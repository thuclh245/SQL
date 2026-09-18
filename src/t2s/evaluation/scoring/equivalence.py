"""Deterministic result equivalence, separate from strict EX (E05 §7, §8).

Strict execution accuracy (:func:`t2s.benchmark.scoring.score_execution_accuracy`)
answers a single yes/no: do the *result values* match as (optionally ordered)
multisets of rows? It is preserved unchanged and remains the deterministic truth
metric.

Result *equivalence* is a strictly richer, still deterministic relation that
additionally recognizes **harmless output-contract variance** — extra columns,
column reordering, row reordering when order is not required, and (only when the
question contract supplies an explicit map) equivalent label/id representation.
Every relaxation is gated by an :class:`OutputContract` and each carries an
explicit rule, so equivalence is never granted merely because "values look
similar" (E05 §8).

Cell normalization is reused verbatim from :mod:`t2s.benchmark.scoring` so the
equivalence engine and the strict scorer / fingerprints agree on NULL handling,
numeric tolerance, boolean and type coercion (E05 §7).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Any

import sqlglot

from t2s.benchmark.scoring import (
    _normalize_value,  # reuse: single source of truth for cell normalization
    _query_requires_order,
)
from t2s.evaluation.scoring.protocols import ResultTable
from t2s.evaluation.scoring.taxonomy import BSubtype
from t2s.evaluation.scoring.versions import EQUIVALENCE_RULES_VERSION

#: Above this candidate column count the column-mapping search is skipped and
#: equivalence is limited to exact / row-order relaxation, to keep scoring
#: deterministic and bounded (n!/(n-k)! blows up). Documented, tested.
MAX_COLUMNS_FOR_MAPPING_SEARCH = 8


@dataclass(frozen=True)
class OutputContract:
    """What the question actually requires of the output (E05 §8, §10).

    Defaults are deliberately conservative but realistic for BIRD-style Q&A:
    row order matters only when the gold query orders; the exact projection
    (column set/order) is *not* required unless the question asks for a specific
    layout; duplicate rows are significant. Label/id equivalence is OFF unless
    the caller supplies an explicit ``value_equivalence`` map — no guessing.
    """

    #: True/False forces ordering behaviour; None → infer from the gold SQL.
    order_required: bool | None = None
    #: When True, extra/reordered columns are NOT harmless (exact layout asked).
    projection_exact: bool = False
    #: When True, duplicate rows are significant (default). When False, rows are
    #: compared as sets (rare; only when the question implies DISTINCT).
    duplicates_significant: bool = True
    #: Explicit, symmetric value-equivalence classes for B3 (e.g. {"M","Male"}).
    #: Only these are treated as equal; never inferred.
    value_equivalence: tuple[frozenset[str], ...] = ()
    #: Free-form note recording *why* a non-default contract was chosen.
    rationale: str | None = None


class EquivalenceLevel(str):
    EXACT = "EXACT"
    RELAXED = "RELAXED"
    NONE = "NONE"


@dataclass(frozen=True)
class EquivalenceOutcome:
    """Result of comparing a candidate result table to gold under a contract."""

    equivalent: bool
    level: str  # one of EquivalenceLevel
    relaxations: tuple[BSubtype, ...]
    rules_version: str
    detail: str
    #: Diagnostic counts for audit views.
    candidate_columns: int = 0
    gold_columns: int = 0

    @property
    def is_exact(self) -> bool:
        return self.level == EquivalenceLevel.EXACT


def _canon_value(value: Any, classes: tuple[frozenset[str], ...]) -> str:
    normalized = _normalize_value(value)
    for cls in classes:
        if normalized in cls:
            # Canonicalize every member of a class to a stable representative
            # (sorted min) so equivalent labels normalize identically.
            return f"~cls:{min(cls)}"
    return normalized


def _normalize_table(
    table: ResultTable, classes: tuple[frozenset[str], ...]
) -> list[tuple[str, ...]]:
    return [tuple(_canon_value(cell, classes) for cell in row) for row in table.rows]


def _rows_equal(
    left: list[tuple[str, ...]],
    right: list[tuple[str, ...]],
    *,
    order_required: bool,
    duplicates_significant: bool,
) -> bool:
    if order_required:
        return left == right
    if duplicates_significant:
        return sorted(left) == sorted(right)
    return {tuple(r) for r in left} == {tuple(r) for r in right}


def compute_result_equivalence(
    candidate: ResultTable | None,
    gold: ResultTable | None,
    *,
    contract: OutputContract | None = None,
    gold_sql: str | None = None,
) -> EquivalenceOutcome:
    """Deterministically classify candidate-vs-gold result equivalence.

    Returns :class:`EquivalenceOutcome` with the applied relaxations (mapped to
    B subtypes). Requires materialized rows; when only fingerprints are available
    the caller should use :func:`fingerprints_match` (exact) and cannot detect
    harmless variance.
    """

    contract = contract or OutputContract()
    if candidate is None or gold is None:
        return EquivalenceOutcome(
            equivalent=False,
            level=EquivalenceLevel.NONE,
            relaxations=(),
            rules_version=EQUIVALENCE_RULES_VERSION,
            detail="missing_result_table",
        )

    order_required = (
        contract.order_required
        if contract.order_required is not None
        else (_query_requires_order(gold_sql) if gold_sql else False)
    )
    classes = contract.value_equivalence
    cand_rows = _normalize_table(candidate, classes)
    gold_rows = _normalize_table(gold, classes)
    n_cand, n_gold = candidate.column_count, gold.column_count

    label_relaxed = bool(classes)

    # --- EXACT: identical columns (count + positional values) and rows -------
    if n_cand == n_gold and _rows_equal(
        cand_rows,
        gold_rows,
        order_required=order_required,
        duplicates_significant=contract.duplicates_significant,
    ):
        relaxations: list[BSubtype] = []
        if not order_required and cand_rows != gold_rows:
            relaxations.append(BSubtype.B4_ROW_ORDER)
        if label_relaxed and candidate.rows != gold.rows:
            relaxations.append(BSubtype.B3_LABEL_EQUIVALENT)
        level = EquivalenceLevel.EXACT if not relaxations else EquivalenceLevel.RELAXED
        return EquivalenceOutcome(
            equivalent=True,
            level=level,
            relaxations=tuple(relaxations),
            rules_version=EQUIVALENCE_RULES_VERSION,
            detail="row_value_match",
            candidate_columns=n_cand,
            gold_columns=n_gold,
        )

    # If the contract demands the exact projection, no column relaxation allowed.
    if contract.projection_exact:
        return EquivalenceOutcome(
            equivalent=False,
            level=EquivalenceLevel.NONE,
            relaxations=(),
            rules_version=EQUIVALENCE_RULES_VERSION,
            detail="projection_exact_mismatch",
            candidate_columns=n_cand,
            gold_columns=n_gold,
        )

    # --- RELAXED: search a column mapping gold_k -> candidate_n --------------
    if n_gold == 0 or n_cand < n_gold or n_cand > MAX_COLUMNS_FOR_MAPPING_SEARCH:
        return EquivalenceOutcome(
            equivalent=False,
            level=EquivalenceLevel.NONE,
            relaxations=(),
            rules_version=EQUIVALENCE_RULES_VERSION,
            detail=(
                "no_column_mapping_within_bounds"
                if n_cand <= MAX_COLUMNS_FOR_MAPPING_SEARCH
                else "column_count_exceeds_mapping_bound"
            ),
            candidate_columns=n_cand,
            gold_columns=n_gold,
        )

    for mapping in permutations(range(n_cand), n_gold):
        projected = [tuple(row[i] for i in mapping) for row in cand_rows]
        if _rows_equal(
            projected,
            gold_rows,
            order_required=order_required,
            duplicates_significant=contract.duplicates_significant,
        ):
            relaxations = []
            if n_cand > n_gold:
                relaxations.append(BSubtype.B1_EXTRA_COLUMNS)
            # Non-identity order of the mapping over the first n_gold indices, or
            # any use of later columns, is a column-order variance.
            if mapping != tuple(range(n_gold)):
                relaxations.append(BSubtype.B2_COLUMN_ORDER)
            if not order_required and projected != gold_rows:
                relaxations.append(BSubtype.B4_ROW_ORDER)
            if label_relaxed:
                relaxations.append(BSubtype.B3_LABEL_EQUIVALENT)
            return EquivalenceOutcome(
                equivalent=True,
                level=EquivalenceLevel.RELAXED,
                relaxations=tuple(dict.fromkeys(relaxations)),
                rules_version=EQUIVALENCE_RULES_VERSION,
                detail=f"column_mapping={mapping}",
                candidate_columns=n_cand,
                gold_columns=n_gold,
            )

    return EquivalenceOutcome(
        equivalent=False,
        level=EquivalenceLevel.NONE,
        relaxations=(),
        rules_version=EQUIVALENCE_RULES_VERSION,
        detail="no_matching_column_mapping",
        candidate_columns=n_cand,
        gold_columns=n_gold,
    )


def fingerprints_match(candidate_fp: str | None, gold_fp: str | None) -> bool | None:
    """Exact result equality via fingerprints. None when either is absent."""

    if candidate_fp is None or gold_fp is None:
        return None
    return candidate_fp == gold_fp


def sql_forms_differ(candidate_sql: str | None, gold_sql: str | None) -> bool | None:
    """True when two SQL strings normalize to different canonical forms (B5 hint).

    Returns None when either side is missing or unparseable — never guesses.
    """

    if not candidate_sql or not gold_sql:
        return None
    try:
        left = sqlglot.parse_one(candidate_sql, dialect="sqlite")
        right = sqlglot.parse_one(gold_sql, dialect="sqlite")
    except sqlglot.errors.SqlglotError:
        return None
    return left.sql(dialect="sqlite", normalize=True) != right.sql(
        dialect="sqlite", normalize=True
    )


def equivalence_rules_manifest() -> dict[str, Any]:
    """Machine-readable description of every relaxation rule (E05 §8, §19)."""

    return {
        "equivalence_rules_version": EQUIVALENCE_RULES_VERSION,
        "cell_normalization_source": "t2s.benchmark.scoring._normalize_value",
        "max_columns_for_mapping_search": MAX_COLUMNS_FOR_MAPPING_SEARCH,
        "relaxations": [
            {
                "subtype": BSubtype.B1_EXTRA_COLUMNS.value,
                "rule": "candidate has extra columns beyond a column mapping that "
                "reproduces every gold row; allowed unless contract.projection_exact.",
            },
            {
                "subtype": BSubtype.B2_COLUMN_ORDER.value,
                "rule": "gold columns map to candidate columns in a different order; "
                "allowed unless contract.projection_exact.",
            },
            {
                "subtype": BSubtype.B3_LABEL_EQUIVALENT.value,
                "rule": "values equal only under an EXPLICIT contract.value_equivalence "
                "class; never inferred.",
            },
            {
                "subtype": BSubtype.B4_ROW_ORDER.value,
                "rule": "row order differs but order is not required (contract or gold "
                "SQL has no ORDER BY).",
            },
            {
                "subtype": BSubtype.B5_EQUIVALENT_FORM.value,
                "rule": "results equivalent while candidate SQL normalizes to a "
                "different form than gold; assigned by the semantic auditor, not the "
                "result comparator.",
            },
        ],
        "default_contract": {
            "order_required": "inferred_from_gold_order_by",
            "projection_exact": False,
            "duplicates_significant": True,
            "value_equivalence": "empty_unless_supplied",
        },
    }
