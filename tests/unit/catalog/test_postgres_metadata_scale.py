"""Scale and bounded query verification for PostgresMetadataProvider."""

import time
from typing import Any

from t2s.catalog.postgres_metadata_provider import PostgresMetadataProvider


class ScaleTrackingCursor:
    def __init__(self, connection: "ScaleTrackingConnection") -> None:
        self.connection = connection
        self.current_rows: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.connection.query_count += 1
        self.connection.statements.append(query.strip())
        q_lower = query.lower()
        if "from pg_class" in q_lower:
            self.current_rows = self.connection.relations_rows
        elif "from pg_attribute" in q_lower:
            self.current_rows = self.connection.columns_rows
        elif "con.contype = 'p'" in q_lower:
            self.current_rows = self.connection.pks_rows
        elif "con.contype = 'f'" in q_lower:
            self.current_rows = self.connection.fks_rows
        else:
            self.current_rows = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.current_rows


class ScaleTrackingConnection:
    def __init__(
        self,
        relations_rows: list[tuple[Any, ...]],
        columns_rows: list[tuple[Any, ...]],
        pks_rows: list[tuple[Any, ...]],
        fks_rows: list[tuple[Any, ...]],
    ) -> None:
        self.relations_rows = relations_rows
        self.columns_rows = columns_rows
        self.pks_rows = pks_rows
        self.fks_rows = fks_rows
        self.query_count = 0
        self.statements: list[str] = []

    def cursor(self) -> ScaleTrackingCursor:
        return ScaleTrackingCursor(self)

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_scale_query_count_bounded_at_9000_tables() -> None:
    """Prove strictly bounded SQL query count (N=4 metadata queries) at 9,000 tables."""
    num_tables = 9000

    relations = [
        ("scale_db", "analytics", f"table_{i}", "r", f"Table description {i}")
        for i in range(num_tables)
    ]
    # Each table has 3 columns: id, name, created_at
    columns: list[tuple[str, str, str, int, str, str, bool, str | None]] = []
    pks = []
    fks = []
    for i in range(num_tables):
        t_name = f"table_{i}"
        columns.append(("analytics", t_name, "id", 1, "bigint", "int8", False, "Primary ID"))
        columns.append(("analytics", t_name, "name", 2, "text", "text", True, "Entity name"))
        columns.append(
            ("analytics", t_name, "created_at", 3, "timestamp", "timestamp", False, None)
        )
        pks.append(("analytics", t_name, f"pk_{t_name}", "id", 1))

    # Add 100 foreign keys across tables
    for i in range(1, 101):
        fks.append(
            (
                f"fk_table_{i}",
                "analytics",
                f"table_{i}",
                "id",
                "analytics",
                f"table_{i - 1}",
                "id",
                1,
            )
        )

    conn = ScaleTrackingConnection(
        relations_rows=relations,
        columns_rows=columns,
        pks_rows=pks,
        fks_rows=fks,
    )
    provider = PostgresMetadataProvider(
        service_name="scale_service",
        database_name="scale_db",
        connection_factory=lambda: conn,
    )

    started = time.monotonic()
    catalog_tables = provider.fetch_metadata()
    elapsed = time.monotonic() - started

    # Assert bounded query count:
    # 2 session config statements (SET TRANSACTION READ ONLY, SET LOCAL statement_timeout)
    # + exactly 4 metadata queries (SQL_RELATIONS, SQL_COLUMNS, SQL_PRIMARY_KEYS, SQL_FOREIGN_KEYS)
    metadata_queries = [s for s in conn.statements if not s.startswith("SET ")]
    assert len(metadata_queries) == 4, (
        "Expected strictly 4 metadata queries regardless of table count, "
        f"got {len(metadata_queries)}: {metadata_queries}"
    )

    assert len(catalog_tables) == 9000
    # Assert linear assembly performance (in-memory assembly under 2.0s for 9k tables)
    assert elapsed < 2.0, f"Assembly took too long: {elapsed:.2f}s"
