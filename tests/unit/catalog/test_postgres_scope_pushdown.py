"""Unit tests for PostgreSQL scope pushdown query generation and parameterization."""

from unittest.mock import MagicMock

from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.postgres_metadata_provider import (
    PostgresMetadataProvider,
    _build_pushdown_conditions,
)


def test_pushdown_conditions_none_scope() -> None:
    clause, params = _build_pushdown_conditions(None)
    assert clause == ""
    assert params == []


def test_pushdown_conditions_schema_names() -> None:
    scope = MetadataScope(schema_names={"sales", "marketing"})
    clause, params = _build_pushdown_conditions(
        scope, schema_col="n.nspname", table_col="c.relname"
    )
    assert "AND n.nspname = ANY(%s)" in clause
    assert len(params) == 1
    assert params[0] == ["marketing", "sales"]


def test_pushdown_conditions_exclude_schemas() -> None:
    scope = MetadataScope(exclude_schemas={"temp", "test"})
    clause, params = _build_pushdown_conditions(
        scope, schema_col="n.nspname", table_col="c.relname"
    )
    assert "AND n.nspname != ALL(%s)" in clause
    assert len(params) == 1
    assert params[0] == ["temp", "test"]


def test_pushdown_conditions_include_tables() -> None:
    scope = MetadataScope(include_tables={"orders", "order_items", "customers"})
    clause, params = _build_pushdown_conditions(
        scope, schema_col="n.nspname", table_col="c.relname"
    )
    assert "AND c.relname = ANY(%s)" in clause
    assert len(params) == 1
    assert params[0] == ["customers", "order_items", "orders"]


def test_pushdown_glob_patterns_omitted_from_exact_any() -> None:
    # Glob patterns should not be pushed down as exact equality; they are filtered in Python
    scope = MetadataScope(
        schema_names={"sales"},
        include_tables={"orders", "tmp_*", "test_?"},
    )
    clause, params = _build_pushdown_conditions(scope)
    assert "AND n.nspname = ANY(%s)" in clause
    assert "AND c.relname = ANY(%s)" in clause
    assert params[0] == ["sales"]
    assert params[1] == ["orders"]


def test_postgres_provider_passes_parameters_to_cursor() -> None:
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Setup empty return values for all 4 queries
    mock_cursor.fetchall.return_value = []

    provider = PostgresMetadataProvider(connection_factory=lambda: mock_conn)
    scope = MetadataScope(
        schema_names={"public"},
        include_tables={"orders"},
    )

    tables = provider.fetch_metadata(scope=scope)
    assert tables == []

    # 2 transaction setup queries + 4 bulk metadata queries = 6 total execute calls
    assert mock_cursor.execute.call_count == 6

    # Verify that the 4 bulk metadata queries received pushdown parameters
    metadata_calls = [
        call for call in mock_cursor.execute.call_args_list if call[0] and "ANY(%s)" in call[0][0]
    ]
    assert len(metadata_calls) == 4
    for call in metadata_calls:
        query_sql, query_params = call[0]
        assert "ANY(%s)" in query_sql
        assert ["public"] in query_params or ["orders"] in query_params
