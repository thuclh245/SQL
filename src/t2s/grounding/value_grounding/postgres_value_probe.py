"""PostgreSQL adapter for bounded, read-only value probing.

Each probe runs in its own READ ONLY transaction with a statement timeout, so a
slow or pathological column cannot hold a connection or mutate anything.
"""

import time
from typing import Any

import psycopg
from psycopg import sql as postgres_sql

from t2s.grounding.value_grounding.value_grounding_contracts import (
    ValueProbeOutcome,
    ValueProbeRequest,
)

PostgresConnection = psycopg.Connection[Any]


def build_postgres_identifier(identifier: str) -> postgres_sql.Composable:
    """Compose a dotted catalog identifier through psycopg's identifier quoting."""
    return postgres_sql.SQL(".").join(
        postgres_sql.Identifier(part) for part in identifier.split(".")
    )


class PostgresValueProbe:
    """Reads candidate literals from PostgreSQL inside a read-only transaction."""

    def __init__(
        self,
        database_url: str,
        connect_timeout_seconds: int = 10,
    ) -> None:
        self.database_url = database_url
        self.connect_timeout_seconds = connect_timeout_seconds

    def probe_matching_values(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return stored literals equal to any supplied match term."""
        if not probe_request.match_terms:
            return ValueProbeOutcome(column=probe_request.column)

        column_identifier = build_postgres_identifier(probe_request.column.column_name)
        table_identifier = build_postgres_identifier(probe_request.column.sql_identifier)
        statement = postgres_sql.SQL(
            "SELECT DISTINCT {column} FROM {table} "
            "WHERE {column} IS NOT NULL AND {column}::text = ANY(%s) LIMIT %s"
        ).format(column=column_identifier, table=table_identifier)
        parameters = (list(probe_request.match_terms), probe_request.max_values)
        return self._execute(probe_request, statement, parameters, probe_request.max_values)

    def probe_column_domain(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return a capped slice of the column's distinct values."""
        column_identifier = build_postgres_identifier(probe_request.column.column_name)
        table_identifier = build_postgres_identifier(probe_request.column.sql_identifier)
        statement = postgres_sql.SQL(
            "SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT %s"
        ).format(column=column_identifier, table=table_identifier)
        return self._execute(
            probe_request,
            statement,
            (probe_request.max_values + 1,),
            probe_request.max_values,
        )

    def _execute(
        self,
        probe_request: ValueProbeRequest,
        statement: postgres_sql.SQL | postgres_sql.Composed,
        parameters: tuple[object, ...],
        max_values: int,
    ) -> ValueProbeOutcome:
        started_at = time.monotonic()
        connection: PostgresConnection | None = None
        try:
            connection = psycopg.connect(
                self.database_url,
                autocommit=False,
                connect_timeout=self.connect_timeout_seconds,
            )
            cursor = connection.cursor()
            # Must be the transaction's first statement to take effect.
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                postgres_sql.SQL("SET LOCAL statement_timeout = {}").format(
                    postgres_sql.Literal(probe_request.timeout_ms)
                )
            )
            cursor.execute(statement, parameters)
            rows = cursor.fetchall()
        except psycopg.Error as exc:
            return ValueProbeOutcome(
                column=probe_request.column,
                probe_count=1,
                elapsed_ms=self._elapsed_ms(started_at),
                # Type only: a PostgreSQL message can echo the offending literal.
                error_message=type(exc).__name__,
            )
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                finally:
                    connection.close()

        observed_values = [str(row[0]) for row in rows if row[0] is not None]
        return ValueProbeOutcome(
            column=probe_request.column,
            observed_values=observed_values[:max_values],
            domain_truncated=len(observed_values) > max_values,
            probe_count=1,
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _elapsed_ms(self, started_at: float) -> float:
        return round((time.monotonic() - started_at) * 1000, 3)
