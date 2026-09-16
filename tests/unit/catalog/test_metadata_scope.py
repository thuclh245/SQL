"""Unit tests for MetadataScope contract and deterministic filtering semantics."""

import pytest

from t2s.catalog.metadata_scope import MetadataScope


def test_default_empty_scope_permits_all_business_assets() -> None:
    scope = MetadataScope()
    assert scope.matches_database("analytics_db")
    assert scope.matches_schema("public")
    assert scope.matches_table("orders", "public", "analytics_db", "table")
    assert scope.matches_table("daily_summary", "public", "analytics_db", "view")


def test_database_filtering() -> None:
    scope = MetadataScope(database_names={"sales_db", "crm_db"})
    assert scope.matches_database("sales_db")
    assert scope.matches_database("crm_db")
    assert not scope.matches_database("hr_db")
    assert scope.matches_table("customers", "main", "sales_db")
    assert not scope.matches_table("customers", "main", "hr_db")


def test_schema_filtering_inclusion() -> None:
    scope = MetadataScope(schema_names={"core", "analytics"})
    assert scope.matches_schema("core")
    assert scope.matches_schema("analytics")
    assert not scope.matches_schema("raw")
    assert scope.matches_table("dim_customers", "core")
    assert not scope.matches_table("dim_customers", "raw")


def test_schema_filtering_exclusion_wins() -> None:
    scope = MetadataScope(
        schema_names={"core", "staging"},
        exclude_schemas={"staging", "tmp_*"},
    )
    assert scope.matches_schema("core")
    assert not scope.matches_schema("staging")  # Exclude wins
    assert not scope.matches_schema("tmp_scratch")
    assert scope.matches_table("users", "core")
    assert not scope.matches_table("users", "staging")


def test_table_filtering_exact_and_glob_patterns() -> None:
    scope = MetadataScope(
        include_tables={"customers", "orders", "dim_*"},
        exclude_tables={"dim_legacy", "tmp_*", "*_deprecated"},
    )
    assert scope.matches_table("customers", "public")
    assert scope.matches_table("orders", "public")
    assert scope.matches_table("dim_products", "public")
    assert not scope.matches_table("dim_legacy", "public")  # Exclude wins on conflict
    assert not scope.matches_table("tmp_orders", "public")
    assert not scope.matches_table("customers_deprecated", "public")
    assert not scope.matches_table("payments", "public")  # Not in include_tables


def test_table_filtering_scoped_fqn_pattern() -> None:
    scope = MetadataScope(
        include_tables={"analytics.daily_revenue", "public.users"},
    )
    assert scope.matches_table("daily_revenue", "analytics")
    assert scope.matches_table("users", "public")
    assert not scope.matches_table("daily_revenue", "staging")
    assert not scope.matches_table("users", "internal")


def test_asset_type_filtering() -> None:
    scope = MetadataScope(include_asset_types={"table", "view"})
    assert scope.matches_table("orders", "public", asset_type="table")
    assert scope.matches_table("v_orders", "public", asset_type="view")
    assert not scope.matches_table("mv_orders", "public", asset_type="materialized_view")


def test_case_preservation_and_unicode_support() -> None:
    scope = MetadataScope(
        include_tables={"DonnéesClients", "顧客_table", "đơn_hàng"},
        exclude_tables={"*Archive"},
    )
    assert scope.matches_table("DonnéesClients", "public")
    assert not scope.matches_table("donnéesclients", "public")  # Case sensitive
    assert scope.matches_table("顧客_table", "public")
    assert scope.matches_table("đơn_hàng", "public")
    assert not scope.matches_table("DonnéesClientsArchive", "public")  # Exclude wins


def test_empty_inclusion_sets_restrict_to_nothing() -> None:
    scope = MetadataScope(include_tables=frozenset())
    assert not scope.matches_table("customers", "public")
    assert not scope.matches_table("orders", "public")


def test_invalid_pattern_strings_raise_validation_error() -> None:
    with pytest.raises(ValueError, match="include_tables items must not be empty"):
        MetadataScope(include_tables={""})

    with pytest.raises(ValueError, match="schema_names items must not be empty"):
        MetadataScope(schema_names={"   "})
