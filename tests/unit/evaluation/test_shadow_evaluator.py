"""Unit tests for Phase 7A ShadowEvaluator."""

import sqlite3
from pathlib import Path

import pytest

from t2s.evaluation.shadow_evaluator import (
    ShadowEvaluationStatus,
    ShadowEvaluator,
    UnresolvedNoteCategory,
    classify_unresolved_note,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> tuple[Path, str]:
    db_id = "test_db"
    db_dir = tmp_path / db_id
    db_dir.mkdir(parents=True)
    db_file = db_dir / f"{db_id}.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.commit()
    conn.close()
    return tmp_path, db_id


def test_classify_unresolved_notes() -> None:
    assert (
        classify_unresolved_note("No column or table for telephone number")
        == UnresolvedNoteCategory.HARD_BLOCKER
    )
    assert (
        classify_unresolved_note("Tie-breaker rule was not specified for equal score")
        == UnresolvedNoteCategory.TIE_BREAK_NOTE
    )
    assert (
        classify_unresolved_note("Missing rows or null values were excluded")
        == UnresolvedNoteCategory.SOFT_CAVEAT
    )
    assert (
        classify_unresolved_note("Assumed high school means grades 9 to 12")
        == UnresolvedNoteCategory.SOFT_ASSUMPTION
    )
    assert (
        classify_unresolved_note("Exact stored string for country code is unknown")
        == UnresolvedNoteCategory.DATA_SEMANTIC_UNCERTAINTY
    )
    assert (
        classify_unresolved_note("Foreign key relationship was missing")
        == UnresolvedNoteCategory.SCHEMA_UNCERTAINTY
    )
    assert (
        classify_unresolved_note("Random observation about query") == UnresolvedNoteCategory.OTHER
    )


def test_candidate_unavailable(temp_db: tuple[Path, str]) -> None:
    db_root, db_id = temp_db
    evaluator = ShadowEvaluator(database_root=db_root)
    result = evaluator.evaluate_case(
        case_id="c1",
        db_id=db_id,
        candidate_sql=None,
        gold_sql="SELECT name FROM users",
    )
    assert result.status == ShadowEvaluationStatus.CANDIDATE_UNAVAILABLE


def test_candidate_safety_rejected(temp_db: tuple[Path, str]) -> None:
    db_root, db_id = temp_db
    evaluator = ShadowEvaluator(database_root=db_root)
    result = evaluator.evaluate_case(
        case_id="c2",
        db_id=db_id,
        candidate_sql="DROP TABLE users;",
        gold_sql="SELECT name FROM users",
    )
    assert result.status == ShadowEvaluationStatus.SHADOW_SAFETY_REJECTED
    assert result.safety_valid is False


def test_candidate_access_rejected(temp_db: tuple[Path, str]) -> None:
    db_root, db_id = temp_db
    evaluator = ShadowEvaluator(database_root=db_root)
    result = evaluator.evaluate_case(
        case_id="c3",
        db_id=db_id,
        candidate_sql="SELECT * FROM secret_table;",
        gold_sql="SELECT name FROM users",
        authorized_tables={"users"},
    )
    assert result.status == ShadowEvaluationStatus.SHADOW_ACCESS_REJECTED
    assert result.authorization_valid is False


def test_candidate_execution_error_syntax(temp_db: tuple[Path, str]) -> None:
    db_root, db_id = temp_db
    evaluator = ShadowEvaluator(database_root=db_root)
    result = evaluator.evaluate_case(
        case_id="c4",
        db_id=db_id,
        candidate_sql="SELECT FROM WHERE users;",
        gold_sql="SELECT name FROM users",
    )
    assert result.status == ShadowEvaluationStatus.SHADOW_EXECUTION_ERROR
    assert result.ast_valid is False


def test_candidate_correct(temp_db: tuple[Path, str]) -> None:
    db_root, db_id = temp_db
    evaluator = ShadowEvaluator(database_root=db_root)
    result = evaluator.evaluate_case(
        case_id="c5",
        db_id=db_id,
        candidate_sql="SELECT name FROM users WHERE id = 1;",
        gold_sql="SELECT name FROM users WHERE id = 1",
        authorized_tables={"users"},
        unresolved_notes=["Assumed id = 1 is alice"],
    )
    assert result.status == ShadowEvaluationStatus.SHADOW_CORRECT
    assert result.matches_gold is True


def test_candidate_incorrect(temp_db: tuple[Path, str]) -> None:
    db_root, db_id = temp_db
    evaluator = ShadowEvaluator(database_root=db_root)
    result = evaluator.evaluate_case(
        case_id="c6",
        db_id=db_id,
        candidate_sql="SELECT name FROM users WHERE id = 2;",
        gold_sql="SELECT name FROM users WHERE id = 1",
        authorized_tables={"users"},
    )
    assert result.status == ShadowEvaluationStatus.SHADOW_INCORRECT
    assert result.matches_gold is False


def test_diagnostics_and_error_budget_helpers() -> None:
    from t2s.benchmark.case_loader import BenchmarkCaseBundle, InferenceBenchmarkCase, ScoringGold
    from t2s.evaluation.shadow_evaluator import (
        analyze_grounding_diagnostics,
        decompose_error_budget,
    )

    bundle = BenchmarkCaseBundle(
        inference_case=InferenceBenchmarkCase(
            case_id="bird_eval_5",
            question_id=5,
            db_id="california_schools",
            question="Question",
            evidence="Evidence",
            bird_difficulty="simple",
            t2s_stratum="S2",
        ),
        scoring_gold=ScoringGold(
            official_sql=(
                "SELECT COUNT(DISTINCT T2.School) FROM satscores AS T1 "
                "INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode "
                "WHERE T2.Virtual = 'F' AND T1.AvgScrMath > 400"
            ),
            curated_sql=None,
        ),
    )
    bundles = {"bird_eval_5": bundle}
    case_record = {
        "case_id": "bird_eval_5",
        "runtime_status": "UNRESOLVED",
        "failure_taxonomy": "UNRESOLVED",
        "execution_correct": None,
        "final_tables": ["california_schools.main.schools", "california_schools.main.satscores"],
    }
    tables_json = Path("data/bird_mini_dev/mini_dev_tables.json")

    diag = analyze_grounding_diagnostics([case_record], bundles, tables_json)
    assert diag["gold_table_coverage"]["covered"] == 2
    assert diag["gold_table_coverage"]["total"] == 2
    assert diag["gold_table_coverage"]["full_cases"] == 1

    budget = decompose_error_budget([case_record], bundles, tables_json)
    assert "bird_eval_5" in budget["H_SUSPECTED_FALSE_ABSTENTION"]
