"""Unit tests for PostgresMetadataProvider using simulated PostgreSQL catalogs."""

from typing import Any

import pytest

from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.postgres_metadata_provider import (
    PostgresMetadataProvider,
    normalize_postgres_data_type,
)
from t2s.errors.application_errors import ConfigurationError, MetadataCatalogError


class FakePostgresCursor:
    def __init__(self, connection: "FakePostgresConnection") -> None:
        self.connection = connection
        self.current_rows: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.connection.executed_statements.append(query.strip())
        if self.connection.raise_on_query is not None and not query.strip().startswith("SET "):
            raise self.connection.raise_on_query

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
        return list(self.current_rows)


class FakePostgresConnection:
    def __init__(
        self,
        relations_rows: list[tuple[Any, ...]] | None = None,
        columns_rows: list[tuple[Any, ...]] | None = None,
        pks_rows: list[tuple[Any, ...]] | None = None,
        fks_rows: list[tuple[Any, ...]] | None = None,
        raise_on_query: Exception | None = None,
    ) -> None:
        self.relations_rows = relations_rows or []
        self.columns_rows = columns_rows or []
        self.pks_rows = pks_rows or []
        self.fks_rows = fks_rows or []
        self.raise_on_query = raise_on_query
        self.executed_statements: list[str] = []
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakePostgresCursor:
        return FakePostgresCursor(self)

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_type_normalizer_fidelity() -> None:
    assert normalize_postgres_data_type("numeric(18,4)", "numeric") == "DECIMAL"
    assert normalize_postgres_data_type("character varying(255)", "varchar") == "VARCHAR"
    assert normalize_postgres_data_type("timestamp with time zone", "timestamptz") == "TIMESTAMP"
    assert normalize_postgres_data_type("integer[]", "_int4") == "ARRAY"
    assert (
        normalize_postgres_data_type("custom_enum_type", "custom_enum_type") == "CUSTOM_ENUM_TYPE"
    )


def test_postgres_provider_multi_schema_and_asset_types() -> None:
    # 3 tables: regular in core, view in analytics, materialized view in analytics
    relations = [
        ("shop_db", "core", "orders", "r", "Customer purchase orders"),
        ("shop_db", "analytics", "daily_metrics", "v", "Daily aggregated sales"),
        ("shop_db", "analytics", "product_sales_mv", "m", "Materialized product aggregates"),
    ]
    columns = [
        ("core", "orders", "order_id", 1, "bigint", "int8", False, "Order primary key"),
        ("core", "orders", "amount", 2, "numeric(10,2)", "numeric", False, "Order monetary amount"),
        ("analytics", "daily_metrics", "metric_date", 1, "date", "date", True, "Aggregation date"),
        ("analytics", "product_sales_mv", "product_id", 1, "integer", "int4", False, "Product ID"),
    ]
    pks = [
        ("core", "orders", "orders_pkey", "order_id", 1),
    ]
    fks: list[tuple[Any, ...]] = []

    conn = FakePostgresConnection(
        relations_rows=relations,
        columns_rows=columns,
        pks_rows=pks,
        fks_rows=fks,
    )
    provider = PostgresMetadataProvider(
        service_name="shop_service",
        database_name="shop_db",
        connection_factory=lambda: conn,
    )

    tables = provider.fetch_metadata()

    assert len(tables) == 3
    # alphabetical: analytics.daily_metrics, analytics.product_sales_mv, core.orders
    t_daily, t_mv, t_orders = tables

    # Assert relations
    assert t_daily.table_fqn == "shop_service.shop_db.analytics.daily_metrics"
    assert t_daily.table_type == "view"
    assert t_daily.description == "Daily aggregated sales"

    assert t_orders.table_fqn == "shop_service.shop_db.core.orders"
    assert t_orders.table_type == "table"
    assert t_orders.description == "Customer purchase orders"
    assert t_orders.primary_key_column_names == ["order_id"]
    assert len(t_orders.columns) == 2
    assert t_orders.columns[0].column_name == "order_id"
    assert t_orders.columns[0].native_type == "bigint"
    assert t_orders.columns[0].data_type == "BIGINT"
    assert t_orders.columns[0].is_nullable is False
    assert t_orders.columns[0].is_primary_key is True

    assert t_mv.table_fqn == "shop_service.shop_db.analytics.product_sales_mv"
    assert t_mv.table_type == "materialized_view"

    # Verify read-only guarantees
    assert conn.rolled_back is True
    assert conn.closed is True
    assert any("SET TRANSACTION READ ONLY" in s for s in conn.executed_statements)


def test_postgres_provider_composite_pk_and_composite_fk() -> None:
    relations = [
        ("shop_db", "sales", "order_items", "r", "Order line items"),
        ("shop_db", "sales", "orders", "r", "Parent orders"),
    ]
    columns = [
        ("sales", "order_items", "order_id", 1, "text", "text", False, None),
        ("sales", "order_items", "item_seq", 2, "integer", "int4", False, None),
        ("sales", "order_items", "product_code", 3, "text", "text", False, None),
        ("sales", "orders", "order_id", 1, "text", "text", False, None),
        ("sales", "orders", "customer_id", 2, "text", "text", False, None),
    ]
    # Composite PK on order_items (order_id, item_seq)
    pks = [
        ("sales", "order_items", "order_items_pk", "order_id", 1),
        ("sales", "order_items", "order_items_pk", "item_seq", 2),
        ("sales", "orders", "orders_pk", "order_id", 1),
    ]
    # FK from order_items(order_id) -> orders(order_id)
    fks = [
        ("fk_items_orders", "sales", "order_items", "order_id", "sales", "orders", "order_id", 1),
    ]

    conn = FakePostgresConnection(
        relations_rows=relations,
        columns_rows=columns,
        pks_rows=pks,
        fks_rows=fks,
    )
    provider = PostgresMetadataProvider(
        service_name="shop",
        database_name="shop_db",
        connection_factory=lambda: conn,
    )

    tables = provider.fetch_metadata()
    order_items_table = next(t for t in tables if t.table_name == "order_items")

    assert order_items_table.primary_key_column_names == ["order_id", "item_seq"]
    assert len(order_items_table.foreign_keys) == 1
    fk = order_items_table.foreign_keys[0]
    assert fk.relationship_name == "fk_items_orders"
    assert fk.from_column_names == ["order_id"]
    assert fk.to_column_names == ["order_id"]
    assert fk.to_table_fqn == "shop.shop_db.sales.orders"


def test_postgres_provider_cross_schema_fk() -> None:
    relations = [
        ("shop_db", "inventory", "stock", "r", None),
        ("shop_db", "catalog", "products", "r", None),
    ]
    columns = [
        ("inventory", "stock", "product_sku", 1, "text", "text", False, None),
        ("inventory", "stock", "warehouse_id", 2, "text", "text", False, None),
        ("catalog", "products", "sku", 1, "text", "text", False, None),
    ]
    pks = [
        ("inventory", "stock", "stock_pk", "product_sku", 1),
        ("catalog", "products", "products_pk", "sku", 1),
    ]
    fks = [
        ("fk_stock_product", "inventory", "stock", "product_sku", "catalog", "products", "sku", 1),
    ]

    conn = FakePostgresConnection(
        relations_rows=relations,
        columns_rows=columns,
        pks_rows=pks,
        fks_rows=fks,
    )
    provider = PostgresMetadataProvider(
        service_name="shop",
        database_name="shop_db",
        connection_factory=lambda: conn,
    )

    tables = provider.fetch_metadata()
    stock_table = next(t for t in tables if t.table_name == "stock")
    assert len(stock_table.foreign_keys) == 1
    fk = stock_table.foreign_keys[0]
    assert fk.from_table_fqn == "shop.shop_db.inventory.stock"
    assert fk.to_table_fqn == "shop.shop_db.catalog.products"
    assert fk.from_column_names == ["product_sku"]
    assert fk.to_column_names == ["sku"]


def test_postgres_provider_semantic_hash_stability() -> None:
    relations = [("db", "sch", "t1", "r", "table comment")]
    columns = [("sch", "t1", "id", 1, "int4", "int4", False, "id comment")]
    pks = [("sch", "t1", "pk_t1", "id", 1)]

    provider = PostgresMetadataProvider(
        service_name="svc",
        database_name="db",
        connection_factory=lambda: FakePostgresConnection(relations, columns, pks, []),
    )

    tables_fetch_1 = provider.fetch_metadata()
    tables_fetch_2 = provider.fetch_metadata()

    assert len(tables_fetch_1) == 1
    assert len(tables_fetch_2) == 1
    hash1 = tables_fetch_1[0].semantic_content_hash
    hash2 = tables_fetch_2[0].semantic_content_hash
    assert hash1 == hash2


def test_postgres_provider_with_metadata_scope() -> None:
    relations = [
        ("db", "sales", "orders", "r", None),
        ("db", "sales", "customers", "r", None),
        ("db", "finance", "ledgers", "r", None),
    ]
    columns = [
        ("sales", "orders", "id", 1, "text", "text", False, None),
        ("sales", "customers", "id", 1, "text", "text", False, None),
        ("finance", "ledgers", "id", 1, "text", "text", False, None),
    ]
    conn = FakePostgresConnection(relations, columns, [], [])
    provider = PostgresMetadataProvider(
        service_name="svc",
        database_name="db",
        connection_factory=lambda: conn,
    )

    # Scope: only sales schema, and exclude customers
    scope = MetadataScope(
        schema_names={"sales"},
        exclude_tables={"customers"},
    )
    tables = provider.fetch_metadata(scope=scope)

    assert len(tables) == 1
    assert tables[0].table_name == "orders"


def test_postgres_provider_query_error_raises_metadata_catalog_error() -> None:
    conn = FakePostgresConnection(raise_on_query=RuntimeError("connection reset by peer"))
    provider = PostgresMetadataProvider(
        service_name="svc",
        database_name="db",
        connection_factory=lambda: conn,
    )
    with pytest.raises(MetadataCatalogError, match="PostgreSQL metadata fetch failed"):
        provider.fetch_metadata()
    assert conn.rolled_back is True
    assert conn.closed is True


def test_postgres_provider_missing_connection_params_raises_configuration_error() -> None:
    with pytest.raises(
        ConfigurationError, match="requires either 'database_url' or 'connection_factory'"
    ):
        PostgresMetadataProvider()
