from t2s.catalog import CatalogColumn, CatalogSearchDocumentBuilder, CatalogTable


def test_search_documents_preserve_canonical_fqn_and_structured_fields() -> None:
    catalog_table = CatalogTable(
        table_fqn="warehouse.sales.orders",
        service_name="warehouse",
        database_name="sales",
        schema_name="public",
        table_name="orders",
        sql_identifier="sales.public.orders",
        description="Customer orders",
        columns=[
            CatalogColumn(
                column_fqn="warehouse.sales.orders.order_id",
                column_name="order_id",
                data_type="BIGINT",
                description="Stable order identifier",
                is_primary_key=True,
            )
        ],
        metadata_version="1.2",
    )

    search_documents = CatalogSearchDocumentBuilder().build_search_documents(catalog_table)

    assert [document.document_type for document in search_documents] == ["table", "column"]
    assert search_documents[0].table_fqn == "warehouse.sales.orders"
    assert search_documents[0].table_name == "orders"
    assert "Stable order identifier" in search_documents[0].searchable_text
    assert search_documents[1].column_fqn == "warehouse.sales.orders.order_id"


def test_duplicate_table_short_names_keep_distinct_document_ids() -> None:
    first_table = CatalogTable(
        table_fqn="warehouse.sales.orders",
        service_name="warehouse",
        database_name="sales",
        schema_name="public",
        table_name="orders",
        sql_identifier="sales.public.orders",
    )
    second_table = CatalogTable(
        table_fqn="warehouse.archive.orders",
        service_name="warehouse",
        database_name="archive",
        schema_name="public",
        table_name="orders",
        sql_identifier="archive.public.orders",
    )

    first_document = CatalogSearchDocumentBuilder().build_search_documents(first_table)[0]
    second_document = CatalogSearchDocumentBuilder().build_search_documents(second_table)[0]

    assert first_document.title == second_document.title == "orders"
    assert first_document.document_id != second_document.document_id
    assert first_document.table_fqn != second_document.table_fqn
