from typing import Literal, Protocol

from pydantic import BaseModel, Field

from t2s.catalog.catalog_models import CatalogTable, MetadataSnapshot

DocumentType = Literal["table", "column"]


class CatalogSearchDocument(BaseModel):
    document_id: str
    document_type: DocumentType
    table_fqn: str
    column_fqn: str | None = None
    title: str
    searchable_text: str
    service_name: str
    database_name: str
    schema_name: str
    table_name: str
    column_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    glossary_terms: list[str] = Field(default_factory=list)
    metadata_version: str | None = None


class CatalogSearchDocumentBuilder:
    def build_search_documents(self, catalog_table: CatalogTable) -> list[CatalogSearchDocument]:
        return [
            self._build_table_document(catalog_table),
            *[
                CatalogSearchDocument(
                    document_id=f"column:{catalog_column.column_fqn}",
                    document_type="column",
                    table_fqn=catalog_table.table_fqn,
                    column_fqn=catalog_column.column_fqn,
                    title=f"{catalog_table.table_name}.{catalog_column.column_name}",
                    searchable_text=self._join_search_text(
                        [
                            catalog_column.column_fqn,
                            catalog_column.column_name,
                            catalog_column.description,
                            catalog_column.data_type,
                            *catalog_column.tags,
                            *catalog_column.glossary_terms,
                        ]
                    ),
                    service_name=catalog_table.service_name,
                    database_name=catalog_table.database_name,
                    schema_name=catalog_table.schema_name,
                    table_name=catalog_table.table_name,
                    column_name=catalog_column.column_name,
                    tags=catalog_column.tags,
                    glossary_terms=catalog_column.glossary_terms,
                    metadata_version=catalog_table.metadata_version,
                )
                for catalog_column in catalog_table.columns
            ],
        ]

    def _build_table_document(self, catalog_table: CatalogTable) -> CatalogSearchDocument:
        return CatalogSearchDocument(
            document_id=f"table:{catalog_table.table_fqn}",
            document_type="table",
            table_fqn=catalog_table.table_fqn,
            title=catalog_table.table_name,
            searchable_text=self._join_search_text(
                [
                    catalog_table.table_fqn,
                    catalog_table.table_name,
                    catalog_table.description,
                    *[catalog_column.column_name for catalog_column in catalog_table.columns],
                    *[
                        catalog_column.description
                        for catalog_column in catalog_table.columns
                        if catalog_column.description
                    ],
                    *catalog_table.tags,
                    *catalog_table.glossary_terms,
                ]
            ),
            service_name=catalog_table.service_name,
            database_name=catalog_table.database_name,
            schema_name=catalog_table.schema_name,
            table_name=catalog_table.table_name,
            tags=catalog_table.tags,
            glossary_terms=catalog_table.glossary_terms,
            metadata_version=catalog_table.metadata_version,
        )

    def _join_search_text(self, search_parts: list[str | None]) -> str:
        return "\n".join(search_part.strip() for search_part in search_parts if search_part)


class SearchIndexPort(Protocol):
    def upsert_search_documents(self, search_documents: list[CatalogSearchDocument]) -> None: ...

    def delete_search_documents_for_tables(self, table_fqns: list[str]) -> None: ...

    def record_metadata_snapshot(self, metadata_snapshot: MetadataSnapshot) -> None: ...


def build_catalog_index_mapping() -> dict[str, object]:
    return {
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "document_type": {"type": "keyword"},
                "table_fqn": {"type": "keyword"},
                "column_fqn": {"type": "keyword"},
                "title": {"type": "text"},
                "searchable_text": {"type": "text"},
                "service_name": {"type": "keyword"},
                "database_name": {"type": "keyword"},
                "schema_name": {"type": "keyword"},
                "table_name": {"type": "keyword"},
                "column_name": {"type": "keyword"},
                "tags": {"type": "keyword"},
                "glossary_terms": {"type": "keyword"},
                "metadata_version": {"type": "keyword"},
            }
        }
    }
