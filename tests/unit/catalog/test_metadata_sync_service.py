"""Unit tests for MetadataSyncService."""

from unittest.mock import Mock

from t2s.catalog.canonical_metadata import (
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


def _make_table(
    table_name: str,
    schema_name: str = "core",
    columns: list[str] | None = None,
    fks: list[CatalogForeignKey] | None = None,
    description: str | None = "Business description",
) -> CatalogTable:
    cols = columns or ["id"]
    table_fqn = f"svc.db.{schema_name}.{table_name}"
    return CatalogTable(
        table_fqn=table_fqn,
        service_name="svc",
        database_name="db",
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


def test_full_catalog_safety_gate_blocks_unrestricted_by_default() -> None:
    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    service = MetadataSyncService(
        provider=mock_provider,
        allow_full_catalog_sync=False,
    )
    unrestricted_scope = MetadataScope(include_tables=None, schema_names=None)

    result = service.sync(unrestricted_scope)

    assert result.status == SyncStatus.REJECTED
    assert "Full-catalog sync rejected" in result.message
    assert mock_provider.fetch_metadata.call_count == 0


def test_full_catalog_safety_gate_allows_when_explicitly_configured() -> None:
    t = _make_table("orders")
    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    mock_provider.fetch_metadata.return_value = [t]

    service = MetadataSyncService(
        provider=mock_provider,
        allow_full_catalog_sync=True,
    )
    unrestricted_scope = MetadataScope(include_tables=None, schema_names=None)

    result = service.sync(unrestricted_scope)

    assert result.status == SyncStatus.SUCCESS
    assert result.promoted_snapshot_id is not None
    assert mock_provider.fetch_metadata.call_count == 1


def test_provider_failure_preserves_active_lkg() -> None:
    store = InMemoryMetadataSnapshotStore()
    quarantine = InMemoryMetadataQuarantine()
    t1 = _make_table("orders")

    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    mock_provider.fetch_metadata.return_value = [t1]

    service = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        quarantine=quarantine,
    )
    scope = MetadataScope(schema_names={"core"})

    # First sync succeeds
    result1 = service.sync(scope)
    assert result1.status == SyncStatus.SUCCESS
    active = store.get_active_snapshot()
    initial_lkg_id = active.snapshot_id if active else None
    assert initial_lkg_id is not None

    # Next sync fails due to provider exception
    mock_provider.fetch_metadata.side_effect = RuntimeError("Database connection dropped")
    result2 = service.sync(scope)

    assert result2.status == SyncStatus.FAILED
    assert result2.active_snapshot_id == initial_lkg_id
    active = store.get_active_snapshot()
    assert active is not None
    assert active.snapshot_id == initial_lkg_id
    assert "Database connection dropped" in result2.message


def test_validation_error_quarantines_and_preserves_lkg() -> None:
    store = InMemoryMetadataSnapshotStore()
    quarantine = InMemoryMetadataQuarantine()
    t_valid = _make_table("orders")

    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    mock_provider.fetch_metadata.return_value = [t_valid]

    service = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        quarantine=quarantine,
    )
    scope = MetadataScope(schema_names={"core"})

    # Initial good sync
    result1 = service.sync(scope)
    assert result1.status == SyncStatus.SUCCESS
    active = store.get_active_snapshot()
    lkg_id = active.snapshot_id if active else None
    assert lkg_id is not None

    # Second sync returns candidate with broken FK pointing to missing in-scope table
    broken_fk = CatalogForeignKey(
        from_table_fqn="svc.db.core.orders",
        from_column_names=["user_id"],
        to_table_fqn="svc.db.core.users",
        to_column_names=["id"],
    )
    t_bad = _make_table(
        "orders",
        columns=["id", "user_id"],
        fks=[broken_fk],
    )
    mock_provider.fetch_metadata.return_value = [t_bad]

    result2 = service.sync(scope)

    assert result2.status == SyncStatus.REJECTED
    assert result2.active_snapshot_id == lkg_id
    active_after = store.get_active_snapshot()
    assert active_after is not None
    assert active_after.snapshot_id == lkg_id

    # Quarantine recorded
    q_records = quarantine.get_quarantine_records()
    assert len(q_records) == 1
    assert q_records[0].sync_id == result2.sync_id
    assert "svc.db.core.orders" in q_records[0].rejected_table_fqns
    assert any(i.severity.value == "ERROR" for i in q_records[0].issues)


def test_validation_warnings_allow_promotion() -> None:
    store = InMemoryMetadataSnapshotStore()
    quarantine = InMemoryMetadataQuarantine()
    # Table with missing description and out-of-scope FK
    pilot_fk = CatalogForeignKey(
        from_table_fqn="svc.db.core.orders",
        from_column_names=["external_id"],
        to_table_fqn="svc.db.legacy_erp.invoices",
        to_column_names=["id"],
    )
    t = _make_table(
        "orders",
        columns=["id", "external_id"],
        fks=[pilot_fk],
        description="",  # triggers missing description warning
    )

    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    mock_provider.fetch_metadata.return_value = [t]

    service = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        quarantine=quarantine,
    )
    scope = MetadataScope(schema_names={"core"})

    result = service.sync(scope)

    assert result.status == SyncStatus.SUCCESS
    assert result.validation_result is not None
    assert result.validation_result.has_warnings is True
    assert result.validation_result.has_errors is False
    assert result.promoted_snapshot_id is not None
    assert len(quarantine.get_quarantine_records()) == 0


def test_idempotent_no_change_detection() -> None:
    store = InMemoryMetadataSnapshotStore()
    t = _make_table("orders")

    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    mock_provider.fetch_metadata.return_value = [t]

    service = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
    )
    scope = MetadataScope(schema_names={"core"})

    # Sync 1: Promoted
    result1 = service.sync(scope)
    assert result1.status == SyncStatus.SUCCESS
    first_snapshot_id = result1.promoted_snapshot_id

    # Sync 2: Identical candidate
    result2 = service.sync(scope)
    assert result2.status == SyncStatus.NO_CHANGE
    assert result2.promoted_snapshot_id is None
    assert result2.active_snapshot_id == first_snapshot_id
    active_now = store.get_active_snapshot()
    assert active_now is not None
    assert active_now.snapshot_id == first_snapshot_id


def test_downstream_catalog_atomic_upsert_and_delete() -> None:
    catalog = InMemoryCatalog()
    store = InMemoryMetadataSnapshotStore()

    t_users = _make_table("users")
    t_orders = _make_table("orders")

    mock_provider = Mock(spec=MetadataProviderPort)
    mock_provider.source_system = "test_pg"
    mock_provider.fetch_metadata.return_value = [t_users, t_orders]

    service = MetadataSyncService(
        provider=mock_provider,
        snapshot_store=store,
        catalog_storage=catalog,
    )
    scope = MetadataScope(schema_names={"core"})

    # First sync: both tables upserted
    res1 = service.sync(scope)
    assert res1.status == SyncStatus.SUCCESS
    assert set(catalog.list_table_fqns()) == {"svc.db.core.users", "svc.db.core.orders"}

    # Second sync: candidate only returns users; scope authoritatively deletes orders
    mock_provider.fetch_metadata.return_value = [t_users]
    # Allow drop in validation gate by relaxing drop ratio for test
    gate = MetadataValidationGate(maximum_allowed_drop_ratio=0.8)
    service.validation_gate = gate

    res2 = service.sync(scope)
    assert res2.status == SyncStatus.SUCCESS
    assert catalog.list_table_fqns() == ["svc.db.core.users"]
