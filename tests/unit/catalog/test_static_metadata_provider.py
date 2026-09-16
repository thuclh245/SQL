"""Unit tests for StaticMetadataProvider."""

import json
from pathlib import Path

import pytest

from t2s.catalog.canonical_metadata import CatalogColumn, CatalogTable
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.static_metadata_provider import StaticMetadataProvider
from t2s.errors.application_errors import ConfigurationError, MetadataMappingError


def _create_sample_catalog_file(tmp_path: Path) -> Path:
    data = [
        {
            "table_fqn": "service_a.db_a.schema_1.products",
            "service_name": "service_a",
            "database_name": "db_a",
            "schema_name": "schema_1",
            "table_name": "products",
            "sql_identifier": "products",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": "service_a.db_a.schema_1.products.id",
                    "column_name": "id",
                    "data_type": "INTEGER",
                    "is_primary_key": True,
                    "ordinal_position": 1,
                },
                {
                    "column_fqn": "service_a.db_a.schema_1.products.name",
                    "column_name": "name",
                    "data_type": "TEXT",
                    "ordinal_position": 2,
                },
            ],
            "primary_key_column_names": ["id"],
        },
        {
            "table_fqn": "service_a.db_a.schema_1.categories",
            "service_name": "service_a",
            "database_name": "db_a",
            "schema_name": "schema_1",
            "table_name": "categories",
            "sql_identifier": "categories",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": "service_a.db_a.schema_1.categories.id",
                    "column_name": "id",
                    "data_type": "INTEGER",
                    "is_primary_key": True,
                    "ordinal_position": 1,
                },
            ],
            "primary_key_column_names": ["id"],
        },
    ]
    path = tmp_path / "catalog_tables.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_static_provider_source_system(tmp_path: Path) -> None:
    catalog_path = _create_sample_catalog_file(tmp_path)
    provider = StaticMetadataProvider(catalog_tables_path=catalog_path)
    assert provider.source_system == "static"


def test_static_provider_fetch_all_tables(tmp_path: Path) -> None:
    catalog_path = _create_sample_catalog_file(tmp_path)
    provider = StaticMetadataProvider(catalog_tables_path=catalog_path)
    tables = provider.fetch_metadata()

    assert len(tables) == 2
    # Deterministic alphabetical ordering by table_fqn: categories comes before products
    assert tables[0].table_name == "categories"
    assert tables[1].table_name == "products"
    assert isinstance(tables[0], CatalogTable)


def test_static_provider_with_metadata_scope(tmp_path: Path) -> None:
    catalog_path = _create_sample_catalog_file(tmp_path)
    provider = StaticMetadataProvider(catalog_tables_path=catalog_path)

    scope = MetadataScope(include_tables={"products"})
    tables = provider.fetch_metadata(scope=scope)

    assert len(tables) == 1
    assert tables[0].table_name == "products"


def test_static_provider_preloaded_tables() -> None:
    table = CatalogTable(
        table_fqn="srv.db.sch.users",
        service_name="srv",
        database_name="db",
        schema_name="sch",
        table_name="users",
        columns=[
            CatalogColumn(
                column_fqn="srv.db.sch.users.id",
                column_name="id",
                data_type="INTEGER",
                ordinal_position=1,
            )
        ],
    )
    provider = StaticMetadataProvider(tables=[table])
    tables = provider.fetch_metadata()
    assert len(tables) == 1
    assert tables[0].table_fqn == "srv.db.sch.users"


def test_static_provider_missing_arguments_raises_configuration_error() -> None:
    with pytest.raises(
        ConfigurationError, match="requires either 'catalog_tables_path' or 'tables'"
    ):
        StaticMetadataProvider()


def test_static_provider_nonexistent_file_raises_configuration_error(tmp_path: Path) -> None:
    provider = StaticMetadataProvider(catalog_tables_path=tmp_path / "missing.json")
    with pytest.raises(ConfigurationError, match="does not exist"):
        provider.fetch_metadata()


def test_static_provider_malformed_json_raises_mapping_error(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{invalid json", encoding="utf-8")
    provider = StaticMetadataProvider(catalog_tables_path=bad_file)
    with pytest.raises(MetadataMappingError, match="Failed to parse"):
        provider.fetch_metadata()


def test_static_provider_invalid_table_invariants_raises_mapping_error(tmp_path: Path) -> None:
    bad_data = [
        {
            "table_fqn": "srv.db.sch.invalid",
            "service_name": "srv",
            "database_name": "db",
            "schema_name": "sch",
            "table_name": "invalid",
            "columns": [
                {
                    "column_fqn": "srv.db.sch.invalid.col_a",
                    "column_name": "col_a",
                    "data_type": "TEXT",
                }
            ],
            "primary_key_column_names": ["non_existent_col"],
        }
    ]
    bad_file = tmp_path / "invalid_invariants.json"
    bad_file.write_text(json.dumps(bad_data), encoding="utf-8")
    provider = StaticMetadataProvider(catalog_tables_path=bad_file)
    with pytest.raises(MetadataMappingError, match="references undefined columns"):
        provider.fetch_metadata()
