"""Scale assertion tests for Metadata Sync, Reconciliation, and Validation (9,000 assets)."""

import time

from t2s.catalog.canonical_metadata import (
    CatalogColumn,
    CatalogForeignKey,
    CatalogTable,
)
from t2s.catalog.metadata_reconciler import MetadataReconciler
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot
from t2s.catalog.metadata_validation import MetadataValidationGate


def _generate_synthetic_tables(count: int = 9000) -> list[CatalogTable]:
    tables: list[CatalogTable] = []
    # 90 schemas with 100 tables each = 9000 tables
    for i in range(count):
        s_id = i // 100
        t_id = i % 100
        schema = f"scale_schema_{s_id}"
        table_name = f"tbl_{t_id}"
        table_fqn = f"pg.db.{schema}.{table_name}"

        cols = [
            CatalogColumn(
                column_fqn=f"{table_fqn}.id",
                column_name="id",
                data_type="integer",
                ordinal_position=1,
            ),
            CatalogColumn(
                column_fqn=f"{table_fqn}.ref_id",
                column_name="ref_id",
                data_type="integer",
                ordinal_position=2,
            ),
            CatalogColumn(
                column_fqn=f"{table_fqn}.name",
                column_name="name",
                data_type="text",
                ordinal_position=3,
            ),
        ]

        fks = []
        if t_id > 0:
            parent_fqn = f"pg.db.{schema}.tbl_{t_id - 1}"
            fks.append(
                CatalogForeignKey(
                    from_table_fqn=table_fqn,
                    from_column_names=["ref_id"],
                    to_table_fqn=parent_fqn,
                    to_column_names=["id"],
                )
            )

        tables.append(
            CatalogTable(
                table_fqn=table_fqn,
                service_name="pg",
                database_name="db",
                schema_name=schema,
                table_name=table_name,
                description=f"Synthetic scale table {i}",
                columns=cols,
                foreign_keys=fks,
            )
        )
    return tables


def test_reconciliation_scale_9000_assets() -> None:
    tables = _generate_synthetic_tables(9000)

    # Previous snapshot: all 9000 tables
    prev_snapshot = CanonicalMetadataSnapshot.create(
        source_system="pg",
        scope_fingerprint="scale_test",
        tables={t.table_fqn: t for t in tables},
    )

    # Candidate:
    # 0 to 7999: unchanged (8000)
    # 8000 to 8499: changed description (500)
    # 8500 to 8999: omitted from candidate (deleted) (500)
    # new_0 to new_499: added (500)
    candidate: list[CatalogTable] = []
    for t in tables[:8000]:
        candidate.append(t)

    for t in tables[8000:8500]:
        candidate.append(t.model_copy(update={"description": f"{t.description} (UPDATED)"}))

    # 500 new tables
    for i in range(500):
        schema = "scale_schema_new"
        table_name = f"new_tbl_{i}"
        table_fqn = f"pg.db.{schema}.{table_name}"
        candidate.append(
            CatalogTable(
                table_fqn=table_fqn,
                service_name="pg",
                database_name="db",
                schema_name=schema,
                table_name=table_name,
                description="New table",
                columns=[
                    CatalogColumn(
                        column_fqn=f"{table_fqn}.id",
                        column_name="id",
                        data_type="integer",
                        ordinal_position=1,
                    )
                ],
                foreign_keys=[],
            )
        )

    # Authoritative scope covering all schemas
    scope = MetadataScope(
        schema_names={f"scale_schema_{i}" for i in range(90)} | {"scale_schema_new"}
    )

    reconciler = MetadataReconciler()

    start_time = time.perf_counter()
    summary = reconciler.reconcile(
        candidate_tables=candidate,
        previous_snapshot=prev_snapshot,
        scope=scope,
    )
    elapsed = time.perf_counter() - start_time

    assert summary.unchanged_count == 8000
    assert summary.changed_count == 500
    assert summary.deleted_count == 500
    assert len(summary.assets) == 9500
    assert summary.total_result_count == 9000

    # Strict O(N) performance assertion: 9500 asset reconciliation must complete under 2.5 seconds
    assert elapsed < 2.5, f"Reconciliation took {elapsed:.2f}s, expected < 2.5s"


def test_validation_gate_scale_9000_assets() -> None:
    tables = _generate_synthetic_tables(9000)
    scope = MetadataScope(schema_names={f"scale_schema_{i}" for i in range(90)})

    gate = MetadataValidationGate(maximum_allowed_drop_ratio=0.5)

    start_time = time.perf_counter()
    result = gate.validate(
        candidate_tables=tables,
        merged_tables={t.table_fqn: t for t in tables},
        scope=scope,
    )
    elapsed = time.perf_counter() - start_time

    assert result.has_errors is False
    assert result.error_count == 0

    # Strict O(N) performance assertion:
    # 9000 asset validation with FK cross-resolution must complete under 2.5 seconds
    assert elapsed < 2.5, f"Validation took {elapsed:.2f}s, expected < 2.5s"
