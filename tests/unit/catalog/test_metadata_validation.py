"""Unit tests for MetadataValidationGate, referential integrity, and anomaly guards."""

from t2s.catalog.canonical_metadata import CatalogColumn, CatalogForeignKey, CatalogTable
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot
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
                data_type="text",
                ordinal_position=idx + 1,
            )
            for idx, c in enumerate(cols)
        ],
        foreign_keys=fks or [],
    )


def test_validation_duplicate_canonical_identity_rejected() -> None:
    t1 = _make_table("orders")
    t2 = _make_table("orders")  # Duplicate identical FQN in candidate batch
    gate = MetadataValidationGate()
    scope = MetadataScope(schema_names={"core"})

    result = gate.validate([t1, t2], {t1.table_fqn: t1}, scope)
    assert result.has_errors is True
    assert any(i.code == "DUPLICATE_CANONICAL_IDENTITY" for i in result.issues)


def test_validation_valid_foreign_key() -> None:
    t_cust = _make_table("customers", columns=["customer_id"])
    t_ord = _make_table(
        "orders",
        columns=["order_id", "customer_id"],
        fks=[
            CatalogForeignKey(
                from_table_fqn="svc.db.core.orders",
                from_column_names=["customer_id"],
                to_table_fqn="svc.db.core.customers",
                to_column_names=["customer_id"],
            )
        ],
    )
    merged = {t_cust.table_fqn: t_cust, t_ord.table_fqn: t_ord}
    gate = MetadataValidationGate()
    scope = MetadataScope(schema_names={"core"})

    result = gate.validate([t_cust, t_ord], merged, scope)
    assert result.has_errors is False
    assert result.valid_fk_count == 1
    assert result.broken_fk_count == 0


def test_validation_broken_target_column_on_existing_table_rejected() -> None:
    t_cust = _make_table("customers", columns=["id"])
    # FK references "nonexistent_col" on target table
    t_ord = _make_table(
        "orders",
        columns=["order_id", "cust_id"],
        fks=[
            CatalogForeignKey(
                from_table_fqn="svc.db.core.orders",
                from_column_names=["cust_id"],
                to_table_fqn="svc.db.core.customers",
                to_column_names=["nonexistent_col"],
            )
        ],
    )
    merged = {t_cust.table_fqn: t_cust, t_ord.table_fqn: t_ord}
    gate = MetadataValidationGate()
    scope = MetadataScope(schema_names={"core"})

    result = gate.validate([t_cust, t_ord], merged, scope)
    assert result.has_errors is True
    assert any(i.code == "BROKEN_FK_TARGET_COLUMNS" for i in result.issues)
    assert result.broken_fk_count == 1


def test_validation_missing_fk_target_in_scope_rejected() -> None:
    # Target table svc.db.core.customers is within scope (schema 'core'), but missing!
    t_ord = _make_table(
        "orders",
        columns=["order_id", "customer_id"],
        fks=[
            CatalogForeignKey(
                from_table_fqn="svc.db.core.orders",
                from_column_names=["customer_id"],
                to_table_fqn="svc.db.core.customers",
                to_column_names=["customer_id"],
            )
        ],
    )
    gate = MetadataValidationGate()
    scope = MetadataScope(schema_names={"core"})

    result = gate.validate([t_ord], {t_ord.table_fqn: t_ord}, scope)
    assert result.has_errors is True
    assert any(i.code == "BROKEN_REFERENCE_TARGET_MISSING_IN_SCOPE" for i in result.issues)
    assert result.broken_fk_count == 1


def test_validation_pilot_out_of_scope_fk_yields_warning_not_error() -> None:
    """Critical pilot test: FK pointing outside current pilot scope is WARNING, not ERROR."""
    # Target table is in schema 'finance', but current scope is only 'analytics'
    t_ord = _make_table(
        "orders",
        schema_name="analytics",
        columns=["order_id", "ledger_id"],
        fks=[
            CatalogForeignKey(
                from_table_fqn="svc.db.analytics.orders",
                from_column_names=["ledger_id"],
                to_table_fqn="svc.db.finance.ledgers",
                to_column_names=["ledger_id"],
            )
        ],
    )
    gate = MetadataValidationGate()
    scope = MetadataScope(schema_names={"analytics"})

    result = gate.validate([t_ord], {t_ord.table_fqn: t_ord}, scope)
    # Must NOT be an error! It allows pilot onboarding
    assert result.has_errors is False
    assert result.has_warnings is True
    assert any(i.code == "UNRESOLVED_OUT_OF_SCOPE_FK" for i in result.issues)
    assert result.unresolved_out_of_scope_fk_count == 1


def test_validation_missing_description_is_warning_only() -> None:
    t = _make_table("orders", description=None)
    gate = MetadataValidationGate()
    scope = MetadataScope(schema_names={"core"})

    result = gate.validate([t], {t.table_fqn: t}, scope)
    assert result.has_errors is False
    assert result.has_warnings is True
    assert any(i.code == "MISSING_TABLE_DESCRIPTION" for i in result.issues)


def test_validation_asset_count_anomaly_guard() -> None:
    # Previous active snapshot had 20 tables
    prev_tables = [_make_table(f"t_{i}") for i in range(20)]
    scope = MetadataScope(schema_names={"core"})
    prev_snapshot = CanonicalMetadataSnapshot.create(
        source_system="test",
        scope_fingerprint=scope.compute_fingerprint(),
        tables=prev_tables,
    )

    # Current candidate dropped to 5 tables (75% drop > default 50% threshold)
    cand_tables = [_make_table(f"t_{i}") for i in range(5)]
    gate = MetadataValidationGate(maximum_allowed_drop_ratio=0.5)

    result = gate.validate(
        candidate_tables=cand_tables,
        merged_tables={t.table_fqn: t for t in cand_tables},
        scope=scope,
        previous_snapshot=prev_snapshot,
    )

    assert result.has_errors is True
    assert any(i.code == "ANOMALOUS_ASSET_COUNT_DROP" for i in result.issues)
