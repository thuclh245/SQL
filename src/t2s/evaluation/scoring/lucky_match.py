"""Lucky-match (grade E) detection (E05 §9).

Grade ``E`` exists because a logically wrong query can return the same result as
gold *on the current fixture* by accident. Assigning ``E`` is deliberately hard:
it requires evidence that (1) the candidate matches gold on the primary fixture
**and** (2) the candidate's logic is actually wrong. A mere structural difference
is NOT sufficient (E05 §9) — many correct queries are structurally different
(that is grade B5). When logic-wrong evidence is absent, the auditor must choose
``F`` (unknown) or ``D`` (if independently shown wrong), never ``E``.

Two evidence sources are supported:

* **Structural divergence** (advisory only) - the candidate and gold normalize
  to different SQL and differ in predicates / joins / aggregations. On its own
  this is *insufficient* for E.
* **Counterexample divergence** (decisive) - the candidate and gold produce
  *different* results on a governed alternate fixture while matching on the
  primary one. This proves the logic is wrong and the primary match was luck.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import sqlglot
from sqlglot import exp

from t2s.benchmark.scoring import compute_result_fingerprint, execute_evaluation_sql


@dataclass(frozen=True)
class StructuralDivergence:
    """Advisory structural comparison of candidate vs gold SQL."""

    parse_ok: bool
    normalized_forms_differ: bool | None
    predicate_diff: bool
    join_diff: bool
    aggregation_diff: bool
    notes: tuple[str, ...]

    @property
    def any_logic_diff(self) -> bool:
        return self.predicate_diff or self.join_diff or self.aggregation_diff


class LuckyMatchVerdict(StrEnum):
    LUCKY = "LUCKY"  # proven grade-E
    NOT_LUCKY = "NOT_LUCKY"  # matches and no divergence found on tested fixtures
    INSUFFICIENT = "INSUFFICIENT"  # cannot prove either way -> auditor uses F/D
    NOT_APPLICABLE = "NOT_APPLICABLE"  # candidate did not even match on primary


@dataclass(frozen=True)
class LuckyMatchAssessment:
    verdict: LuckyMatchVerdict
    evidence: tuple[str, ...]
    structural: StructuralDivergence | None
    alternate_fixtures_tested: int
    alternate_fixtures_diverged: int


def _multiset_agg_names(tree: exp.Expression) -> set[str]:
    return {func.key.upper() for func in tree.find_all(exp.AggFunc)}


def _predicate_forms(tree: exp.Expression) -> set[str]:
    forms: set[str] = set()
    for select in tree.find_all(exp.Select):
        where = select.args.get("where")
        if where is not None:
            for pred in where.find_all(exp.Predicate):
                forms.add(pred.sql(dialect="sqlite", normalize=True))
    return forms


def _join_forms(tree: exp.Expression) -> set[str]:
    forms: set[str] = set()
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is not None:
            forms.add(on.sql(dialect="sqlite", normalize=True))
    return forms


def analyze_structural_divergence(
    candidate_sql: str | None,
    gold_sql: str | None,
) -> StructuralDivergence:
    """Compare candidate vs gold SQL structure (advisory only, never decisive)."""

    if not candidate_sql or not gold_sql:
        return StructuralDivergence(
            parse_ok=False,
            normalized_forms_differ=None,
            predicate_diff=False,
            join_diff=False,
            aggregation_diff=False,
            notes=("missing_sql",),
        )
    try:
        cand = sqlglot.parse_one(candidate_sql, dialect="sqlite")
        gold = sqlglot.parse_one(gold_sql, dialect="sqlite")
    except sqlglot.errors.SqlglotError:
        return StructuralDivergence(
            parse_ok=False,
            normalized_forms_differ=None,
            predicate_diff=False,
            join_diff=False,
            aggregation_diff=False,
            notes=("unparseable_sql",),
        )

    notes: list[str] = []
    predicate_diff = _predicate_forms(cand) != _predicate_forms(gold)
    join_diff = _join_forms(cand) != _join_forms(gold)
    aggregation_diff = _multiset_agg_names(cand) != _multiset_agg_names(gold)
    if predicate_diff:
        notes.append("predicate_sets_differ")
    if join_diff:
        notes.append("join_conditions_differ")
    if aggregation_diff:
        notes.append("aggregation_functions_differ")
    normalized_differ = cand.sql(dialect="sqlite", normalize=True) != gold.sql(
        dialect="sqlite", normalize=True
    )
    return StructuralDivergence(
        parse_ok=True,
        normalized_forms_differ=normalized_differ,
        predicate_diff=predicate_diff,
        join_diff=join_diff,
        aggregation_diff=aggregation_diff,
        notes=tuple(notes),
    )


def counterexample_divergence(
    candidate_sql: str,
    gold_sql: str,
    alternate_db_paths: list[Path | str],
) -> tuple[int, int, list[str]]:
    """Execute candidate & gold on governed alternate fixtures.

    Returns ``(tested, diverged, notes)``. A fixture is "diverged" when both
    statements execute successfully and their result fingerprints differ — proof
    the candidate's logic is wrong and the primary match was luck. Fixtures where
    either side errors are counted as tested but not diverged (inconclusive).
    """

    tested = 0
    diverged = 0
    notes: list[str] = []
    for db_path in alternate_db_paths:
        cand_res = execute_evaluation_sql(candidate_sql, db_path)
        gold_res = execute_evaluation_sql(gold_sql, db_path)
        tested += 1
        if not cand_res.ok or not gold_res.ok:
            notes.append(f"{Path(db_path).name}:execution_error")
            continue
        cand_fp = compute_result_fingerprint(cand_res.rows)
        gold_fp = compute_result_fingerprint(gold_res.rows)
        # Order-insensitive divergence: differ regardless of row order.
        cand_sorted = compute_result_fingerprint(sorted(cand_res.rows, key=repr))
        gold_sorted = compute_result_fingerprint(sorted(gold_res.rows, key=repr))
        if cand_fp != gold_fp and cand_sorted != gold_sorted:
            diverged += 1
            notes.append(f"{Path(db_path).name}:diverged")
    return tested, diverged, notes


def assess_lucky_match(
    *,
    matches_on_primary: bool,
    candidate_sql: str | None,
    gold_sql: str | None,
    alternate_db_paths: list[Path | str] | None = None,
) -> LuckyMatchAssessment:
    """Decide whether a primary-fixture match is a lucky match (E05 §9).

    * If the candidate does not match on the primary fixture, lucky-match does
      not apply (a mismatch is a plain wrong result, handled as D/F upstream).
    * ``LUCKY`` (grade E) requires a proven counterexample divergence.
    * Structural difference alone yields ``INSUFFICIENT`` — the auditor then
      chooses F (unknown) or D (if wrongness is independently established), never
      E, per E05 §9.
    """

    if not matches_on_primary:
        return LuckyMatchAssessment(
            verdict=LuckyMatchVerdict.NOT_APPLICABLE,
            evidence=("no_primary_match",),
            structural=None,
            alternate_fixtures_tested=0,
            alternate_fixtures_diverged=0,
        )

    structural = analyze_structural_divergence(candidate_sql, gold_sql)
    evidence: list[str] = []

    tested = diverged = 0
    if alternate_db_paths and candidate_sql and gold_sql:
        tested, diverged, notes = counterexample_divergence(
            candidate_sql, gold_sql, alternate_db_paths
        )
        evidence.extend(notes)

    if diverged > 0:
        evidence.append("counterexample_divergence_proven")
        return LuckyMatchAssessment(
            verdict=LuckyMatchVerdict.LUCKY,
            evidence=tuple(evidence),
            structural=structural,
            alternate_fixtures_tested=tested,
            alternate_fixtures_diverged=diverged,
        )

    # No decisive counterexample. Report what structural analysis found, but do
    # NOT escalate structural difference to E.
    if structural.any_logic_diff:
        evidence.extend(structural.notes)
        verdict = (
            LuckyMatchVerdict.NOT_LUCKY
            if tested > 0
            else LuckyMatchVerdict.INSUFFICIENT
        )
        if verdict is LuckyMatchVerdict.INSUFFICIENT:
            evidence.append("structural_diff_without_counterexample")
        else:
            evidence.append("no_divergence_on_tested_fixtures")
        return LuckyMatchAssessment(
            verdict=verdict,
            evidence=tuple(evidence),
            structural=structural,
            alternate_fixtures_tested=tested,
            alternate_fixtures_diverged=diverged,
        )

    evidence.append("structurally_equivalent_and_matches")
    return LuckyMatchAssessment(
        verdict=LuckyMatchVerdict.NOT_LUCKY,
        evidence=tuple(evidence),
        structural=structural,
        alternate_fixtures_tested=tested,
        alternate_fixtures_diverged=diverged,
    )
