import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class GoldExecutionResult:
    ok: bool
    rows: list[tuple[Any, ...]]
    error: str | None = None


def execute_gold_sql(gold_sql: str, db_path: Path) -> GoldExecutionResult:
    uri = f"file:{db_path.resolve()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            connection.execute("PRAGMA query_only = ON")
            rows = connection.execute(gold_sql).fetchall()
            return GoldExecutionResult(ok=True, rows=rows)
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        return GoldExecutionResult(ok=False, rows=[], error=str(exc))


def score_execution_accuracy(
    generated_rows: list[dict[str, Any]],
    gold_rows: list[tuple[Any, ...]],
    gold_sql: str,
) -> bool:
    predicted_rows = [tuple(row.values()) for row in generated_rows]
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
