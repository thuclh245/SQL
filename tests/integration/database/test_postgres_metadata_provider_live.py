"""Optional live integration test for PostgresMetadataProvider against local PostgreSQL."""

import os

import pytest

from t2s.catalog.postgres_metadata_provider import PostgresMetadataProvider

LIVE_PG_URL = os.getenv("TEST_POSTGRES_DATABASE_URL")


@pytest.mark.skipif(
    not LIVE_PG_URL, reason="TEST_POSTGRES_DATABASE_URL environment variable not set"
)
def test_live_postgres_metadata_introspection() -> None:
    assert LIVE_PG_URL is not None
    provider = PostgresMetadataProvider(
        database_url=LIVE_PG_URL,
        service_name="live_test",
    )
    tables = provider.fetch_metadata()
    assert isinstance(tables, list)
    for table in tables:
        assert table.table_fqn.startswith("live_test.")
        assert len(table.columns) > 0
