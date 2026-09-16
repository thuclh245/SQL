"""Unit tests for the provider-agnostic Canonical Metadata Model Foundation.

Tests cover asset identity, column fidelity, structural constraints, business metadata,
provenance, immutability, deterministic serialization, and domain invariants using
strictly synthetic schemas (zero benchmark leakage).
"""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from t2s.catalog.canonical_metadata import (
    AssetIdentity,
    CatalogColumn,
    CatalogForeignKey,
    CatalogTable,
    MetadataProvenance,
    MetadataSnapshot,
)

# --- 1. Asset Identity & Dialect Invariance ---


def test_asset_identity_table_and_view() -> None:
    """Verify structured identity preservation for tables and views."""
    identity = AssetIdentity(
        service_name="enterprise_dw",
        database_name="sales",
        schema_name="public",
        asset_name="orders",
        asset_type="table",
        canonical_fqn="enterprise_dw.sales.orders",
    )
    assert identity.service_name == "enterprise_dw"
    assert identity.canonical_fqn == "enterprise_dw.sales.orders"

    table = CatalogTable(
        table_fqn="enterprise_dw.sales.orders",
        service_name="enterprise_dw",
        database_name="sales",
        schema_name="public",
        table_name="orders",
        table_type="table",
        sql_identifier="orders",
    )
    assert table.asset_identity.service_name == "enterprise_dw"
    assert table.asset_identity.database_name == "sales"
    assert table.asset_identity.schema_name == "public"
    assert table.asset_identity.asset_name == "orders"
    assert table.asset_identity.asset_type == "table"
    assert table.asset_identity.canonical_fqn == "enterprise_dw.sales.orders"

    view = CatalogTable(
        table_fqn="enterprise_dw.sales.v_active_orders",
        service_name="enterprise_dw",
        database_name="sales",
        schema_name="public",
        table_name="v_active_orders",
        table_type="view",
        sql_identifier="v_active_orders",
    )
    assert view.table_type == "view"
    assert view.asset_identity.asset_type == "view"


def test_asset_identity_preserves_case_and_unicode() -> None:
    """Verify mixed-case identifiers and Vietnamese Unicode descriptions are preserved."""
    vn_description = "Bảng lưu trữ thông tin đơn hàng và hóa đơn thanh toán của khách hàng"
    table = CatalogTable(
        table_fqn="AppDB.Commerce.CustomerOrders",
        service_name="AppDB",
        database_name="Commerce",
        schema_name="Sales",
        table_name="CustomerOrders",
        description=vn_description,
        columns=[
            CatalogColumn(
                column_fqn="AppDB.Commerce.CustomerOrders.MãĐơnHàng",
                column_name="MãĐơnHàng",
                data_type="BIGINT",
                native_type="BIGINT GENERATED ALWAYS AS IDENTITY",
                description="Mã định danh duy nhất của từng đơn hàng",
                is_primary_key=True,
                ordinal_position=1,
            )
        ],
        primary_key_column_names=["MãĐơnHàng"],
    )

    assert table.table_name == "CustomerOrders"  # Case preserved
    assert table.description == vn_description
    assert table.columns[0].column_name == "MãĐơnHàng"  # Unicode preserved
    assert table.columns[0].description == "Mã định danh duy nhất của từng đơn hàng"


# --- 2. Columns, Types & Uncertainty ---


def test_column_model_preserves_native_and_canonical_types() -> None:
    """Retain native source dialect type alongside canonical normalized type."""
    col = CatalogColumn(
        column_fqn="dw.finance.invoices.total_amount",
        column_name="total_amount",
        data_type="DECIMAL",
        native_type="NUMERIC(18, 4)",
        ordinal_position=2,
    )
    assert col.data_type == "DECIMAL"
    assert col.native_type == "NUMERIC(18, 4)"
    assert col.effective_native_type == "NUMERIC(18, 4)"


def test_column_model_supports_unknown_and_custom_types() -> None:
    """Unknown source types must never crash validation."""
    col = CatalogColumn(
        column_fqn="dw.geo.locations.boundary",
        column_name="boundary",
        data_type="GEOMETRY",
        native_type="ST_Polygon(4326)",
    )
    assert col.data_type == "GEOMETRY"
    assert col.native_type == "ST_Polygon(4326)"


def test_column_nullability_represents_uncertainty() -> None:
    """Explicitly verify that unknown nullability is None, not False or True."""
    col_unknown = CatalogColumn(
        column_fqn="dw.sales.items.notes",
        column_name="notes",
        data_type="VARCHAR",
        is_nullable=None,  # Uncertainty preserved
    )
    assert col_unknown.is_nullable is None

    col_nullable = CatalogColumn(
        column_fqn="dw.sales.items.discount",
        column_name="discount",
        data_type="DECIMAL",
        is_nullable=True,
    )
    assert col_nullable.is_nullable is True

    col_not_null = CatalogColumn(
        column_fqn="dw.sales.items.id",
        column_name="id",
        data_type="BIGINT",
        is_nullable=False,
    )
    assert col_not_null.is_nullable is False


# --- 3. Structural Constraints (PK & FK) ---


def test_single_and_composite_primary_keys() -> None:
    """Verify single and composite primary keys preserve declared order."""
    table = CatalogTable(
        table_fqn="dw.sales.order_items",
        service_name="dw",
        database_name="sales",
        schema_name="public",
        table_name="order_items",
        columns=[
            CatalogColumn(
                column_fqn="dw.sales.order_items.order_id",
                column_name="order_id",
                data_type="BIGINT",
                is_primary_key=True,
                ordinal_position=1,
            ),
            CatalogColumn(
                column_fqn="dw.sales.order_items.item_seq",
                column_name="item_seq",
                data_type="INT",
                is_primary_key=True,
                ordinal_position=2,
            ),
            CatalogColumn(
                column_fqn="dw.sales.order_items.quantity",
                column_name="quantity",
                data_type="INT",
                ordinal_position=3,
            ),
        ],
        primary_key_column_names=["order_id", "item_seq"],
    )
    assert table.primary_key_column_names == ["order_id", "item_seq"]


def test_foreign_key_composite_and_cross_schema() -> None:
    """Verify composite foreign keys and cross-schema references."""
    fk = CatalogForeignKey(
        relationship_name="fk_order_items_order",
        from_table_fqn="dw.sales.order_items",
        from_column_names=["tenant_id", "order_id"],
        to_table_fqn="dw.core.orders",
        to_column_names=["tenant_id", "id"],
        provenance="declared_foreign_key",
    )
    assert fk.from_table_fqn == "dw.sales.order_items"
    assert fk.to_table_fqn == "dw.core.orders"
    assert fk.from_column_names == ["tenant_id", "order_id"]
    assert fk.to_column_names == ["tenant_id", "id"]


def test_foreign_key_cardinality_mismatch_rejected() -> None:
    """Foreign key must reject unequal local vs remote column counts."""
    with pytest.raises(ValidationError, match="cardinality mismatch"):
        CatalogForeignKey(
            relationship_name="fk_invalid",
            from_table_fqn="dw.sales.orders",
            from_column_names=["customer_id", "region_id"],
            to_table_fqn="dw.sales.customers",
            to_column_names=["id"],
        )


def test_foreign_key_empty_columns_rejected() -> None:
    """Foreign key must reject empty column lists."""
    with pytest.raises(ValidationError, match="column lists must not be empty"):
        CatalogForeignKey(
            from_table_fqn="dw.sales.orders",
            from_column_names=[],
            to_table_fqn="dw.sales.customers",
            to_column_names=[],
        )


# --- 4. Business Metadata & Provenance ---


def test_business_metadata_tags_glossary_domain_owner() -> None:
    """Verify business semantics: tags, glossary terms, domain, owner."""
    table = CatalogTable(
        table_fqn="dw.marketing.campaigns",
        service_name="dw",
        database_name="marketing",
        schema_name="public",
        table_name="campaigns",
        owner="growth_data_team",
        domain="Marketing & Retention",
        tags=["gdpr_applicable", "pii_low", "tier1_critical"],
        glossary_terms=["RetentionCampaign", "MarketingAttribution"],
    )
    assert table.domain == "Marketing & Retention"
    assert table.owner == "growth_data_team"
    assert "gdpr_applicable" in table.tags
    assert "RetentionCampaign" in table.glossary_terms


def test_provenance_provider_independence() -> None:
    """Demonstrate provenance with an entirely synthetic provider name."""
    now = datetime.now(UTC)
    prov = MetadataProvenance(
        source_system="synthetic_enterprise_catalog_v2",
        source_entity_id="entity_guid_987654321",
        source_version="v3.1.4",
        source_updated_at=now,
    )
    table = CatalogTable(
        table_fqn="synth.inventory.warehouses",
        service_name="synth",
        database_name="inventory",
        schema_name="main",
        table_name="warehouses",
        provenance=prov,
    )
    assert table.provenance is not None
    assert table.provenance.source_system == "synthetic_enterprise_catalog_v2"
    assert table.provenance.source_entity_id == "entity_guid_987654321"
    assert table.provenance.source_version == "v3.1.4"
    assert table.provenance.source_updated_at == now
    # Backward compatibility properties populated
    assert table.source_entity_id == "entity_guid_987654321"
    assert table.metadata_version == "v3.1.4"
    assert table.updated_at == now


# --- 5. Validation Invariants ---


def test_validation_rejects_empty_identifiers() -> None:
    """Identifiers must not be empty or whitespace."""
    with pytest.raises(ValidationError, match="must not be empty"):
        CatalogTable(
            table_fqn="",
            service_name="dw",
            database_name="db",
            schema_name="schema",
            table_name="users",
        )

    with pytest.raises(ValidationError, match="must not be empty"):
        CatalogColumn(
            column_fqn="dw.db.schema.users.name",
            column_name="   ",
            data_type="VARCHAR",
        )


def test_validation_rejects_duplicate_columns() -> None:
    """Tables must reject duplicate column definitions."""
    with pytest.raises(ValidationError, match="duplicate column definitions"):
        CatalogTable(
            table_fqn="dw.sales.payments",
            service_name="dw",
            database_name="sales",
            schema_name="public",
            table_name="payments",
            columns=[
                CatalogColumn(
                    column_fqn="dw.sales.payments.amount",
                    column_name="amount",
                    data_type="DECIMAL",
                    ordinal_position=1,
                ),
                CatalogColumn(
                    column_fqn="dw.sales.payments.amount_dup",
                    column_name="amount",
                    data_type="DECIMAL",
                    ordinal_position=2,
                ),
            ],
        )


def test_validation_rejects_undefined_primary_key_column() -> None:
    """Declared primary key must exist in declared columns."""
    with pytest.raises(ValidationError, match="references undefined columns"):
        CatalogTable(
            table_fqn="dw.sales.subscriptions",
            service_name="dw",
            database_name="sales",
            schema_name="public",
            table_name="subscriptions",
            columns=[
                CatalogColumn(
                    column_fqn="dw.sales.subscriptions.id",
                    column_name="id",
                    data_type="BIGINT",
                )
            ],
            primary_key_column_names=["nonexistent_pk_id"],
        )


def test_validation_rejects_undefined_foreign_key_local_column() -> None:
    """Outgoing foreign keys must reference existing local columns."""
    with pytest.raises(ValidationError, match="references undefined local columns"):
        CatalogTable(
            table_fqn="dw.sales.subscriptions",
            service_name="dw",
            database_name="sales",
            schema_name="public",
            table_name="subscriptions",
            columns=[
                CatalogColumn(
                    column_fqn="dw.sales.subscriptions.id",
                    column_name="id",
                    data_type="BIGINT",
                )
            ],
            foreign_keys=[
                CatalogForeignKey(
                    relationship_name="fk_sub_user",
                    from_table_fqn="dw.sales.subscriptions",
                    from_column_names=["user_id"],  # not defined in columns!
                    to_table_fqn="dw.core.users",
                    to_column_names=["id"],
                )
            ],
        )


# --- 6. Immutability & Deterministic Serialization ---


def test_immutability_prevents_accidental_mutation() -> None:
    """Catalog models are frozen; mutation raises ValidationError."""
    table = CatalogTable(
        table_fqn="dw.sales.products",
        service_name="dw",
        database_name="sales",
        schema_name="public",
        table_name="products",
        description="Original description",
    )
    with pytest.raises(ValidationError):
        table.description = "Mutated description"  # type: ignore[misc]


def test_round_trip_json_serialization() -> None:
    """Verify complete model -> JSON -> model round-trip with full equality."""
    original = CatalogTable(
        table_fqn="dw.analytics.user_events",
        service_name="dw",
        database_name="analytics",
        schema_name="tracking",
        table_name="user_events",
        table_type="table",
        description="Event stream for user clicks and interactions",
        domain="Product Analytics",
        owner="analytics_eng",
        tags=["clickstream", "high_volume"],
        glossary_terms=["UserAction", "InteractionEvent"],
        columns=[
            CatalogColumn(
                column_fqn="dw.analytics.user_events.event_id",
                column_name="event_id",
                data_type="UUID",
                native_type="uuid",
                description="Unique event ID",
                is_primary_key=True,
                is_nullable=False,
                ordinal_position=1,
            ),
            CatalogColumn(
                column_fqn="dw.analytics.user_events.user_id",
                column_name="user_id",
                data_type="BIGINT",
                native_type="int8",
                is_nullable=True,
                ordinal_position=2,
            ),
        ],
        primary_key_column_names=["event_id"],
        foreign_keys=[
            CatalogForeignKey(
                relationship_name="fk_events_user",
                from_table_fqn="dw.analytics.user_events",
                from_column_names=["user_id"],
                to_table_fqn="dw.core.users",
                to_column_names=["id"],
            )
        ],
        provenance=MetadataProvenance(
            source_system="synthetic_dw",
            source_entity_id="entity-001",
            source_version="2.0",
        ),
    )

    json_str = original.model_dump_json(indent=2)
    reconstituted = CatalogTable.model_validate_json(json_str)

    assert reconstituted == original
    assert reconstituted.table_name == "user_events"
    assert len(reconstituted.columns) == 2
    assert reconstituted.columns[0].native_type == "uuid"
    assert reconstituted.provenance is not None
    assert reconstituted.provenance.source_system == "synthetic_dw"
    assert reconstituted.compute_content_hash() == original.compute_content_hash()


def test_metadata_snapshot_telemetry() -> None:
    """Verify MetadataSnapshot tracking record."""
    snapshot = MetadataSnapshot(
        snapshot_id="snap-2026-09-15-001",
        metadata_version="1.0.0",
        source_name="synthetic_catalog",
        source_entity_count=42,
        indexed_document_count=42,
    )
    assert snapshot.source_entity_count == 42
    assert snapshot.deleted_entity_count == 0
    raw = json.loads(snapshot.model_dump_json())
    assert raw["snapshot_id"] == "snap-2026-09-15-001"


# --- 7. Hardening: Semantic Hash, Provenance Conflicts & FQN Semantics ---


def test_content_hash_invariance_to_operational_and_sync_fields() -> None:
    """Semantic content hash must be invariant to sync timestamps and source versions."""
    time_early = datetime(2026, 9, 15, 8, 0, 0, tzinfo=UTC)
    time_later = datetime(2026, 9, 15, 8, 5, 0, tzinfo=UTC)

    table_v1 = CatalogTable(
        table_fqn="dw.sales.orders",
        service_name="dw",
        database_name="sales",
        schema_name="public",
        table_name="orders",
        sql_identifier="orders",
        description="Orders table",
        columns=[
            CatalogColumn(
                column_fqn="dw.sales.orders.id",
                column_name="id",
                data_type="BIGINT",
                is_primary_key=True,
            )
        ],
        primary_key_column_names=["id"],
        provenance=MetadataProvenance(
            source_system="pg_source",
            source_entity_id="entity-100",
            source_version="v1.0",
            source_updated_at=time_early,
            snapshot_at=time_early,
        ),
    )

    # Identical semantic metadata, but different sync/operational observation fields
    table_v2 = CatalogTable(
        table_fqn="dw.sales.orders",
        service_name="dw",
        database_name="sales",
        schema_name="public",
        table_name="orders",
        sql_identifier="orders",
        description="Orders table",
        columns=[
            CatalogColumn(
                column_fqn="dw.sales.orders.id",
                column_name="id",
                data_type="BIGINT",
                is_primary_key=True,
            )
        ],
        primary_key_column_names=["id"],
        provenance=MetadataProvenance(
            source_system="pg_source",
            source_entity_id="entity-100",
            source_version="v2.0",  # new version
            source_updated_at=time_later,  # new updated time
            snapshot_at=time_later,  # new snapshot time
        ),
    )

    # Semantic content hash MUST match for incremental change detection
    assert table_v1.compute_content_hash() == table_v2.compute_content_hash()
    assert table_v1.semantic_content_hash == table_v2.semantic_content_hash

    # Changing a semantic field (e.g. column description) must change the hash
    table_modified = CatalogTable(
        table_fqn="dw.sales.orders",
        service_name="dw",
        database_name="sales",
        schema_name="public",
        table_name="orders",
        sql_identifier="orders",
        description="Orders table",
        columns=[
            CatalogColumn(
                column_fqn="dw.sales.orders.id",
                column_name="id",
                data_type="BIGINT",
                description="Altered semantic description",
                is_primary_key=True,
            )
        ],
        primary_key_column_names=["id"],
        provenance=table_v1.provenance,
    )
    assert table_v1.compute_content_hash() != table_modified.compute_content_hash()


def test_provenance_conflict_rejection() -> None:
    """Conflicting legacy and provenance fields must raise explicit validation error."""
    now = datetime.now(UTC)
    earlier = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    # Conflict on source_entity_id
    with pytest.raises(ValidationError, match="Provenance conflict on source_entity_id"):
        CatalogTable(
            table_fqn="dw.sales.customers",
            service_name="dw",
            database_name="sales",
            schema_name="public",
            table_name="customers",
            source_entity_id="LEGACY_A",
            provenance=MetadataProvenance(
                source_system="dw",
                source_entity_id="PROVENANCE_B",
            ),
        )

    # Conflict on metadata_version
    with pytest.raises(ValidationError, match="Provenance conflict on metadata_version"):
        CatalogTable(
            table_fqn="dw.sales.customers",
            service_name="dw",
            database_name="sales",
            schema_name="public",
            table_name="customers",
            metadata_version="1.0",
            provenance=MetadataProvenance(
                source_system="dw",
                source_version="2.0",
            ),
        )

    # Conflict on updated_at
    with pytest.raises(ValidationError, match="Provenance conflict on updated_at"):
        CatalogTable(
            table_fqn="dw.sales.customers",
            service_name="dw",
            database_name="sales",
            schema_name="public",
            table_name="customers",
            updated_at=earlier,
            provenance=MetadataProvenance(
                source_system="dw",
                source_updated_at=now,
            ),
        )


def test_provenance_matching_values_accepted() -> None:
    """When legacy and provenance fields agree, accept and harmonize."""
    now = datetime.now(UTC)
    table = CatalogTable(
        table_fqn="dw.sales.customers",
        service_name="dw",
        database_name="sales",
        schema_name="public",
        table_name="customers",
        source_entity_id="MATCHING_ID",
        metadata_version="1.0",
        updated_at=now,
        provenance=MetadataProvenance(
            source_system="dw",
            source_entity_id="MATCHING_ID",
            source_version="1.0",
            source_updated_at=now,
        ),
    )
    assert table.source_entity_id == "MATCHING_ID"
    assert table.provenance is not None
    assert table.provenance.source_entity_id == "MATCHING_ID"


def test_asset_identity_deterministic_fqn_construction() -> None:
    """AssetIdentity provides deterministic T2S canonical locator construction."""
    constructed = AssetIdentity.build_canonical_fqn("pg", "analytics", "reporting", "daily_metrics")
    assert constructed == "pg.analytics.reporting.daily_metrics"

    identity = AssetIdentity.from_parts("pg", "analytics", "reporting", "daily_metrics", "view")
    assert identity.canonical_fqn == "pg.analytics.reporting.daily_metrics"
    assert identity.asset_type == "view"

    with pytest.raises(ValueError, match="Cannot build canonical FQN with empty path segments"):
        AssetIdentity.build_canonical_fqn("pg", "  ", "reporting", "daily_metrics")
