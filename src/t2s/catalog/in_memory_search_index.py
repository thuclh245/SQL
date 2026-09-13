from t2s.catalog.catalog_models import MetadataSnapshot
from t2s.catalog.metadata_document import CatalogSearchDocument


class InMemorySearchIndex:
    def __init__(self) -> None:
        self.search_documents_by_id: dict[str, CatalogSearchDocument] = {}
        self.metadata_snapshots: list[MetadataSnapshot] = []

    def upsert_search_documents(self, search_documents: list[CatalogSearchDocument]) -> None:
        for search_document in search_documents:
            self.search_documents_by_id[search_document.document_id] = search_document

    def delete_search_documents_for_tables(self, table_fqns: list[str]) -> None:
        table_fqns_to_delete = set(table_fqns)
        for document_id, search_document in list(self.search_documents_by_id.items()):
            if search_document.table_fqn in table_fqns_to_delete:
                del self.search_documents_by_id[document_id]

    def record_metadata_snapshot(self, metadata_snapshot: MetadataSnapshot) -> None:
        self.metadata_snapshots.append(metadata_snapshot)
