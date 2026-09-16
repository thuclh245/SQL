import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class EvaluationExecutionResult:
    ok: bool
    rows: list[tuple[Any, ...]]
    error: str | None = None


# Backward-compatible alias
GoldExecutionResult = EvaluationExecutionResult


def execute_evaluation_sql(
    sql: str,
    db_path: Path | str,
    timeout_seconds: int = 30,
    maximum_result_rows: int | None = None,
) -> EvaluationExecutionResult:
    resolved_path = Path(db_path).resolve()
    uri = f"file:{resolved_path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=timeout_seconds)
        try:
            connection.execute("PRAGMA query_only = ON")
            cursor = connection.cursor()
            cursor.execute(sql)
            if maximum_result_rows is not None:
                rows = cursor.fetchmany(maximum_result_rows)
            else:
                rows = cursor.fetchall()
            return EvaluationExecutionResult(ok=True, rows=rows)
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        return EvaluationExecutionResult(ok=False, rows=[], error=str(exc))


def execute_gold_sql(gold_sql: str, db_path: Path) -> EvaluationExecutionResult:
    return execute_evaluation_sql(gold_sql, db_path, timeout_seconds=30)


def evaluate_candidate_vs_gold(
    candidate_sql: str,
    gold_sql: str,
    db_path: Path | str,
    timeout_seconds: int = 30,
    maximum_result_rows: int | None = None,
) -> tuple[bool, EvaluationExecutionResult, EvaluationExecutionResult]:
    """Symmetrically execute and score candidate SQL against gold SQL for benchmark evaluation."""
    cand_res = execute_evaluation_sql(
        candidate_sql,
        db_path,
        timeout_seconds=timeout_seconds,
        maximum_result_rows=maximum_result_rows,
    )
    gold_res = execute_evaluation_sql(
        gold_sql,
        db_path,
        timeout_seconds=timeout_seconds,
        maximum_result_rows=maximum_result_rows,
    )
    if not cand_res.ok or not gold_res.ok:
        return False, cand_res, gold_res
    correct = score_execution_accuracy(
        generated_rows=cand_res.rows,
        gold_rows=gold_res.rows,
        gold_sql=gold_sql,
    )
    return correct, cand_res, gold_res


def score_execution_accuracy(
    generated_rows: list[dict[str, Any]] | list[tuple[Any, ...]],
    gold_rows: list[tuple[Any, ...]],
    gold_sql: str,
) -> bool:
    predicted_rows = [
        tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in generated_rows
    ]
    if _query_requires_order(gold_sql):
        return _normalize_rows(predicted_rows) == _normalize_rows(gold_rows)
    return sorted(_normalize_rows(predicted_rows)) == sorted(_normalize_rows(gold_rows))


def _query_requires_order(sql: str) -> bool:
    try:
        parsed_expression = sqlglot.parse_one(sql, dialect="sqlite")
    except sqlglot.errors.SqlglotError:
        return False
    return parsed_expression.find(exp.Order) is not None


def _normalize_rows(rows: list[tuple[Any, ...]]) -> list[tuple[str, ...]]:
    return [tuple(_normalize_value(value) for value in row) for row in rows]


def _normalize_value(value: Any) -> str:
    if value is None:
        return "<NULL>"
    if isinstance(value, bool):
        return "1" if value else "0"
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    normalized_decimal = decimal_value.normalize()
    if normalized_decimal == normalized_decimal.to_integral():
        try:
            return str(normalized_decimal.quantize(Decimal("1")))
        except InvalidOperation:
            return format(normalized_decimal, "f")
    return format(normalized_decimal, "f")
