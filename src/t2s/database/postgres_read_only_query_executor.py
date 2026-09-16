"""Read-only PostgreSQL query executor.

Execution is confined by a READ ONLY transaction and a per-statement timeout, so a
bug in an earlier validation layer still cannot write through this executor. The
database account is expected to be read-only as well, as the outermost guard.
"""

import time
from collections.abc import Callable
from typing import Any

import psycopg
from psycopg import sql as postgres_sql

from t2s.database.query_execution_policy import QueryExecutionPolicy
from t2s.database.query_execution_result import QueryExecutionResult
from t2s.database.query_explain_result import QueryExplainResult
from t2s.errors import (
    QueryExecutionError,
    QueryExecutionTimeoutError,
    SqlExplainError,
    UnsafeSqlError,
)

PostgresConnection = psycopg.Connection[Any]
PostgresConnectionFactory = Callable[[], PostgresConnection]


class PostgresReadOnlyQueryExecutor:
    """Executes validated SELECT statements against PostgreSQL, read-only.

    This class is synchronous on purpose: it satisfies ``QueryExecutorPort`` and is
    called from the async runtime through ``asyncio.to_thread``, so its blocking
    socket I/O never runs on the event loop.
    """

    def __init__(
        self,
        database_url: str,
        connect_timeout_seconds: int = 10,
        connection_factory: PostgresConnectionFactory | None = None,
    ) -> None:
        self.database_url = database_url
        self.connect_timeout_seconds = connect_timeout_seconds
        self.connection_factory = connection_factory or self._connect

    def explain_query(self, sql: str, execution_policy: QueryExecutionPolicy) -> QueryExplainResult:
        started_at = time.monotonic()
        try:
            with self._read_only_transaction(execution_policy) as cursor:
                # Plain EXPLAIN plans the statement without running it; never ANALYZE.
                cursor.execute(f"EXPLAIN {sql}")
                plan_rows = cursor.fetchall()
        except psycopg.errors.QueryCanceled as exc:
            raise QueryExecutionTimeoutError(
                "PostgreSQL query explain exceeded statement timeout."
            ) from exc
        except psycopg.Error as exc:
            raise SqlExplainError("PostgreSQL query explain failed.") from exc

        return QueryExplainResult(
            plan_text="\n".join(" | ".join(str(value) for value in row) for row in plan_rows),
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def execute_read_only_query(
        self,
        sql: str,
        execution_policy: QueryExecutionPolicy,
    ) -> QueryExecutionResult:
        if not execution_policy.read_only_required:
            raise UnsafeSqlError("PostgreSQL executor only supports read-only execution.")

        started_at = time.monotonic()
        try:
            with self._read_only_transaction(execution_policy) as cursor:
                cursor.execute(sql)
                column_names = [description[0] for description in cursor.description or []]
                fetched_rows = cursor.fetchmany(execution_policy.maximum_result_rows + 1)
        except psycopg.errors.QueryCanceled as exc:
            raise QueryExecutionTimeoutError(
                "PostgreSQL query exceeded statement timeout."
            ) from exc
        except psycopg.Error as exc:
            raise QueryExecutionError("PostgreSQL query execution failed.") from exc

        visible_rows = fetched_rows[: execution_policy.maximum_result_rows]
        return QueryExecutionResult(
            columns=column_names,
            rows=[dict(zip(column_names, row, strict=True)) for row in visible_rows],
            row_count=len(visible_rows),
            has_more_rows=len(fetched_rows) > execution_policy.maximum_result_rows,
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _connect(self) -> PostgresConnection:
        return psycopg.connect(
            self.database_url,
            autocommit=False,
            connect_timeout=self.connect_timeout_seconds,
        )

    def _read_only_transaction(
        self,
        execution_policy: QueryExecutionPolicy,
    ) -> "_ReadOnlyTransaction":
        return _ReadOnlyTransaction(self.connection_factory, execution_policy)

    def _elapsed_ms(self, started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)


class _ReadOnlyTransaction:
    """Opens a READ ONLY, timeout-bounded transaction and always rolls it back."""

    def __init__(
        self,
        connection_factory: PostgresConnectionFactory,
        execution_policy: QueryExecutionPolicy,
    ) -> None:
        self.connection_factory = connection_factory
        self.execution_policy = execution_policy
        self.connection: PostgresConnection | None = None

    def __enter__(self) -> Any:
        connection = self.connection_factory()
        self.connection = connection
        try:
            cursor = connection.cursor()
            # Must be the first statement of the transaction to take effect.
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                postgres_sql.SQL("SET LOCAL statement_timeout = {}").format(
                    postgres_sql.Literal(self.execution_policy.statement_timeout_seconds * 1000)
                )
            )
        except BaseException:
            self._close()
            raise
        return cursor

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._close()

    def _close(self) -> None:
        connection = self.connection
        self.connection = None
        if connection is None:
            return
        try:
            connection.rollback()
        finally:
            connection.close()
