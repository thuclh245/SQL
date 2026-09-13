from t2s.catalog import CatalogColumn, CatalogTable
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.catalog.in_memory_search_index import InMemorySearchIndex
from workers.metadata_indexer import MetadataIndexer
from workers.metadata_indexer.sync_metadata_changes import MetadataChangeSynchronizer


class StaticMetadataSource:
    def __init__(self, catalog_tables: list[CatalogTable]) -> None:
        self.catalog_tables = catalog_tables

    def list_tables(self) -> list[CatalogTable]:
        return self.catalog_tables


def create_catalog_table(
    table_fqn: str,
    description: str = "initial description",
    column_names: list[str] | None = None,
) -> CatalogTable:
    service_name, database_name, schema_name, table_name = table_fqn.split(".")
    return CatalogTable(
        table_fqn=table_fqn,
        service_name=service_name,
        database_name=database_name,
        schema_name=schema_name,
        table_name=table_name,
        sql_identifier=f"{database_name}.{schema_name}.{table_name}",
        description=description,
        metadata_version=description,
        columns=[
            CatalogColumn(
                column_fqn=f"{table_fqn}.{column_name}",
                column_name=column_name,
                data_type="text",
            )
            for column_name in column_names or []
        ],
    )


def test_full_sync_is_idempotent_and_hydrates_by_fqn() -> None:
    catalog_table = create_catalog_table("warehouse.sales.public.orders")
    catalog = InMemoryCatalog()
    search_index = InMemorySearchIndex()
    metadata_indexer = MetadataIndexer(
        metadata_source=StaticMetadataSource([catalog_table]),
        catalog=catalog,
        search_index=search_index,
    )

    first_result = metadata_indexer.sync_full_metadata()
    second_result = metadata_indexer.sync_full_metadata()

    assert (
        first_result.metadata_snapshot.metadata_version
        == second_result.metadata_snapshot.metadata_version
    )
    assert catalog.get_table_by_fqn("warehouse.sales.public.orders") == catalog_table
    assert len(search_index.search_documents_by_id) == 1


def test_description_update_is_reflected_in_catalog_and_search_index() -> None:
    catalog = InMemoryCatalog()
    search_index = InMemorySearchIndex()
    MetadataIndexer(
        metadata_source=StaticMetadataSource(
            [create_catalog_table("warehouse.sales.public.orders")]
        ),
        catalog=catalog,
        search_index=search_index,
    ).sync_full_metadata()

    MetadataIndexer(
        metadata_source=StaticMetadataSource(
            [
                create_catalog_table(
                    "warehouse.sales.public.orders",
                    description="updated order facts",
                )
            ]
        ),
        catalog=catalog,
        search_index=search_index,
    ).sync_full_metadata()

    hydrated_table = catalog.get_table_by_fqn("warehouse.sales.public.orders")
    search_document = search_index.search_documents_by_id[
        "table:warehouse.sales.public.orders"
    ]
    assert hydrated_table.description == "updated order facts"
    assert "updated order facts" in search_document.searchable_text


def test_deleted_table_is_removed_from_catalog_and_search_index() -> None:
    catalog = InMemoryCatalog()
    search_index = InMemorySearchIndex()
    MetadataIndexer(
        metadata_source=StaticMetadataSource(
            [
                create_catalog_table("warehouse.sales.public.orders"),
                create_catalog_table("warehouse.archive.public.orders"),
            ]
        ),
        catalog=catalog,
        search_index=search_index,
    ).sync_full_metadata()

    result = MetadataIndexer(
        metadata_source=StaticMetadataSource(
            [create_catalog_table("warehouse.sales.public.orders")]
        ),
        catalog=catalog,
        search_index=search_index,
    ).sync_full_metadata()

    assert result.deleted_table_count == 1
    assert catalog.list_table_fqns() == ["warehouse.sales.public.orders"]
    assert set(search_index.search_documents_by_id) == {"table:warehouse.sales.public.orders"}


def test_full_sync_removes_search_documents_for_dropped_columns() -> None:
    table_fqn = "warehouse.sales.public.orders"
    catalog = InMemoryCatalog()
    search_index = InMemorySearchIndex()
    source = StaticMetadataSource(
        [create_catalog_table(table_fqn, column_names=["id", "old_column"])]
    )
    metadata_indexer = MetadataIndexer(source, catalog, search_index)
    metadata_indexer.sync_full_metadata()

    source.catalog_tables = [create_catalog_table(table_fqn, column_names=["id"])]
    metadata_indexer.sync_full_metadata()

    assert set(search_index.search_documents_by_id) == {
        f"table:{table_fqn}",
        f"column:{table_fqn}.id",
    }


def test_full_sync_treats_column_rename_as_delete_old_and_add_new() -> None:
    table_fqn = "warehouse.sales.public.orders"
    catalog = InMemoryCatalog()
    search_index = InMemorySearchIndex()
    source = StaticMetadataSource(
        [create_catalog_table(table_fqn, column_names=["id", "old_name"])]
    )
    metadata_indexer = MetadataIndexer(source, catalog, search_index)
    metadata_indexer.sync_full_metadata()

    source.catalog_tables = [
        create_catalog_table(table_fqn, column_names=["id", "new_name"])
    ]
    metadata_indexer.sync_full_metadata()

    assert f"column:{table_fqn}.old_name" not in search_index.search_documents_by_id
    assert f"column:{table_fqn}.new_name" in search_index.search_documents_by_id


def test_incremental_sync_replaces_changed_table_search_documents() -> None:
    table_fqn = "warehouse.sales.public.orders"
    catalog = InMemoryCatalog()
    search_index = InMemorySearchIndex()
    MetadataIndexer(
        metadata_source=StaticMetadataSource(
            [create_catalog_table(table_fqn, column_names=["id", "old_column"])]
        ),
        catalog=catalog,
        search_index=search_index,
    ).sync_full_metadata()

    MetadataChangeSynchronizer(catalog, search_index).apply_metadata_changes(
        changed_tables=[create_catalog_table(table_fqn, column_names=["id"])],
        deleted_table_fqns=[],
    )

    assert f"column:{table_fqn}.old_column" not in search_index.search_documents_by_id
