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
