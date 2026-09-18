"""Layer 1 - mechanical / deterministic scoring (E05 §4, §7, §8).

Produces a :class:`ScoringRecord` from a :class:`CaseRunEvidence`. All signals
here are reproducible and free of judgement:

* **strict_ex** - strict execution accuracy, computed via the *unchanged*
  runtime scorer :func:`t2s.benchmark.scoring.score_execution_accuracy` when
  rows are captured, else via fingerprint equality. Tri-state: True / False /
  None (None = not determinable, never silently False).
* **deterministic_equivalent** - the richer result-equivalence relation from
  :mod:`t2s.evaluation.scoring.equivalence`, with harmless-variance relaxations recorded.
* **fingerprint_match** - cheap exact equality independent of row capture.
* **determination_blockers** - missing-evidence reasons that force grade F.

This module does not assign A-F grades; that is Layer 2's job. It only exposes
deterministic facts the semantic auditor consumes.
"""

from __future__ import annotations

from t2s.benchmark.scoring import score_execution_accuracy
from t2s.evaluation.scoring.equivalence import (
    OutputContract,
    compute_result_equivalence,
    fingerprints_match,
)
from t2s.evaluation.scoring.protocols import CaseRunEvidence, determination_blockers
from t2s.evaluation.scoring.records import ScoringRecord
from t2s.evaluation.scoring.versions import EQUIVALENCE_RULES_VERSION, SCORER_VERSION


def compute_strict_ex(evidence: CaseRunEvidence) -> bool | None:
    """Strict execution accuracy as a tri-state.

    Prefers materialized rows (delegates to the unchanged runtime scorer). Falls
    back to fingerprint equality when rows are absent. Returns None when neither
    the candidate nor the gold reference is available, or when the candidate did
    not execute successfully — the strict metric is undefined, not False.
    """

    # Any missing side => undefined.
    have_candidate = (
        evidence.candidate_result is not None or evidence.candidate_fingerprint is not None
    )
    have_gold = evidence.gold_result is not None or evidence.gold_fingerprint is not None
    if not have_candidate or not have_gold:
        return None

    if evidence.candidate_result is not None and evidence.gold_result is not None:
        return score_execution_accuracy(
            generated_rows=list(evidence.candidate_result.rows),
            gold_rows=list(evidence.gold_result.rows),
            gold_sql=evidence.gold_sql or "",
        )
    return fingerprints_match(evidence.candidate_fingerprint, evidence.gold_fingerprint)


def score_case_deterministic(
    evidence: CaseRunEvidence,
    *,
    contract: OutputContract | None = None,
) -> ScoringRecord:
    """Compute the full Layer-1 :class:`ScoringRecord` for one replicate."""

    blockers = tuple(determination_blockers(evidence))
    strict_ex = compute_strict_ex(evidence)
    fp_match = fingerprints_match(evidence.candidate_fingerprint, evidence.gold_fingerprint)

    equivalence = compute_result_equivalence(
        evidence.candidate_result,
        evidence.gold_result,
        contract=contract,
        gold_sql=evidence.gold_sql,
    )
    # deterministic_equivalent is only asserted when result tables were present;
    # otherwise fall back to fingerprint equality as the exact-only signal. On the
    # fingerprint-only path there is no row detail, so an exact fingerprint match
    # is reported as EXACT (fingerprints are an exact equality check) and a
    # mismatch as NONE — the row-based equivalence outcome (computed against absent
    # tables) is not meaningful here.
    equivalence_level = equivalence.level
    equivalence_relaxations = equivalence.relaxations
    equivalence_detail = equivalence.detail
    if evidence.candidate_result is not None and evidence.gold_result is not None:
        deterministic_equivalent: bool | None = equivalence.equivalent
    else:
        deterministic_equivalent = fp_match
        if fp_match is True:
            equivalence_level = "EXACT"
            equivalence_relaxations = ()
            equivalence_detail = "fingerprint_exact_match"
        elif fp_match is False:
            equivalence_level = "NONE"
            equivalence_detail = "fingerprint_mismatch"

    return ScoringRecord(
        case_id=evidence.case_id,
        replicate_id=evidence.replicate_id,
        db_id=evidence.db_id,
        scorer_version=SCORER_VERSION,
        equivalence_rules_version=EQUIVALENCE_RULES_VERSION,
        runtime_status=evidence.runtime_status,
        candidate_execution_ok=evidence.candidate_execution_ok,
        gold_execution_ok=evidence.gold_execution_ok,
        strict_ex=strict_ex,
        deterministic_equivalent=deterministic_equivalent,
        equivalence_level=equivalence_level,
        equivalence_relaxations=equivalence_relaxations,
        equivalence_detail=equivalence_detail,
        fingerprint_match=fp_match,
        candidate_columns=(
            evidence.candidate_result.column_count
            if evidence.candidate_result is not None
            else None
        ),
        gold_columns=(
            evidence.gold_result.column_count if evidence.gold_result is not None else None
        ),
        determination_blockers=blockers,
    )
