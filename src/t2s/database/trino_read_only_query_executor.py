"""Read-only Trino query executor for the telecom lakehouse.

Trino has no read-only transaction to sit behind, so the guarantee is layered
differently from PostgreSQL: the engine's file-based access control grants the
application's Trino user ``SELECT`` only, this executor refuses to run unless the
policy demands read-only, and every statement is bounded by both a server-side
``query_max_execution_time`` and a client-side deadline that cancels the query.
"""

import time
from typing import Any

from t2s.database.query_execution_policy import QueryExecutionPolicy
from t2s.database.query_execution_result import QueryExecutionResult
from t2s.database.query_explain_result import QueryExplainResult
from t2s.database.trino_rest_client import (
    TrinoClientError,
    TrinoRestClient,
    TrinoStatementError,
    TrinoTimeoutError,
    build_session_properties,
)
from t2s.errors import (
    QueryExecutionError,
    QueryExecutionTimeoutError,
    SqlExplainError,
    UnsafeSqlError,
)

# Trino error names that mean "the query ran out of its budget", not "the query is wrong".
_TIMEOUT_ERROR_NAMES = frozenset(
    {
        "EXCEEDED_TIME_LIMIT",
        "EXCEEDED_CPU_LIMIT",
        "ABANDONED_QUERY",
        "QUERY_EXPIRED",
    }
)

# Headroom so the client deadline fires only after Trino has had its full budget.
_CLIENT_DEADLINE_GRACE_SECONDS = 5.0


class TrinoReadOnlyQueryExecutor:
    """Executes validated SELECT statements against Trino, read-only.

    Synchronous on purpose: it satisfies ``QueryExecutorPort`` and is called from the
    async runtime through ``asyncio.to_thread``, so its blocking HTTP polling never
    runs on the event loop.
    """

    def __init__(
        self,
        client: TrinoRestClient,
    ) -> None:
        self.client = client

    def explain_query(self, sql: str, execution_policy: QueryExecutionPolicy) -> QueryExplainResult:
        started_at = time.monotonic()
        try:
            outcome = self.client.run(
                f"EXPLAIN {sql}",
                session_properties=build_session_properties(
                    execution_policy.statement_timeout_seconds
                ),
                deadline_seconds=self._client_deadline(execution_policy),
            )
        except TrinoTimeoutError as exc:
            raise QueryExecutionTimeoutError(
                "Trino query explain exceeded its time budget."
            ) from exc
        except TrinoStatementError as exc:
            if exc.error_name in _TIMEOUT_ERROR_NAMES:
                raise QueryExecutionTimeoutError(
                    "Trino query explain exceeded its time budget."
                ) from exc
            raise SqlExplainError("Trino query explain failed.") from exc
        except TrinoClientError as exc:
            raise SqlExplainError("Trino query explain failed.") from exc

        return QueryExplainResult(
            plan_text="\n".join(
                " | ".join("" if value is None else str(value) for value in row)
                for row in outcome.rows
            ),
            elapsed_ms=int((time.monotonic() - started_at) * 1000),
        )

    def execute_read_only_query(
        self,
        sql: str,
        execution_policy: QueryExecutionPolicy,
    ) -> QueryExecutionResult:
        if not execution_policy.read_only_required:
            raise UnsafeSqlError("Trino executor only supports read-only execution.")

        started_at = time.monotonic()
        try:
            outcome = self.client.run(
                sql,
                session_properties=build_session_properties(
                    execution_policy.statement_timeout_seconds
                ),
                max_rows=execution_policy.maximum_result_rows,
                deadline_seconds=self._client_deadline(execution_policy),
            )
        except TrinoTimeoutError as exc:
            raise QueryExecutionTimeoutError("Trino query exceeded its time budget.") from exc
        except TrinoStatementError as exc:
            if exc.error_name in _TIMEOUT_ERROR_NAMES:
                raise QueryExecutionTimeoutError("Trino query exceeded its time budget.") from exc
            raise QueryExecutionError("Trino query execution failed.") from exc
        except TrinoClientError as exc:
            raise QueryExecutionError("Trino query execution failed.") from exc

        column_names = self._deduplicate_column_names(outcome.columns)
        return QueryExecutionResult(
            columns=column_names,
            rows=[self._to_row_mapping(column_names, row) for row in outcome.rows],
            row_count=len(outcome.rows),
            has_more_rows=outcome.truncated,
            elapsed_ms=int((time.monotonic() - started_at) * 1000),
        )

    def _client_deadline(self, execution_policy: QueryExecutionPolicy) -> float:
        return execution_policy.statement_timeout_seconds + _CLIENT_DEADLINE_GRACE_SECONDS

    def _deduplicate_column_names(self, column_names: list[str]) -> list[str]:
        """Trino allows a result to repeat a column name; a row mapping cannot.

        Repeats are suffixed rather than dropped, so no value silently disappears
        from a result the user is looking at.
        """
        seen: dict[str, int] = {}
        unique_names: list[str] = []
        for name in column_names:
            if name not in seen:
                seen[name] = 1
                unique_names.append(name)
                continue
            seen[name] += 1
            unique_names.append(f"{name}_{seen[name]}")
        return unique_names

    def _to_row_mapping(self, column_names: list[str], row: list[Any]) -> dict[str, Any]:
        return dict(zip(column_names, row, strict=True))
