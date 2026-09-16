from typing import Any

import psycopg
import pytest
from psycopg.sql import Composable

from t2s.database import PostgresReadOnlyQueryExecutor, QueryExecutionPolicy
from t2s.errors import (
    QueryExecutionError,
    QueryExecutionTimeoutError,
    SqlExplainError,
    UnsafeSqlError,
)


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def execute(self, query: object, params: object = None) -> None:
        rendered = query.as_string(None) if isinstance(query, Composable) else str(query)
        self.connection.statements.append(rendered)
        if self.connection.raise_on_query is not None and not rendered.startswith("SET "):
            raise self.connection.raise_on_query

    @property
    def description(self) -> list[tuple[str, ...]] | None:
        return [(name,) for name in self.connection.columns]

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        return self.connection.rows[:size]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.connection.rows


class FakeConnection:
    def __init__(
        self,
        columns: list[str] | None = None,
        rows: list[tuple[Any, ...]] | None = None,
        raise_on_query: BaseException | None = None,
    ) -> None:
        self.columns = columns or []
        self.rows = rows or []
        self.raise_on_query = raise_on_query
        self.statements: list[str] = []
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def _executor(connection: FakeConnection) -> PostgresReadOnlyQueryExecutor:
    return PostgresReadOnlyQueryExecutor(
        database_url="postgresql://readonly@localhost/warehouse",
        connection_factory=lambda: connection,  # type: ignore[arg-type]
    )


def _query_canceled() -> psycopg.errors.QueryCanceled:
    return psycopg.errors.QueryCanceled("canceling statement due to statement timeout")


def test_transaction_is_opened_read_only_with_the_policy_timeout() -> None:
    connection = FakeConnection(columns=["id"], rows=[(1,)])

    _executor(connection).execute_read_only_query(
        "SELECT id FROM customers",
        QueryExecutionPolicy(statement_timeout_seconds=7),
    )

    assert connection.statements[0] == "SET TRANSACTION READ ONLY"
    assert connection.statements[1] == "SET LOCAL statement_timeout = 7000"
    assert connection.statements[2] == "SELECT id FROM customers"


def test_successful_query_maps_rows_onto_column_names() -> None:
    connection = FakeConnection(columns=["id", "name"], rows=[(1, "Anh"), (2, "Binh")])

    result = _executor(connection).execute_read_only_query(
        "SELECT id, name FROM customers",
        QueryExecutionPolicy(),
    )

    assert result.columns == ["id", "name"]
    assert result.rows == [{"id": 1, "name": "Anh"}, {"id": 2, "name": "Binh"}]
    assert result.row_count == 2
    assert result.has_more_rows is False
    assert result.elapsed_ms is not None


def test_result_rows_are_capped_and_overflow_is_reported() -> None:
    connection = FakeConnection(columns=["id"], rows=[(index,) for index in range(10)])

    result = _executor(connection).execute_read_only_query(
        "SELECT id FROM customers",
        QueryExecutionPolicy(maximum_result_rows=3),
    )

    assert result.row_count == 3
    assert result.rows == [{"id": 0}, {"id": 1}, {"id": 2}]
    assert result.has_more_rows is True


def test_exactly_the_row_limit_does_not_report_more_rows() -> None:
    connection = FakeConnection(columns=["id"], rows=[(index,) for index in range(3)])

    result = _executor(connection).execute_read_only_query(
        "SELECT id FROM customers",
        QueryExecutionPolicy(maximum_result_rows=3),
    )

    assert result.row_count == 3
    assert result.has_more_rows is False


def test_write_policy_is_refused_before_any_connection_is_opened() -> None:
    connection = FakeConnection()

    with pytest.raises(UnsafeSqlError):
        _executor(connection).execute_read_only_query(
            "UPDATE customers SET name = 'x'",
            QueryExecutionPolicy(read_only_required=False),
        )

    assert connection.statements == []
    assert connection.closed is False


def test_statement_timeout_is_reported_as_a_timeout_error() -> None:
    connection = FakeConnection(raise_on_query=_query_canceled())

    with pytest.raises(QueryExecutionTimeoutError):
        _executor(connection).execute_read_only_query(
            "SELECT pg_sleep(60)",
            QueryExecutionPolicy(),
        )


def test_database_error_is_reported_as_an_execution_error() -> None:
    connection = FakeConnection(raise_on_query=psycopg.errors.UndefinedTable("no such table"))

    with pytest.raises(QueryExecutionError):
        _executor(connection).execute_read_only_query(
            "SELECT id FROM missing",
            QueryExecutionPolicy(),
        )


def test_connection_is_rolled_back_and_closed_after_success() -> None:
    connection = FakeConnection(columns=["id"], rows=[(1,)])

    _executor(connection).execute_read_only_query(
        "SELECT id FROM customers",
        QueryExecutionPolicy(),
    )

    assert connection.rolled_back is True
    assert connection.closed is True


def test_connection_is_rolled_back_and_closed_after_failure() -> None:
    connection = FakeConnection(raise_on_query=psycopg.errors.UndefinedTable("boom"))

    with pytest.raises(QueryExecutionError):
        _executor(connection).execute_read_only_query("SELECT 1", QueryExecutionPolicy())

    assert connection.rolled_back is True
    assert connection.closed is True


def test_explain_plans_without_executing_the_statement() -> None:
    connection = FakeConnection(columns=["QUERY PLAN"], rows=[("Seq Scan on customers",)])

    result = _executor(connection).explain_query("SELECT id FROM customers", QueryExecutionPolicy())

    assert connection.statements[-1] == "EXPLAIN SELECT id FROM customers"
    assert "ANALYZE" not in connection.statements[-1]
    assert result.plan_text == "Seq Scan on customers"


def test_explain_failure_is_reported_as_an_explain_error() -> None:
    connection = FakeConnection(raise_on_query=psycopg.errors.SyntaxError("bad syntax"))

    with pytest.raises(SqlExplainError):
        _executor(connection).explain_query("SELECT FROM", QueryExecutionPolicy())


def test_explain_timeout_is_reported_as_a_timeout_error() -> None:
    connection = FakeConnection(raise_on_query=_query_canceled())

    with pytest.raises(QueryExecutionTimeoutError):
        _executor(connection).explain_query("SELECT pg_sleep(60)", QueryExecutionPolicy())
