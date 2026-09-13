from t2s.catalog import CatalogForeignKey, CatalogTable
from t2s.catalog.in_memory_catalog import InMemoryCatalog


def test_catalog_relationship_lookup_returns_outgoing_and_incoming_foreign_keys() -> None:
    orders_to_customers = CatalogForeignKey(
        relationship_name="fk_orders_customers",
        from_table_fqn="warehouse.sales.public.orders",
        from_column_names=["customer_id"],
        to_table_fqn="warehouse.sales.public.customers",
        to_column_names=["id"],
    )
    catalog = InMemoryCatalog()
    catalog.upsert_tables(
        [
            catalog_table("warehouse.sales.public.orders", [orders_to_customers]),
            catalog_table("warehouse.sales.public.customers", []),
        ]
    )

    assert catalog.get_relationships("warehouse.sales.public.orders") == [
        orders_to_customers
    ]
    assert catalog.get_relationships("warehouse.sales.public.customers") == [
        orders_to_customers
    ]


def test_catalog_relationship_lookup_does_not_duplicate_same_relationship() -> None:
    orders_to_customers = CatalogForeignKey(
        relationship_name="fk_orders_customers",
        from_table_fqn="warehouse.sales.public.orders",
        from_column_names=["customer_id"],
        to_table_fqn="warehouse.sales.public.customers",
        to_column_names=["id"],
    )
    catalog = InMemoryCatalog()
    catalog.upsert_tables([catalog_table("warehouse.sales.public.orders", [orders_to_customers])])

    assert catalog.get_relationships("warehouse.sales.public.orders") == [
        orders_to_customers
    ]


def test_catalog_relationship_lookup_supports_multiple_relationships() -> None:
    orders_to_customers = CatalogForeignKey(
        relationship_name="fk_orders_customers",
        from_table_fqn="warehouse.sales.public.orders",
        from_column_names=["customer_id"],
        to_table_fqn="warehouse.sales.public.customers",
        to_column_names=["id"],
    )
    orders_to_regions = CatalogForeignKey(
        relationship_name="fk_orders_regions",
        from_table_fqn="warehouse.sales.public.orders",
        from_column_names=["region_id"],
        to_table_fqn="warehouse.sales.public.regions",
        to_column_names=["id"],
    )
    catalog = InMemoryCatalog()
    catalog.upsert_tables(
        [
            catalog_table(
                "warehouse.sales.public.orders",
                [orders_to_customers, orders_to_regions],
            ),
            catalog_table("warehouse.sales.public.customers", []),
            catalog_table("warehouse.sales.public.regions", []),
        ]
    )

    assert catalog.get_relationships("warehouse.sales.public.orders") == [
        orders_to_customers,
        orders_to_regions,
    ]
    assert catalog.get_relationships("warehouse.sales.public.customers") == [
        orders_to_customers
    ]
    assert catalog.get_relationships("warehouse.sales.public.regions") == [
        orders_to_regions
    ]


def catalog_table(table_fqn: str, foreign_keys: list[CatalogForeignKey]) -> CatalogTable:
    service_name, database_name, schema_name, table_name = table_fqn.split(".")
    return CatalogTable(
        table_fqn=table_fqn,
        service_name=service_name,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
        sql_identifier=f"{database_name}.{schema_name}.{table_name}",
        sql_identifier_source="explicit",
        foreign_keys=foreign_keys,
    )
