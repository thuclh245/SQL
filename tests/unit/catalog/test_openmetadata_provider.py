"""Unit tests for OpenMetadataProvider and full Catalog Sync / LKG integration."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from t2s.catalog.canonical_metadata import (
    CatalogColumn,
    CatalogTable,
    MetadataProvenance,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.catalog.metadata_provider import MetadataProviderPort
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot
from t2s.catalog.metadata_snapshot_store import InMemoryMetadataSnapshotStore
from t2s.catalog.metadata_sync_result import SyncStatus
from t2s.catalog.metadata_sync_service import MetadataSyncService
from t2s.catalog.openmetadata_provider import OpenMetadataProvider
from t2s.errors import (
    MetadataCardinalityLimitExceededError,
    MetadataSyncError,
)
from t2s.integrations.openmetadata.openmetadata_client import OpenMetadataClient


def _make_om_raw_table(
    name: str,
    table_type: str = "Regular",
    schema_name: str = "sales",
    database_name: str = "analytics",
    service_name: str = "warehouse",
    columns: list[dict[str, Any]] | None = None,
    constraints: list[dict[str, Any]] | None = None,
    description: str | None = "Sales table description in **Markdown**",
    tags: list[dict[str, Any]] | None = None,
    owner: dict[str, Any] | None = None,
    domain: dict[str, Any] | None = None,
    version: float = 1.2,
    updated_at: int = 1690000000000,
) -> dict[str, Any]:
    fqn = f"{service_name}.{database_name}.{schema_name}.{name}"
    cols = columns or [
        {
            "name": "id",
            "dataType": "BIGINT",
            "dataTypeDisplay": "int8",
            "constraint": "PRIMARY_KEY",
            "isNullable": False,
            "description": "Primary key ID",
        },
        {
            "name": "status",
            "dataType": "VARCHAR",
            "dataTypeDisplay": "varchar(32)",
            "description": "Current status",
        },
    ]
    return {
        "id": f"uuid-{name}-12345",
        "name": name,
        "fullyQualifiedName": fqn,
        "tableType": table_type,
        "description": description,
        "service": {"name": service_name},
        "database": {"name": database_name},
        "databaseSchema": {"name": schema_name},
        "columns": cols,
        "tableConstraints": constraints or [],
        "tags": tags or [{"source": "Tag", "tagFQN": "Classification.Confidential"}],
        "owner": owner or {"name": "data-governance-team"},
        "domain": domain or {"name": "commercial"},
        "version": version,
        "updatedAt": updated_at,
    }


def test_openmetadata_provider_exact_pilot_fqn_acquisition() -> None:
    """Acquire exact 5 approved pilot tables by FQN directly."""
    tables_db = {
        f"warehouse.analytics.sales.t_{i}": _make_om_raw_table(f"t_{i}") for i in range(1, 6)
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # e.g. /api/v1/tables/name/warehouse.analytics.sales.t_1
        for fqn, raw_table in tables_db.items():
            if fqn in path:
                return httpx.Response(200, json=raw_table)
        return httpx.Response(404, json={"message": "Not found"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
        max_assets=10,
    )
    pilot_fqns = list(tables_db.keys())
    provider = OpenMetadataProvider(client=client, pilot_fqns=pilot_fqns)

    tables = provider.fetch_metadata()

    assert len(tables) == 5
    assert [t.table_name for t in tables] == ["t_1", "t_2", "t_3", "t_4", "t_5"]
    for t in tables:
        assert t.service_name == "warehouse"
        assert t.database_name == "analytics"
        assert t.schema_name == "sales"
        assert t.provenance is not None
        assert t.provenance.source_system == "openmetadata"
        assert t.provenance.source_version == "1.2"
        assert t.provenance.source_updated_at is not None


def test_openmetadata_provider_exact_pilot_partial_failure_aborts() -> None:
    """If 4 assets succeed and 1 returns 500, provider must fail closed (zero partial drops)."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        path = request.url.path
        if "t_5" in path:
            return httpx.Response(500, json={"error": "Database error on table t_5"})
        return httpx.Response(200, json=_make_om_raw_table("orders"))

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    provider = OpenMetadataProvider(
        client=client,
        pilot_fqns=[f"warehouse.analytics.sales.t_{i}" for i in range(1, 6)],
    )

    with pytest.raises(MetadataSyncError):
        provider.fetch_metadata()


def test_openmetadata_provider_cardinality_guard_enforced() -> None:
    """Provider fetch must fail closed if API returns more assets than max_assets."""
    raw_tables = [_make_om_raw_table(f"table_{i}") for i in range(1, 26)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": raw_tables})

    # max_assets set to 20; 25 returned -> must raise MetadataCardinalityLimitExceededError
    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        max_assets=20,
        transport=httpx.MockTransport(handler),
    )
    provider = OpenMetadataProvider(client=client)

    with pytest.raises(
        MetadataCardinalityLimitExceededError, match="exceeding configured safety limit"
    ):
        provider.fetch_metadata()


def test_openmetadata_provider_mapping_fidelity() -> None:
    """Verify detailed canonical mapping: table types, native types, PK/FK, Unicode, Markdown."""
    fk_constraint = {
        "name": "fk_orders_customer",
        "constraintType": "FOREIGN_KEY",
        "columns": ["customer_id"],
        "referredColumns": ["warehouse.analytics.crm.customers.id"],
    }
    raw_orders = _make_om_raw_table(
        name="orders",
        table_type="View",
        description="Orders view with **Markdown** and Unicode: Đơn hàng",
        columns=[
            {
                "name": "order_id",
                "dataType": "BIGINT",
                "dataTypeDisplay": "int8",
                "constraint": "PRIMARY_KEY",
                "isNullable": False,
            },
            {
                "name": "customer_id",
                "dataType": "BIGINT",
                "dataTypeDisplay": "int8",
                "isNullable": True,
            },
            {
                "name": "notes",
                "dataType": "TEXT",
                "dataTypeDisplay": "text",
                # isNullable absent -> should map to None (unknown)
            },
        ],
        constraints=[fk_constraint],
        tags=[
            {"source": "Tag", "tagFQN": "Tier.Gold"},
            {"source": "Glossary", "tagFQN": "Sales.Order"},
        ],
        owner={"name": "analytics-eng"},
        domain={"name": "ecommerce"},
        version=2.0,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [raw_orders]})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenMetadataProvider(client=client)
    tables = provider.fetch_metadata()

    assert len(tables) == 1
    t = tables[0]
    assert t.table_fqn == "warehouse.analytics.sales.orders"
    assert t.table_type == "view"
    assert t.description == "Orders view with **Markdown** and Unicode: Đơn hàng"
    assert t.primary_key_column_names == ["order_id"]
    assert t.owner == "analytics-eng"
    assert t.domain == "ecommerce"
    assert t.tags == ["Tier.Gold"]
    assert t.glossary_terms == ["Sales.Order"]

    # Columns
    assert len(t.columns) == 3
    col_order_id, col_cust_id, col_notes = t.columns
    assert col_order_id.is_nullable is False
    assert col_order_id.native_type == "int8"
    assert col_cust_id.is_nullable is True
    assert col_notes.is_nullable is None  # Unknown remains None!

    # Foreign Key
    assert len(t.foreign_keys) == 1
    fk = t.foreign_keys[0]
    assert fk.from_table_fqn == "warehouse.analytics.sales.orders"
    assert fk.from_column_names == ["customer_id"]
    assert fk.to_table_fqn == "warehouse.analytics.crm.customers"
    assert fk.to_column_names == ["id"]
    assert fk.to_service_name == "warehouse"
    assert fk.to_database_name == "analytics"
    assert fk.to_schema_name == "crm"
    assert fk.to_table_name == "customers"


def test_openmetadata_provider_unknown_table_type_safely_handled() -> None:
    raw = _make_om_raw_table(name="external_stream", table_type="FutureStreamingTableType")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [raw]})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenMetadataProvider(client=client)
    tables = provider.fetch_metadata()

    assert len(tables) == 1
    assert tables[0].table_type == "unknown"


def test_openmetadata_source_authority_transition_in_sync_service() -> None:
    """When a table supplied by postgresql is now supplied by openmetadata with same content,
    the sync service promotes a new active snapshot with source transitioned to openmetadata.
    """
    t_pg = CatalogTable(
        table_fqn="warehouse.analytics.sales.orders",
        service_name="warehouse",
        database_name="analytics",
        schema_name="sales",
        table_name="orders",
        table_type="table",
        columns=[
            CatalogColumn(
                column_fqn="warehouse.analytics.sales.orders.id",
                column_name="id",
                data_type="BIGINT",
            )
        ],
        provenance=MetadataProvenance(source_system="postgresql"),
    )

    store = InMemoryMetadataSnapshotStore()
    catalog = InMemoryCatalog()
    scope = MetadataScope(schema_names={"sales"})

    # Step 1: Initial sync with PostgreSQL
    pg_provider = MockProvider(source_sys="postgresql", tables=[t_pg])
    service_pg = MetadataSyncService(
        provider=pg_provider, snapshot_store=store, catalog_storage=catalog
    )
    res_pg = service_pg.sync(scope)
    assert res_pg.status == SyncStatus.SUCCESS
    snap_pg = store.get_active_snapshot()
    assert snap_pg is not None
    assert snap_pg.source_system == "postgresql"

    # Step 2: Sync with OpenMetadata provider returning equivalent table
    t_om = CatalogTable(
        table_fqn="warehouse.analytics.sales.orders",
        service_name="warehouse",
        database_name="analytics",
        schema_name="sales",
        table_name="orders",
        table_type="table",
        columns=[
            CatalogColumn(
                column_fqn="warehouse.analytics.sales.orders.id",
                column_name="id",
                data_type="BIGINT",
            )
        ],
        provenance=MetadataProvenance(source_system="openmetadata", source_version="1.0"),
    )
    om_provider = MockProvider(source_sys="openmetadata", tables=[t_om])
    service_om = MetadataSyncService(
        provider=om_provider, snapshot_store=store, catalog_storage=catalog
    )
    res_om = service_om.sync(scope)

    assert res_om.status == SyncStatus.SUCCESS
    snap_om = store.get_active_snapshot()
    assert snap_om is not None
    assert snap_om.source_system == "openmetadata"
    assert "Source authority transitioned from 'postgresql' to 'openmetadata'" in res_om.message


def test_openmetadata_pilot_mixed_source_preserves_postgresql_lkg() -> None:
    """In an incremental pilot: 2 OpenMetadata tables in 'sales' are ingested while 3 PostgreSQL
    tables in 'finance' are preserved unscoped. The resulting snapshot has is_mixed_source = True.
    """
    # Active PostgreSQL tables
    t_fin_1 = CatalogTable(
        table_fqn="warehouse.analytics.finance.invoices",
        service_name="warehouse",
        database_name="analytics",
        schema_name="finance",
        table_name="invoices",
        provenance=MetadataProvenance(source_system="postgresql"),
    )
    t_fin_2 = CatalogTable(
        table_fqn="warehouse.analytics.finance.payments",
        service_name="warehouse",
        database_name="analytics",
        schema_name="finance",
        table_name="payments",
        provenance=MetadataProvenance(source_system="postgresql"),
    )
    t_sales_old = CatalogTable(
        table_fqn="warehouse.analytics.sales.orders",
        service_name="warehouse",
        database_name="analytics",
        schema_name="sales",
        table_name="orders",
        provenance=MetadataProvenance(source_system="postgresql"),
    )

    store = InMemoryMetadataSnapshotStore()
    catalog = InMemoryCatalog()

    # Establish active snapshot
    init_snap = CanonicalMetadataSnapshot.create(
        source_system="postgresql",
        scope_fingerprint="fp_all",
        tables=[t_fin_1, t_fin_2, t_sales_old],
    )
    store.promote_snapshot(init_snap)
    catalog.sync_snapshot(list(init_snap.tables.values()), init_snap.snapshot_id)

    # OpenMetadata pilot runs scoped only to 'sales'
    t_sales_om1 = CatalogTable(
        table_fqn="warehouse.analytics.sales.orders",
        service_name="warehouse",
        database_name="analytics",
        schema_name="sales",
        table_name="orders",
        description="Onboarded via OpenMetadata",
        provenance=MetadataProvenance(source_system="openmetadata", source_version="2.0"),
    )
    t_sales_om2 = CatalogTable(
        table_fqn="warehouse.analytics.sales.customers",
        service_name="warehouse",
        database_name="analytics",
        schema_name="sales",
        table_name="customers",
        description="Onboarded via OpenMetadata",
        provenance=MetadataProvenance(source_system="openmetadata", source_version="2.0"),
    )

    om_provider = MockProvider(source_sys="openmetadata", tables=[t_sales_om1, t_sales_om2])
    pilot_scope = MetadataScope(schema_names={"sales"})
    service = MetadataSyncService(
        provider=om_provider, snapshot_store=store, catalog_storage=catalog
    )

    result = service.sync(pilot_scope)

    assert result.status == SyncStatus.SUCCESS
    active_snap = store.get_active_snapshot()
    assert active_snap is not None
    # Provenance invariant:
    assert active_snap.sync_source == "openmetadata"
    assert set(active_snap.source_systems) == {"openmetadata", "postgresql"}
    assert active_snap.is_mixed_source is True

    # Tables in active snapshot:
    assert len(active_snap.tables) == 4
    inv_prov = active_snap.tables["warehouse.analytics.finance.invoices"].provenance
    assert inv_prov is not None
    assert inv_prov.source_system == "postgresql"

    orders_prov = active_snap.tables["warehouse.analytics.sales.orders"].provenance
    assert orders_prov is not None
    assert orders_prov.source_system == "openmetadata"


def test_openmetadata_provider_failure_preserves_lkg() -> None:
    """When OpenMetadata fails with 500, sync status is FAILED and active LKG is untouched."""
    t_existing = CatalogTable(
        table_fqn="warehouse.analytics.sales.orders",
        service_name="warehouse",
        database_name="analytics",
        schema_name="sales",
        table_name="orders",
        provenance=MetadataProvenance(source_system="postgresql"),
    )
    store = InMemoryMetadataSnapshotStore()
    initial_snap = CanonicalMetadataSnapshot.create(
        source_system="postgresql",
        scope_fingerprint="fp1",
        tables=[t_existing],
    )
    store.promote_snapshot(initial_snap)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "Internal OpenMetadata Error"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        max_retries=0,
        transport=httpx.MockTransport(failing_handler),
    )
    provider = OpenMetadataProvider(client=client)
    service = MetadataSyncService(provider=provider, snapshot_store=store)

    result = service.sync(MetadataScope(schema_names={"sales"}))

    assert result.status == SyncStatus.FAILED
    active_snap = store.get_active_snapshot()
    assert active_snap is not None
    assert active_snap.snapshot_id == initial_snap.snapshot_id
    assert active_snap.source_system == "postgresql"


@pytest.mark.skipif(
    not os.getenv("OPENMETADATA_URL") or not os.getenv("OPENMETADATA_AUTH_TOKEN"),
    reason="Live OpenMetadata instance credentials not available in environment",
)
def test_live_openmetadata_pilot_connection() -> None:
    """Optional live integration test executed only when live server environment is provided."""
    base_url = os.environ["OPENMETADATA_URL"]
    auth_token = os.environ["OPENMETADATA_AUTH_TOKEN"]

    client = OpenMetadataClient(
        base_url=base_url,
        auth_token=auth_token,
        max_assets=10,
    )
    provider = OpenMetadataProvider(client=client)
    tables = provider.fetch_metadata()
    assert isinstance(tables, list)


class MockProvider(MetadataProviderPort):
    def __init__(self, source_sys: str, tables: list[CatalogTable]) -> None:
        self._source_sys = source_sys
        self._tables = tables

    @property
    def source_system(self) -> str:
        return self._source_sys

    def fetch_metadata(self, scope: MetadataScope | None = None) -> list[CatalogTable]:
        if scope is None:
            return self._tables
        return [
            t
            for t in self._tables
            if scope.matches_table(
                table_name=t.table_name,
                schema_name=t.schema_name,
                database_name=t.database_name,
                asset_type=t.table_type,
            )
        ]
