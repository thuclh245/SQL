"""SQLite readiness inspection."""

import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from t2s.database.database_readiness import (
    DatabaseReadinessReport,
    DatabaseReadinessStatus,
)


class SqliteDatabaseReadinessInspector:
    """Checks a SQLite file for user relations that actually hold rows."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def inspect_readiness(self, max_relations_to_sample: int = 25) -> DatabaseReadinessReport:
        """Sample relations until one is found to be non-empty."""
        if not self.database_path.exists():
            return DatabaseReadinessReport(
                status=DatabaseReadinessStatus.UNREACHABLE,
                detail=f"Database file does not exist: {self.database_path}",
            )
        try:
            with closing(self._connect_read_only()) as connection:
                relation_names = self._read_user_relation_names(connection)
                if not relation_names:
                    return DatabaseReadinessReport(
                        status=DatabaseReadinessStatus.NO_USER_RELATIONS,
                        detail="Database exposes no user relations.",
                    )
                inspected = relation_names[:max_relations_to_sample]
                non_empty_count = 0
                for relation_name in inspected:
                    if self._has_any_row(connection, relation_name):
                        non_empty_count += 1
                        # One populated relation is enough to clear the check.
                        break
                status = (
                    DatabaseReadinessStatus.READY
                    if non_empty_count > 0
                    else DatabaseReadinessStatus.NO_DATA_ROWS
                )
                return DatabaseReadinessReport(
                    status=status,
                    relation_count=len(relation_names),
                    inspected_relation_count=len(inspected),
                    non_empty_relation_count=non_empty_count,
                    detail=(
                        None
                        if non_empty_count > 0
                        else (
                            f"All {len(inspected)} inspected relations are empty, which "
                            "indicates a schema-only database rather than an execution database."
                        )
                    ),
                )
        except sqlite3.DatabaseError as exc:
            return DatabaseReadinessReport(
                status=DatabaseReadinessStatus.UNREACHABLE,
                detail=f"Database could not be opened as SQLite: {type(exc).__name__}",
            )

    def _connect_read_only(self) -> sqlite3.Connection:
        database_uri = f"file:{quote(str(self.database_path), safe='/')}?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _read_user_relation_names(self, connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def _has_any_row(self, connection: sqlite3.Connection, relation_name: str) -> bool:
        """LIMIT 1 rather than COUNT(*), so the check stays cheap on a large table."""
        escaped_name = relation_name.replace('"', '""')
        row = connection.execute(f'SELECT 1 FROM "{escaped_name}" LIMIT 1').fetchone()  # noqa: S608 - identifier is quoted catalog metadata
        return row is not None
