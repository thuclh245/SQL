"""Unit tests for Metadata Sync Hardening pass (6 logic hardening points)."""

import threading
from unittest.mock import MagicMock, Mock

from t2s.catalog.canonical_metadata import (
    AssetIdentity,
    CatalogColumn,
    CatalogForeignKey,
    CatalogTable,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.catalog.metadata_provider import MetadataProviderPort
from t2s.catalog.metadata_quarantine import InMemoryMetadataQuarantine
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot_store import InMemoryMetadataSnapshotStore
from t2s.catalog.metadata_sync_result import SyncStatus
from t2s.catalog.metadata_sync_service import MetadataSyncService
from t2s.catalog.metadata_validation import MetadataValidationGate
from t2s.security.error_sanitizer import sanitize_error_message


def _make_table(
    table_name: str,
    schema_name: str = "core",
    columns: list[str] | None = None,
    fks: list[CatalogForeignKey] | None = None,
    description: str | None = "Business description",
    database_name: str = "db",
    service_name: str = "svc",
) -> CatalogTable:
    cols = columns or ["id"]
    table_fqn = f"{service_name}.{database_name}.{schema_name}.{table_name}"
    return CatalogTable(
        table_fqn=table_fqn,
        service_name=service_name,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
        description=description,
        columns=[
            CatalogColumn(
                column_fqn=f"{table_fqn}.{c}",
                column_name=c,
                data_type="integer" if c.endswith("_id") or c == "id" else "text",
                ordinal_position=idx + 1,
            )
            for idx, c in enumerate(cols)
        ],
        foreign_keys=fks or [],
    )


def test_asset_identity_parse_canonical_locator() -> None:
    # Standard 4 parts
    svc, db, sch, asset = AssetIdentity.parse_canonical_locator("pg.prod_db.core.users")
    assert (svc, db, sch, asset) == ("pg", "prod_db", "core", "users")

    # Quoted schema containing dot
    svc, db, sch, asset = AssetIdentity.parse_canonical_locator('pg.prod_db."raw.data".orders')
    assert (svc, db, sch, asset) == ("pg", "prod_db", "raw.data", "orders")

    # Quoted table containing dot
    svc, db, sch, asset = AssetIdentity.parse_canonical_locator('pg.prod_db.core."orders.archive"')
    assert (svc, db, sch, asset) == ("pg", "prod_db", "core", "orders.archive")


def test_referential_integrity_without_split_dots() -> None:
    # Target table has dot in schema name: 'raw.data'
    target_fk = CatalogForeignKey(
        from_table_fqn="pg.db.analytics.daily_orders",
        from_column_names=["order_id"],
        to_table_fqn='pg.db."raw.data".orders',
        to_column_names=["id"],
        to_schema_name="raw.data",
        to_table_name="orders",
        to_database_name="db",
        to_service_name="pg",
    )
    source_table = _make_table(
        "daily_orders",
        schema_name="analytics",
        columns=["id", "order_id"],
        fks=[target_fk],
    )
    # Scope covers only analytics (target is outside scope -> should be WARNING, not crash or ERROR)
    scope = MetadataScope(schema_names={"analytics"})
    gate = MetadataValidationGate()

    result = gate.validate(
        candidate_tables=[source_table],
        merged_tables={source_table.table_fqn: source_table},
        scope=scope,
    )

    assert result.has_errors is False
    assert result.has_warnings is True
    assert any(i.code == "UNRESOLVED_OUT_OF_SCOPE_FK" for i in result.issues)


def test_strict_candidate_scope_containment_rejects_violating_asset() -> None:
    # Scope specifies only schema 'sales'
    scope = MetadataScope(schema_names={"sales"})

    # Provider inadvertently returns a table from 'payroll'
    t_sales = _make_table("orders", schema_name="sales")
    t_payroll = _make_table("salaries", schema_name="payroll")

    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    mock_provider.fetch_metadata.return_value = [t_sales, t_payroll]

    quarantine = InMemoryMetadataQuarantine()
    store = InMemoryMetadataSnapshotStore()
    service = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        quarantine=quarantine,
    )

    result = service.sync(scope)

    assert result.status == SyncStatus.REJECTED
    assert result.validation_result is not None
    assert result.validation_result.has_errors is True
    assert any(i.code == "CANDIDATE_OUTSIDE_SCOPE" for i in result.validation_result.issues)
    assert store.get_active_snapshot() is None
    assert len(quarantine.get_quarantine_records()) == 1
    assert t_payroll.table_fqn in quarantine.get_quarantine_records()[0].rejected_table_fqns


def test_source_authority_transition_promotes_with_same_content() -> None:
    t_orders = _make_table("orders", schema_name="sales")
    scope = MetadataScope(schema_names={"sales"})
    store = InMemoryMetadataSnapshotStore()
    catalog = InMemoryCatalog()

    # 1. Initial sync with PostgreSQL provider
    provider_pg = Mock(spec=MetadataProviderPort)
    provider_pg.source_system = "postgresql"
    provider_pg.fetch_metadata.return_value = [t_orders]

    service_pg = MetadataSyncService(
        provider=provider_pg,
        snapshot_store=store,
        catalog_storage=catalog,
    )
    result_pg = service_pg.sync(scope)
    assert result_pg.status == SyncStatus.SUCCESS
    active_pg = store.get_active_snapshot()
    assert active_pg is not None
    assert active_pg.source_system == "postgresql"
    initial_hash = active_pg.semantic_content_hash

    # 2. Subsequent sync with OpenMetadata provider returning exact same table content
    provider_om = Mock(spec=MetadataProviderPort)
    provider_om.source_system = "openmetadata"
    provider_om.fetch_metadata.return_value = [t_orders]

    service_om = MetadataSyncService(
        provider=provider_om,
        snapshot_store=store,
        catalog_storage=catalog,
    )
    result_om = service_om.sync(scope)

    # Must NOT be NO_CHANGE; must be SUCCESS with updated source authority!
    assert result_om.status == SyncStatus.SUCCESS
    active_om = store.get_active_snapshot()
    assert active_om is not None
    assert active_om.source_system == "openmetadata"
    assert active_om.semantic_content_hash == initial_hash
    assert "Source authority transitioned from 'postgresql' to 'openmetadata'" in result_om.message


def test_atomic_serving_promotion_rollback_on_catalog_failure() -> None:
    t_orders = _make_table("orders", schema_name="sales")
    scope = MetadataScope(schema_names={"sales"})
    store = InMemoryMetadataSnapshotStore()

    # Establish initial good snapshot
    initial_snapshot = None
    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "postgresql"
    mock_provider.fetch_metadata.return_value = [t_orders]

    catalog_working = InMemoryCatalog()
    service1 = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        catalog_storage=catalog_working,
    )
    res1 = service1.sync(scope)
    assert res1.status == SyncStatus.SUCCESS
    initial_snapshot = store.get_active_snapshot()
    assert initial_snapshot is not None

    # Second sync with a failing catalog
    failing_catalog = MagicMock()
    failing_catalog.sync_snapshot.side_effect = RuntimeError("Serving store write timeout")

    t_orders_v2 = _make_table("orders", schema_name="sales", description="Updated orders")
    mock_provider.fetch_metadata.return_value = [t_orders_v2]

    service2 = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        catalog_storage=failing_catalog,
    )
    res2 = service2.sync(scope)

    # Serving catalog failed -> sync fails, and active snapshot is NOT modified!
    assert res2.status == SyncStatus.FAILED
    assert "Serving catalog update failed" in res2.message
    active_snapshot = store.get_active_snapshot()
    assert active_snapshot is not None
    assert active_snapshot.snapshot_id == initial_snapshot.snapshot_id


def test_secret_sanitization_in_error_messages() -> None:
    raw_error = (
        "connection to postgresql://app_user:super_secret_password123"
        "@prod-db.internal:5432/finance failed: "
        "auth token Bearer sec-token-xyz-12345678 was rejected"
    )
    clean = sanitize_error_message(raw_error)
    assert "super_secret_password123" not in clean
    assert "sec-token-xyz-12345678" not in clean
    assert "postgresql://app_user:***@prod-db.internal:5432/finance" in clean
    assert "Bearer ***" in clean

    # Verify provider exception in service is sanitized
    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "postgresql"
    mock_provider.fetch_metadata.side_effect = ConnectionError(raw_error)

    service = MetadataSyncService(provider=mock_provider)
    result = service.sync(MetadataScope(schema_names={"public"}))

    assert result.status == SyncStatus.FAILED
    assert "super_secret_password123" not in result.message
    assert "postgresql://app_user:***@prod-db.internal:5432/finance" in result.message


def test_concurrency_and_thread_safety_in_snapshot_store_and_catalog() -> None:
    store = InMemoryMetadataSnapshotStore()
    catalog = InMemoryCatalog()
    scope = MetadataScope(schema_names={"core"})

    tables = [_make_table(f"tbl_{i}") for i in range(10)]
    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "postgresql"
    mock_provider.fetch_metadata.return_value = tables

    service = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        catalog_storage=catalog,
    )
    res = service.sync(scope)
    assert res.status == SyncStatus.SUCCESS

    errors: list[Exception] = []

    def reader_worker() -> None:
        try:
            for _ in range(50):
                active = store.get_active_snapshot()
                assert active is not None
                cat_tables = catalog.list_table_fqns()
                assert len(cat_tables) == 10
                assert catalog.active_snapshot_id == active.snapshot_id
        except Exception as e:
            errors.append(e)

    def writer_worker() -> None:
        try:
            for i in range(10):
                updated_tables = [
                    _make_table(f"tbl_{j}", description=f"iter_{i}") for j in range(10)
                ]
                mock_provider.fetch_metadata.return_value = updated_tables
                sync_res = service.sync(scope)
                assert sync_res.status in (SyncStatus.SUCCESS, SyncStatus.NO_CHANGE)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=reader_worker) for _ in range(4)] + [
        threading.Thread(target=writer_worker) for _ in range(2)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent execution generated errors: {errors}"
