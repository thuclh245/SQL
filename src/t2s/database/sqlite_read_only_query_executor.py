import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from t2s.database.query_execution_policy import QueryExecutionPolicy
from t2s.database.query_execution_result import QueryExecutionResult
from t2s.database.query_explain_result import QueryExplainResult
from t2s.errors import (
    QueryExecutionError,
    QueryExecutionTimeoutError,
    SqlExplainError,
    UnsafeSqlError,
)


class SqliteReadOnlyQueryExecutor:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def explain_query(self, sql: str, execution_policy: QueryExecutionPolicy) -> QueryExplainResult:
        started_at = time.monotonic()
        try:
            with closing(self._connect_read_only(execution_policy)) as connection:
                rows = connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        except sqlite3.DatabaseError as exc:
            self._raise_timeout_when_interrupted(exc)
            raise SqlExplainError("SQLite query explain failed.") from exc
        return QueryExplainResult(
            plan_text="\n".join(" | ".join(str(value) for value in row) for row in rows),
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def execute_read_only_query(
        self,
        sql: str,
        execution_policy: QueryExecutionPolicy,
    ) -> QueryExecutionResult:
        if not execution_policy.read_only_required:
            raise UnsafeSqlError("SQLite executor only supports read-only execution.")

        started_at = time.monotonic()
        try:
            with closing(self._connect_read_only(execution_policy)) as connection:
                cursor = connection.execute(sql)
                column_names = [description[0] for description in cursor.description or []]
                fetched_rows = cursor.fetchmany(execution_policy.maximum_result_rows + 1)
        except sqlite3.DatabaseError as exc:
            self._raise_timeout_when_interrupted(exc)
            raise QueryExecutionError("SQLite query execution failed.") from exc

        visible_rows = fetched_rows[: execution_policy.maximum_result_rows]
        return QueryExecutionResult(
            columns=column_names,
            rows=[dict(zip(column_names, row, strict=True)) for row in visible_rows],
            row_count=len(visible_rows),
            has_more_rows=len(fetched_rows) > execution_policy.maximum_result_rows,
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _connect_read_only(self, execution_policy: QueryExecutionPolicy) -> sqlite3.Connection:
        database_uri = f"file:{quote(str(self.database_path), safe='/')}?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.set_progress_handler(
            self._build_timeout_progress_handler(time.monotonic(), execution_policy),
            1000,
        )
        return connection

    def _build_timeout_progress_handler(
        self,
        started_at: float,
        execution_policy: QueryExecutionPolicy,
    ) -> Callable[[], int]:
        def abort_on_timeout() -> int:
            elapsed_seconds = time.monotonic() - started_at
            return int(elapsed_seconds > execution_policy.statement_timeout_seconds)

        return abort_on_timeout

    def _raise_timeout_when_interrupted(self, exc: sqlite3.DatabaseError) -> None:
        if "interrupted" in str(exc).lower():
            raise QueryExecutionTimeoutError("SQLite query exceeded statement timeout.") from exc

    def _elapsed_ms(self, started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
