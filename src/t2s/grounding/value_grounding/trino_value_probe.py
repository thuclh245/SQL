"""Trino adapter for bounded, read-only value probing.

Unlike the PostgreSQL adapter, terms cannot be bound as wire parameters: the Trino
client protocol has none, and its official drivers render parameters into statement
text themselves. Terms are therefore rendered through
:func:`format_trino_string_literal`, which is the only place a caller-supplied
string enters a statement, and identifiers come from the catalog and are quoted.

Each probe carries its own time budget and row cap, so a high-cardinality column
on a large lakehouse table cannot stall grounding.
"""

import time

from t2s.database.trino_rest_client import (
    TrinoClientError,
    TrinoRestClient,
    build_session_properties,
    format_trino_identifier,
    format_trino_string_literal,
)
from t2s.grounding.value_grounding.value_grounding_contracts import (
    ValueProbeOutcome,
    ValueProbeRequest,
)

# Below one second Trino's own budget rounds badly; probes get at least this much.
_MINIMUM_SESSION_TIMEOUT_SECONDS = 1


class TrinoValueProbe:
    """Reads candidate literals from a Trino catalog under a per-probe budget."""

    def __init__(self, client: TrinoRestClient) -> None:
        self.client = client

    def probe_matching_values(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return stored literals equal to any supplied match term."""
        if not probe_request.match_terms:
            return ValueProbeOutcome(column=probe_request.column)

        column_identifier = format_trino_identifier(probe_request.column.column_name)
        table_identifier = format_trino_identifier(probe_request.column.sql_identifier)
        term_list = ", ".join(
            format_trino_string_literal(term) for term in probe_request.match_terms
        )
        statement = (
            f"SELECT DISTINCT {column_identifier} FROM {table_identifier} "
            f"WHERE {column_identifier} IS NOT NULL "
            f"AND CAST({column_identifier} AS VARCHAR) IN ({term_list}) "
            f"LIMIT {probe_request.max_values}"
        )
        return self._execute(probe_request, statement, probe_request.max_values)

    def probe_column_domain(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return a capped slice of the column's distinct values."""
        column_identifier = format_trino_identifier(probe_request.column.column_name)
        table_identifier = format_trino_identifier(probe_request.column.sql_identifier)
        statement = (
            f"SELECT DISTINCT {column_identifier} FROM {table_identifier} "
            f"WHERE {column_identifier} IS NOT NULL "
            f"LIMIT {probe_request.max_values + 1}"
        )
        return self._execute(probe_request, statement, probe_request.max_values)

    def _execute(
        self,
        probe_request: ValueProbeRequest,
        statement: str,
        max_values: int,
    ) -> ValueProbeOutcome:
        started_at = time.monotonic()
        timeout_seconds = max(
            _MINIMUM_SESSION_TIMEOUT_SECONDS,
            int(round(probe_request.timeout_ms / 1000)),
        )
        try:
            outcome = self.client.run(
                statement,
                session_properties=build_session_properties(timeout_seconds),
                max_rows=max_values + 1,
                deadline_seconds=timeout_seconds + 1,
            )
        except (TrinoClientError, ValueError) as exc:
            return ValueProbeOutcome(
                column=probe_request.column,
                elapsed_ms=self._elapsed_ms(started_at),
                error_message=f"Trino value probe failed: {type(exc).__name__}",
            )

        observed = [
            str(row[0])
            for row in outcome.rows
            if row and row[0] is not None
        ]
        return ValueProbeOutcome(
            column=probe_request.column,
            observed_values=observed[:max_values],
            domain_truncated=len(observed) > max_values,
            probe_count=1,
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _elapsed_ms(self, started_at: float) -> float:
        return (time.monotonic() - started_at) * 1000
