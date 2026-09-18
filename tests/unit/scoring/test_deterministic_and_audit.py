"""Layer-1 deterministic scoring + Layer-2 deterministic pre-classifier."""

from __future__ import annotations

from t2s.evaluation.scoring.deterministic import compute_strict_ex, score_case_deterministic
from t2s.evaluation.scoring.semantic_audit import deterministic_semantic_audit
from t2s.evaluation.scoring.taxonomy import BSubtype, Grade
from tests.unit.scoring.conftest import evidence, table


def test_strict_ex_tristate_none_when_candidate_missing() -> None:
    ev = evidence(candidate_sql=None, candidate_result=None, gold_result=table(("n",), [(1,)]))
    assert compute_strict_ex(ev) is None


def test_missing_candidate_sql_yields_grade_f() -> None:
    ev = evidence(candidate_sql=None, candidate_result=None, gold_result=table(("n",), [(1,)]))
    scoring = score_case_deterministic(ev)
    assert "candidate_sql_missing" in scoring.determination_blockers
    audit = deterministic_semantic_audit(ev, scoring)
    assert audit.classification is Grade.F
    assert audit.semantic_correctness_assessed is False


def test_exact_match_grade_a() -> None:
    t = table(("n",), [(1,), (2,)])
    ev = evidence(candidate_result=t, gold_result=t, gold_sql="SELECT n FROM t")
    scoring = score_case_deterministic(ev)
    assert scoring.strict_ex is True
    audit = deterministic_semantic_audit(ev, scoring)
    assert audit.classification is Grade.A


def test_harmless_variance_grade_b() -> None:
    gold = table(("region",), [("east",), ("west",)])
    cand = table(("region", "amount"), [("east", 1), ("west", 2)])
    ev = evidence(candidate_result=cand, gold_result=gold, gold_sql="SELECT region FROM t")
    scoring = score_case_deterministic(ev)
    audit = deterministic_semantic_audit(ev, scoring)
    assert audit.classification is Grade.B
    assert audit.subtype is BSubtype.B1_EXTRA_COLUMNS


def test_result_mismatch_provisional_d_low_confidence() -> None:
    ev = evidence(
        candidate_result=table(("n",), [(1,)]),
        gold_result=table(("n",), [(2,)]),
        gold_sql="SELECT n FROM t",
    )
    scoring = score_case_deterministic(ev)
    assert scoring.strict_ex is False
    audit = deterministic_semantic_audit(ev, scoring)
    assert audit.classification is Grade.D
    assert audit.confidence < 0.5  # flagged for human review, not asserted certain


def test_fingerprint_only_evidence_supports_strict_ex() -> None:
    # No row tables, only fingerprints (the minimal E04 record shape).
    same = table(("n",), [(1,), (2,)])
    ev = evidence(candidate_result=same, gold_result=same, gold_sql="SELECT n FROM t")
    stripped = type(ev)(
        case_id=ev.case_id,
        replicate_id=ev.replicate_id,
        db_id=ev.db_id,
        question=ev.question,
        candidate_sql=ev.candidate_sql,
        gold_sql=ev.gold_sql,
        runtime_status="SUCCESS",
        candidate_result=None,
        gold_result=None,
        candidate_fingerprint=ev.candidate_fingerprint,
        gold_fingerprint=ev.gold_fingerprint,
    )
    scoring = score_case_deterministic(stripped)
    assert scoring.strict_ex is True
    assert scoring.fingerprint_match is True
