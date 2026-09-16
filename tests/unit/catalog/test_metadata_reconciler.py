"""Unit tests for MetadataReconciler and scope-aware deletion safety."""

from t2s.catalog.canonical_metadata import CatalogColumn, CatalogTable
from t2s.catalog.metadata_reconciler import MetadataReconciler, ReconciliationStatus
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot


def _make_table(
    table_name: str, schema_name: str = "analytics", col_type: str = "text"
) -> CatalogTable:
    table_fqn = f"svc.db.{schema_name}.{table_name}"
    return CatalogTable(
        table_fqn=table_fqn,
        service_name="svc",
        database_name="db",
        schema_name=schema_name,
        table_name=table_name,
        columns=[
            CatalogColumn(
                column_fqn=f"{table_fqn}.id",
                column_name="id",
                data_type=col_type,
                ordinal_position=1,
            )
        ],
    )


def test_reconciliation_new_asset() -> None:
    scope = MetadataScope(schema_names={"analytics"})
    t1 = _make_table("orders")

    summary = MetadataReconciler.reconcile(
        previous_snapshot=None,
        candidate_tables=[t1],
        scope=scope,
    )

    assert summary.new_count == 1
    assert summary.changed_count == 0
    assert summary.deleted_count == 0
    assert summary.unchanged_count == 0
    assert summary.has_changes is True
    assert summary.assets[0].status == ReconciliationStatus.NEW
    assert summary.assets[0].table_fqn == t1.table_fqn


def test_reconciliation_changed_and_unchanged_assets() -> None:
    t_orders = _make_table("orders", col_type="text")
    t_customers_v1 = _make_table("customers", col_type="text")
    prev_snapshot = CanonicalMetadataSnapshot.create(
        source_system="test",
        scope_fingerprint="fp1",
        tables=[t_orders, t_customers_v1],
    )

    # In candidate: orders is unchanged; customers has changed column type
    t_customers_v2 = _make_table("customers", col_type="integer")
    scope = MetadataScope(schema_names={"analytics"})

    summary = MetadataReconciler.reconcile(
        previous_snapshot=prev_snapshot,
        candidate_tables=[t_orders, t_customers_v2],
        scope=scope,
    )

    assert summary.unchanged_count == 1
    assert summary.changed_count == 1
    assert summary.new_count == 0
    assert summary.deleted_count == 0
    assert summary.has_changes is True

    asset_map = {a.table_fqn: a for a in summary.assets}
    assert asset_map[t_orders.table_fqn].status == ReconciliationStatus.UNCHANGED
    assert asset_map[t_customers_v1.table_fqn].status == ReconciliationStatus.CHANGED


def test_reconciliation_scope_limited_deletion_safety() -> None:
    """Critical safety test: assets outside authoritative scope are NEVER deleted."""
    t_analytics_orders = _make_table("orders", schema_name="analytics")
    t_analytics_customers = _make_table("customers", schema_name="analytics")
    t_finance_payments = _make_table("payments", schema_name="finance")

    prev_snapshot = CanonicalMetadataSnapshot.create(
        source_system="test",
        scope_fingerprint="fp_full",
        tables=[t_analytics_orders, t_analytics_customers, t_finance_payments],
    )

    # Current sync scope is strictly analytics schema!
    # Candidate returns only analytics.orders (analytics.customers was dropped in source).
    current_scope = MetadataScope(schema_names={"analytics"})

    summary = MetadataReconciler.reconcile(
        previous_snapshot=prev_snapshot,
        candidate_tables=[t_analytics_orders],
        scope=current_scope,
    )

    # analytics.customers was in scope and is missing -> DELETED
    assert summary.deleted_count == 1
    deleted_asset = next(a for a in summary.assets if a.status == ReconciliationStatus.DELETED)
    assert deleted_asset.table_fqn == t_analytics_customers.table_fqn

    # finance.payments was OUTSIDE authoritative scope -> PRESERVED in merged state!
    assert summary.unscoped_preserved_count == 1
    assert t_finance_payments.table_fqn in summary.merged_tables
    # Final merged result has orders (updated) and payments (preserved)
    assert summary.total_result_count == 2
    assert t_analytics_orders.table_fqn in summary.merged_tables
    assert t_finance_payments.table_fqn in summary.merged_tables
    assert t_analytics_customers.table_fqn not in summary.merged_tables


def test_reconciliation_source_ordering_invariance() -> None:
    t1 = _make_table("alpha")
    t2 = _make_table("beta")
    scope = MetadataScope(schema_names={"analytics"})

    summary1 = MetadataReconciler.reconcile(None, [t1, t2], scope)
    summary2 = MetadataReconciler.reconcile(None, [t2, t1], scope)

    assert [a.table_fqn for a in summary1.assets] == [a.table_fqn for a in summary2.assets]
    assert summary1.new_count == summary2.new_count
