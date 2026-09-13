from t2s.catalog.catalog_models import CatalogTable
from t2s.catalog.catalog_port import CatalogPort
from t2s.catalog.metadata_document import SearchIndexPort
from workers.metadata_indexer.build_search_documents import build_search_documents_for_tables


class MetadataChangeSynchronizer:
    def __init__(self, catalog: CatalogPort, search_index: SearchIndexPort) -> None:
        self.catalog = catalog
        self.search_index = search_index

    def apply_metadata_changes(
        self,
        changed_tables: list[CatalogTable],
        deleted_table_fqns: list[str],
    ) -> None:
        changed_table_fqns = [catalog_table.table_fqn for catalog_table in changed_tables]
        self.catalog.delete_tables(deleted_table_fqns)
        self.search_index.delete_search_documents_for_tables(
            [*deleted_table_fqns, *changed_table_fqns]
        )
        self.catalog.upsert_tables(changed_tables)
        self.search_index.upsert_search_documents(build_search_documents_for_tables(changed_tables))
