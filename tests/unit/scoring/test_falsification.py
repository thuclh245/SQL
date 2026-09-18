"""E05 §25 independent self-review: each falsification attempt must FAIL to break
the scorer. Every test here encodes one 'can the scorer be fooled?' question and
asserts the answer is no.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from t2s.benchmark.scoring import compute_result_fingerprint, execute_evaluation_sql
from t2s.evaluation.scoring.aggregation import assert_not_pooled, case_level_metrics
from t2s.evaluation.scoring.deterministic import score_case_deterministic
from t2s.evaluation.scoring.equivalence import compute_result_equivalence
from t2s.evaluation.scoring.lucky_match import LuckyMatchVerdict, assess_lucky_match
from t2s.evaluation.scoring.records import new_semantic_audit_record
from t2s.evaluation.scoring.semantic_audit import deterministic_semantic_audit
from t2s.evaluation.scoring.taxonomy import Grade
from tests.unit.scoring.conftest import evidence, make_sales_db, table


def test_wrong_sql_hidden_by_fixture_is_not_silently_ab(tmp_path: Path) -> None:
    """Can a wrong SQL get A/B because the fixture hides the error? -> caught as E."""
    primary = make_sales_db(tmp_path / "p.sqlite", [(1, "east", 10)])
    alt = make_sales_db(tmp_path / "a.sqlite", [(1, "east", 10), (2, "west", 50)])
    gold = "SELECT amount FROM sales WHERE region='east'"
    wrong = "SELECT amount FROM sales"
    assert compute_result_fingerprint(
        execute_evaluation_sql(wrong, primary).rows
    ) == compute_result_fingerprint(execute_evaluation_sql(gold, primary).rows)
    verdict = assess_lucky_match(
        matches_on_primary=True, candidate_sql=wrong, gold_sql=gold, alternate_db_paths=[alt]
    )
    assert verdict.verdict is LuckyMatchVerdict.LUCKY


def test_correct_query_with_harmless_columns_is_not_d() -> None:
    """Can a correct query get D because output columns differ harmlessly? -> no, B."""
    gold = table(("region",), [("east",)])
    cand = table(("region", "extra"), [("east", 1)])
    ev = evidence(candidate_result=cand, gold_result=gold, gold_sql="SELECT region FROM t")
    audit = deterministic_semantic_audit(ev, score_case_deterministic(ev))
    assert audit.classification is Grade.B


def test_f_cannot_disappear_from_denominator() -> None:
    """Can F disappear from the denominator? -> no."""
    records = [
        new_semantic_audit_record(
            case_id=f"c{i}", replicate_id="r1", classification=g,
            rationale="t", reviewer_id_or_role="t",
        )
        for i, g in enumerate([Grade.A, Grade.F, Grade.F])
    ]
    m = case_level_metrics(records)
    assert m.production_semantic_safe.denominator == 3
    assert m.unknown.numerator == 2


def test_ambiguity_not_confused_with_missing_evidence() -> None:
    """Missing evidence must be F, never C (ambiguity)."""
    ev = evidence(candidate_sql=None, candidate_result=None, gold_result=table(("n",), [(1,)]))
    audit = deterministic_semantic_audit(ev, score_case_deterministic(ev))
    assert audit.classification is Grade.F
    assert audit.classification is not Grade.C


def test_order_sensitive_not_treated_order_insensitive() -> None:
    gold = table(("n",), [(1,), (2,)])
    cand = table(("n",), [(2,), (1,)])
    assert not compute_result_equivalence(
        cand, gold, gold_sql="SELECT n FROM t ORDER BY n"
    ).equivalent


def test_nulls_do_not_create_false_equivalence() -> None:
    gold = table(("a",), [(None,)])
    cand = table(("a",), [(0,)])
    assert not compute_result_equivalence(cand, gold, gold_sql="SELECT a FROM t").equivalent


def test_replicates_cannot_be_accidentally_pooled() -> None:
    records = [
        new_semantic_audit_record(
            case_id="c1", replicate_id=r, classification=Grade.A,
            rationale="t", reviewer_id_or_role="t",
        )
        for r in ("r1", "r2", "r3")
    ]
    with pytest.raises(ValueError):
        assert_not_pooled(records)


def test_structural_diff_alone_never_becomes_e() -> None:
    """Can every structural difference be labelled E? -> no; needs a counterexample."""
    verdict = assess_lucky_match(
        matches_on_primary=True,
        candidate_sql="SELECT COUNT(*) FROM t",
        gold_sql="SELECT COUNT(id) FROM t",
        alternate_db_paths=None,
    )
    assert verdict.verdict is not LuckyMatchVerdict.LUCKY
