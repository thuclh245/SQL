import pytest

from t2s.errors import MetadataMappingError
from t2s.integrations.openmetadata import OpenMetadataTableMapper


def test_openmetadata_mapper_preserves_fqn_and_separate_sql_identifier() -> None:
    raw_table = {
        "id": "table-id",
        "fullyQualifiedName": "warehouse.sales.orders",
        "name": "orders",
        "version": 1.3,
        "service": {"name": "warehouse"},
        "database": {"name": "analytics"},
        "databaseSchema": {"name": "sales"},
        "description": "Customer orders",
        "extension": {"sqlIdentifier": "analytics.sales.orders"},
        "owner": {"name": "data-team"},
        "tags": [
            {"source": "Tag", "tagFQN": "Tier.Gold"},
            {"source": "Glossary", "tagFQN": "Revenue"},
        ],
        "columns": [
            {
                "name": "order_id",
                "fullyQualifiedName": "warehouse.sales.orders.order_id",
                "dataType": "BIGINT",
                "constraint": "PRIMARY_KEY",
                "tags": [{"source": "Glossary", "tagFQN": "Order ID"}],
            }
        ],
    }

    catalog_table = OpenMetadataTableMapper().map_table(raw_table)

    assert catalog_table.table_fqn == "warehouse.analytics.sales.orders"
    assert catalog_table.sql_identifier == "analytics.sales.orders"
    assert catalog_table.sql_identifier_source == "explicit"
    assert catalog_table.owner == "data-team"
    assert catalog_table.tags == ["Tier.Gold"]
    assert catalog_table.glossary_terms == ["Revenue"]
    assert catalog_table.primary_key_column_names == ["order_id"]
    assert catalog_table.columns[0].glossary_terms == ["Order ID"]


def test_openmetadata_mapper_preserves_composite_foreign_key() -> None:
    raw_table = {
        "fullyQualifiedName": "warehouse.sales.order_items",
        "name": "order_items",
        "service": {"name": "warehouse"},
        "database": {"name": "analytics"},
        "databaseSchema": {"name": "sales"},
        "columns": [
            {"name": "order_id", "dataType": "BIGINT"},
            {"name": "line_number", "dataType": "INT"},
        ],
        "tableConstraints": [
            {
                "constraintType": "PRIMARY_KEY",
                "columns": ["order_id", "line_number"],
            },
            {
                "name": "fk_order_items_orders",
                "constraintType": "FOREIGN_KEY",
                "columns": ["order_id", "line_number"],
                "referredColumns": [
                    "warehouse.sales.orders.order_id",
                    "warehouse.sales.orders.line_number",
                ],
            },
        ],
    }

    catalog_table = OpenMetadataTableMapper().map_table(raw_table)

    assert catalog_table.primary_key_column_names == ["order_id", "line_number"]
    assert len(catalog_table.foreign_keys) == 1
    foreign_key = catalog_table.foreign_keys[0]
    assert foreign_key.from_column_names == ["order_id", "line_number"]
    assert foreign_key.to_table_fqn == "warehouse.analytics.sales.orders"
    assert foreign_key.to_column_names == ["order_id", "line_number"]
    assert foreign_key.provenance == "declared_foreign_key"


def test_openmetadata_mapper_marks_missing_sql_identifier_as_unresolved() -> None:
    raw_table = {
        "fullyQualifiedName": "warehouse.analytics.sales.orders",
        "name": "orders",
        "service": {"name": "warehouse"},
        "database": {"name": "analytics"},
        "databaseSchema": {"name": "sales"},
        "columns": [{"name": "id", "dataType": "BIGINT"}],
    }

    catalog_table = OpenMetadataTableMapper().map_table(raw_table)

    assert catalog_table.sql_identifier is None
    assert catalog_table.sql_identifier_source == "unresolved"


def test_openmetadata_mapper_rejects_incomplete_table_identity() -> None:
    raw_table = {
        "fullyQualifiedName": "warehouse.analytics.orders",
        "name": "orders",
        "service": {"name": "warehouse"},
        "database": {"name": "analytics"},
        "columns": [{"name": "id", "dataType": "BIGINT"}],
    }

    with pytest.raises(MetadataMappingError, match="databaseSchema.name"):
        OpenMetadataTableMapper().map_table(raw_table)
