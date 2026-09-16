"""PostgreSQL readiness inspection."""

from typing import Any

import psycopg
from psycopg import sql as postgres_sql

from t2s.database.database_readiness import (
    DatabaseReadinessReport,
    DatabaseReadinessStatus,
)

# System namespaces hold catalog metadata, not queryable business data.
_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


class PostgresDatabaseReadinessInspector:
    """Checks a PostgreSQL database for user relations that actually hold rows."""

    def __init__(self, database_url: str, connect_timeout_seconds: int = 10) -> None:
        self.database_url = database_url
        self.connect_timeout_seconds = connect_timeout_seconds

    def inspect_readiness(self, max_relations_to_sample: int = 25) -> DatabaseReadinessReport:
        """Sample relations until one is found to be non-empty."""
        connection: psycopg.Connection[Any] | None = None
        try:
            connection = psycopg.connect(
                self.database_url,
                autocommit=False,
                connect_timeout=self.connect_timeout_seconds,
            )
            cursor = connection.cursor()
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type IN ('BASE TABLE', 'VIEW') "
                "AND table_schema <> ALL(%s) ORDER BY table_schema, table_name",
                (list(_SYSTEM_SCHEMAS),),
            )
            relations = [(str(row[0]), str(row[1])) for row in cursor.fetchall()]
            if not relations:
                return DatabaseReadinessReport(
                    status=DatabaseReadinessStatus.NO_USER_RELATIONS,
                    detail="Database exposes no user relations.",
                )
            inspected = relations[:max_relations_to_sample]
            non_empty_count = 0
            for schema_name, relation_name in inspected:
                cursor.execute(
                    postgres_sql.SQL("SELECT 1 FROM {}.{} LIMIT 1").format(
                        postgres_sql.Identifier(schema_name),
                        postgres_sql.Identifier(relation_name),
                    )
                )
                if cursor.fetchone() is not None:
                    non_empty_count += 1
                    break
            status = (
                DatabaseReadinessStatus.READY
                if non_empty_count > 0
                else DatabaseReadinessStatus.NO_DATA_ROWS
            )
            return DatabaseReadinessReport(
                status=status,
                relation_count=len(relations),
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
        except psycopg.Error as exc:
            return DatabaseReadinessReport(
                status=DatabaseReadinessStatus.UNREACHABLE,
                detail=f"Database could not be inspected: {type(exc).__name__}",
            )
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                finally:
                    connection.close()
