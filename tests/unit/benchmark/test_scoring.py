import sqlite3
from pathlib import Path

from t2s.benchmark.scoring import execute_gold_sql, score_execution_accuracy


def test_score_execution_accuracy_matches_unordered_numeric_and_null_rows() -> None:
    generated_rows = [{"a": 2.0, "b": None}, {"a": 1, "b": "x"}]
    gold_rows = [(1.0, "x"), (2, None)]

    assert score_execution_accuracy(
        generated_rows=generated_rows,
        gold_rows=gold_rows,
        gold_sql="SELECT a, b FROM t",
    )


def test_score_execution_accuracy_preserves_order_when_gold_orders() -> None:
    generated_rows = [{"a": 1}, {"a": 2}]
    gold_rows = [(2,), (1,)]

    assert not score_execution_accuracy(
        generated_rows=generated_rows,
        gold_rows=gold_rows,
        gold_sql="SELECT a FROM t ORDER BY a DESC",
    )


def test_score_execution_accuracy_handles_large_integral_float_normalization() -> None:
    generated_rows = [{"a": 4.1550148e16}]
    gold_rows = [(41550148000000000,)]

    assert score_execution_accuracy(
        generated_rows=generated_rows,
        gold_rows=gold_rows,
        gold_sql="SELECT a FROM t",
    )


def test_execute_gold_sql_uses_read_only_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE items(id INTEGER)")
    connection.execute("INSERT INTO items(id) VALUES (1)")
    connection.commit()
    connection.close()

    result = execute_gold_sql("SELECT id FROM items", db_path)

    assert result.ok is True
    assert result.rows == [(1,)]


def test_evaluate_candidate_vs_gold_handles_large_result_sets_without_truncation_artifact(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "large_test.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE records(val INTEGER)")
    conn.executemany("INSERT INTO records(val) VALUES (?)", [(i,) for i in range(1500)])
    conn.commit()
    conn.close()

    cand_sql = "SELECT val FROM records WHERE val >= 0"
    gold_sql = "SELECT val FROM records WHERE val >= 0"

    from t2s.benchmark.scoring import evaluate_candidate_vs_gold

    is_match, cand_res, gold_res = evaluate_candidate_vs_gold(cand_sql, gold_sql, db_path)

    assert cand_res.ok is True
    assert gold_res.ok is True
    assert len(cand_res.rows) == 1500
    assert len(gold_res.rows) == 1500
    assert is_match is True


def test_evaluate_grade_af_exact_match() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    grade, reason = evaluate_grade_af(
        cand_rows=[("apple", 10)],
        gold_rows=[("apple", 10)],
        execution_success=True,
        strict_ex=True,
    )
    assert grade == GradeAF.A


def test_evaluate_grade_af_practical_match_extra_column() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    # Candidate projected ("School A", 95.5), gold projected (95.5,)
    cand_rows = [("School A", 95.5), ("School B", 88.0)]
    gold_rows = [(95.5,), (88.0,)]
    grade, reason = evaluate_grade_af(
        cand_rows=cand_rows,
        gold_rows=gold_rows,
        execution_success=True,
        strict_ex=False,
    )
    assert grade == GradeAF.B
    assert "extra columns" in reason


def test_evaluate_grade_af_practical_match_distinct() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    cand_rows = [("A",), ("A",), ("B",)]
    gold_rows = [("A",), ("B",)]
    grade, reason = evaluate_grade_af(
        cand_rows=cand_rows,
        gold_rows=gold_rows,
        execution_success=True,
        strict_ex=False,
    )
    assert grade == GradeAF.B
    assert "deduplicated" in reason


def test_evaluate_grade_af_near_miss() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    # Candidate returned 3 rows, gold returned 2 of those 3 rows (subset)
    cand_rows = [("A",), ("B",), ("C",)]
    gold_rows = [( "A",), ("B",)]
    grade, reason = evaluate_grade_af(
        cand_rows=cand_rows,
        gold_rows=gold_rows,
        execution_success=True,
        strict_ex=False,
    )
    assert grade == GradeAF.C


def test_evaluate_grade_af_divergent() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    cand_rows = [("X",), ("Y",)]
    gold_rows = [("A",), ("B",)]
    grade, reason = evaluate_grade_af(
        cand_rows=cand_rows,
        gold_rows=gold_rows,
        execution_success=True,
        strict_ex=False,
    )
    assert grade == GradeAF.D


def test_evaluate_grade_af_failure() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    grade, reason = evaluate_grade_af(
        cand_rows=None,
        gold_rows=[("A",)],
        execution_success=False,
        strict_ex=False,
    )
    assert grade == GradeAF.F


def test_evaluate_grade_af_scalar_numeric_tolerance() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    # 47.55% vs 46.88% (rel diff ~1.4% <= 2%) -> Grade B
    grade_b, _ = evaluate_grade_af([(47.5516,)], [(46.8852,)], execution_success=True, strict_ex=False)
    assert grade_b == GradeAF.B

    # 55.0 vs 50.0 (rel diff ~9.0% <= 10%) -> Grade C
    grade_c, _ = evaluate_grade_af([(55.0,)], [(50.0,)], execution_success=True, strict_ex=False)
    assert grade_c == GradeAF.C


def test_evaluate_grade_af_ratio_vs_percentage() -> None:
    from t2s.benchmark.scoring import GradeAF, evaluate_grade_af

    # Decimal 0.4688 vs 46.88% -> Grade B
    grade, _ = evaluate_grade_af([(0.4688,)], [(46.8852,)], execution_success=True, strict_ex=False)
    assert grade == GradeAF.B


