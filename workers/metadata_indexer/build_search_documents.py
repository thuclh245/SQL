from t2s.catalog.catalog_models import CatalogTable
from t2s.catalog.metadata_document import CatalogSearchDocument, CatalogSearchDocumentBuilder


def build_search_documents_for_tables(
    catalog_tables: list[CatalogTable],
    search_document_builder: CatalogSearchDocumentBuilder | None = None,
) -> list[CatalogSearchDocument]:
    builder = search_document_builder or CatalogSearchDocumentBuilder()
    search_documents: list[CatalogSearchDocument] = []
    for catalog_table in catalog_tables:
        search_documents.extend(builder.build_search_documents(catalog_table))
    return search_documents
