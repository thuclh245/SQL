"""Lucky-match (grade E) detection and generic mutation counterexamples."""

from __future__ import annotations

from pathlib import Path

from t2s.benchmark.scoring import compute_result_fingerprint, execute_evaluation_sql
from t2s.evaluation.scoring.deterministic import score_case_deterministic
from t2s.evaluation.scoring.equivalence import compute_result_equivalence
from t2s.evaluation.scoring.lucky_match import (
    LuckyMatchVerdict,
    analyze_structural_divergence,
    assess_lucky_match,
)
from t2s.evaluation.scoring.mutation import generate_mutants
from t2s.evaluation.scoring.semantic_audit import deterministic_semantic_audit
from t2s.evaluation.scoring.taxonomy import Grade
from tests.unit.scoring.conftest import evidence, make_sales_db, table


def test_lucky_match_proven_by_alternate_fixture(tmp_path: Path) -> None:
    # Primary fixture: every row has region 'east', so a wrong filter
    # (region='west' removed) still returns the same rows as the correct query.
    primary = make_sales_db(tmp_path / "primary.sqlite", [(1, "east", 10), (2, "east", 20)])
    # Alternate governed fixture DOES contain 'west' rows, exposing the wrong logic.
    alternate = make_sales_db(
        tmp_path / "alt.sqlite", [(1, "east", 10), (2, "west", 99)]
    )
    gold_sql = "SELECT amount FROM sales WHERE region = 'east'"
    lucky_sql = "SELECT amount FROM sales"  # omits the filter; matches on primary only

    # They match on the primary fixture.
    g = execute_evaluation_sql(gold_sql, primary)
    c = execute_evaluation_sql(lucky_sql, primary)
    assert compute_result_fingerprint(c.rows) == compute_result_fingerprint(g.rows)

    assessment = assess_lucky_match(
        matches_on_primary=True,
        candidate_sql=lucky_sql,
        gold_sql=gold_sql,
        alternate_db_paths=[alternate],
    )
    assert assessment.verdict is LuckyMatchVerdict.LUCKY
    assert assessment.alternate_fixtures_diverged == 1


def test_structural_difference_alone_is_insufficient_not_e() -> None:
    # Two correct-but-different formulations; no counterexample available.
    assessment = assess_lucky_match(
        matches_on_primary=True,
        candidate_sql="SELECT COUNT(*) FROM sales WHERE amount > 5",
        gold_sql="SELECT COUNT(id) FROM sales WHERE amount >= 6",
        alternate_db_paths=None,
    )
    # Structural diff but no proof of wrongness -> INSUFFICIENT, never LUCKY.
    assert assessment.verdict is LuckyMatchVerdict.INSUFFICIENT
    assert assessment.verdict is not LuckyMatchVerdict.LUCKY


def test_equivalent_form_not_flagged_lucky(tmp_path: Path) -> None:
    db = make_sales_db(tmp_path / "d.sqlite", [(1, "east", 10), (2, "west", 20)])
    # Genuinely equivalent alternate formulation -> no divergence -> NOT_LUCKY.
    assessment = assess_lucky_match(
        matches_on_primary=True,
        candidate_sql="SELECT amount FROM sales WHERE amount > 5",
        gold_sql="SELECT amount FROM sales WHERE amount >= 6",
        alternate_db_paths=[db],
    )
    assert assessment.verdict is LuckyMatchVerdict.NOT_LUCKY


def test_lucky_match_promotes_grade_to_e() -> None:
    same = table(("amount",), [(10,), (20,)])
    ev = evidence(
        candidate_sql="SELECT amount FROM sales",
        gold_sql="SELECT amount FROM sales WHERE region='east'",
        candidate_result=same,
        gold_result=same,
    )
    scoring = score_case_deterministic(ev)
    lucky = assess_lucky_match(
        matches_on_primary=True,
        candidate_sql=ev.candidate_sql,
        gold_sql=ev.gold_sql,
        alternate_db_paths=None,
    )
    # Force the proven-lucky path via a synthesized assessment is unnecessary; use
    # a real proven assessment object instead:
    from t2s.evaluation.scoring.lucky_match import LuckyMatchAssessment

    proven = LuckyMatchAssessment(
        verdict=LuckyMatchVerdict.LUCKY,
        evidence=("counterexample_divergence_proven",),
        structural=lucky.structural,
        alternate_fixtures_tested=1,
        alternate_fixtures_diverged=1,
    )
    audit = deterministic_semantic_audit(ev, scoring, lucky_assessment=proven)
    assert audit.classification is Grade.E


def test_mutants_are_logically_wrong_and_scorer_catches_them(tmp_path: Path) -> None:
    # Fixture engineered so every generic mutation actually changes the result
    # (fixture-HIDDEN mutations are the lucky-match scenario, covered separately).
    db = make_sales_db(
        tmp_path / "m.sqlite",
        [(1, "east", 6), (2, "west", 8), (3, "east", 30), (4, "west", 4)],
    )
    gold_sql = "SELECT region, SUM(amount) FROM sales WHERE amount > 5 GROUP BY region"
    gold_res = execute_evaluation_sql(gold_sql, db)
    assert gold_res.ok
    gold_tbl = table(("region", "s"), list(gold_res.rows))

    mutants = generate_mutants(gold_sql)
    assert mutants, "expected at least one mutant"

    caught = 0
    for mutant in mutants:
        res = execute_evaluation_sql(mutant.sql, db)
        if not res.ok:
            caught += 1  # a mutant that fails to execute is trivially not-safe
            continue
        cand_tbl = table(("region", "s"), list(res.rows))
        outcome = compute_result_equivalence(cand_tbl, gold_tbl, gold_sql=gold_sql)
        if not outcome.equivalent:
            caught += 1
    # Every generic logic mutation must be caught as non-equivalent or non-executing;
    # none may be silently marked safe (E05 §21).
    assert caught == len(mutants)


def test_structural_divergence_detects_join_and_predicate_changes() -> None:
    div = analyze_structural_divergence(
        "SELECT a FROM t JOIN u ON t.x = u.y WHERE t.a > 1",
        "SELECT a FROM t JOIN u ON t.x = u.z WHERE t.a > 2",
    )
    assert div.parse_ok
    assert div.join_diff
    assert div.predicate_diff
