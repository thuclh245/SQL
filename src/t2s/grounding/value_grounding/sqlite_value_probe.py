"""SQLite adapter for bounded, read-only value probing."""

import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from t2s.grounding.value_grounding.value_grounding_contracts import (
    ValueProbeOutcome,
    ValueProbeRequest,
)

# SQLite has no server-side statement timeout; the progress handler is checked
# every N virtual-machine instructions and aborts the statement instead.
_PROGRESS_HANDLER_INSTRUCTIONS = 1000


def quote_sqlite_identifier(identifier: str) -> str:
    """Quote a dotted catalog identifier, escaping embedded quotes.

    Identifiers reach this function from the catalog, never from user input, but
    they are quoted regardless so that unusual names cannot alter the statement.
    """
    return ".".join(f'"{part.replace(chr(34), chr(34) * 2)}"' for part in identifier.split("."))


class SqliteValueProbe:
    """Reads candidate literals from a SQLite database opened read-only."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def probe_matching_values(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return stored literals equal to any supplied match term."""
        if not probe_request.match_terms:
            return ValueProbeOutcome(column=probe_request.column)

        quoted_column = quote_sqlite_identifier(probe_request.column.column_name)
        quoted_table = quote_sqlite_identifier(probe_request.column.sql_identifier)
        placeholders = ", ".join("?" for _ in probe_request.match_terms)
        statement = (
            f"SELECT DISTINCT {quoted_column} FROM {quoted_table} "  # noqa: S608 - identifiers are quoted catalog values
            f"WHERE {quoted_column} IS NOT NULL AND {quoted_column} IN ({placeholders}) "
            f"LIMIT ?"
        )
        parameters = (*probe_request.match_terms, probe_request.max_values)
        return self._execute(probe_request, statement, parameters, probe_request.max_values)

    def probe_column_domain(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome:
        """Return a capped slice of the column's distinct values."""
        quoted_column = quote_sqlite_identifier(probe_request.column.column_name)
        quoted_table = quote_sqlite_identifier(probe_request.column.sql_identifier)
        statement = (
            f"SELECT DISTINCT {quoted_column} FROM {quoted_table} "  # noqa: S608 - identifiers are quoted catalog values
            f"WHERE {quoted_column} IS NOT NULL LIMIT ?"
        )
        # One extra row distinguishes "this is the whole domain" from "there is more".
        return self._execute(
            probe_request,
            statement,
            (probe_request.max_values + 1,),
            probe_request.max_values,
        )

    def _execute(
        self,
        probe_request: ValueProbeRequest,
        statement: str,
        parameters: tuple[object, ...],
        max_values: int,
    ) -> ValueProbeOutcome:
        started_at = time.monotonic()
        try:
            with closing(self._connect_read_only(probe_request)) as connection:
                rows = connection.execute(statement, parameters).fetchall()
        except sqlite3.DatabaseError as exc:
            return ValueProbeOutcome(
                column=probe_request.column,
                probe_count=1,
                elapsed_ms=self._elapsed_ms(started_at),
                # Type only: a SQLite message can echo the offending literal.
                error_message=type(exc).__name__,
            )
        observed_values = [str(row[0]) for row in rows if row[0] is not None]
        return ValueProbeOutcome(
            column=probe_request.column,
            observed_values=observed_values[:max_values],
            domain_truncated=len(observed_values) > max_values,
            probe_count=1,
            elapsed_ms=self._elapsed_ms(started_at),
        )

    def _connect_read_only(self, probe_request: ValueProbeRequest) -> sqlite3.Connection:
        database_uri = f"file:{quote(str(self.database_path), safe='/')}?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        connection.set_progress_handler(
            self._build_timeout_progress_handler(time.monotonic(), probe_request.timeout_ms),
            _PROGRESS_HANDLER_INSTRUCTIONS,
        )
        return connection

    def _build_timeout_progress_handler(
        self, started_at: float, timeout_ms: int
    ) -> Callable[[], int]:
        def abort_on_timeout() -> int:
            return int((time.monotonic() - started_at) * 1000 > timeout_ms)

        return abort_on_timeout

    def _elapsed_ms(self, started_at: float) -> float:
        return round((time.monotonic() - started_at) * 1000, 3)
