import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from t2s.catalog.catalog_models import CatalogTable, MetadataSnapshot
from t2s.catalog.catalog_port import CatalogPort
from t2s.catalog.metadata_document import SearchIndexPort
from workers.metadata_indexer.build_search_documents import build_search_documents_for_tables


class MetadataSourcePort(Protocol):
    def list_tables(self) -> list[CatalogTable]:
        ...


@dataclass(frozen=True)
class MetadataIndexSyncResult:
    metadata_snapshot: MetadataSnapshot
    upserted_table_count: int
    deleted_table_count: int
    indexed_document_count: int


class MetadataIndexer:
    def __init__(
        self,
        metadata_source: MetadataSourcePort,
        catalog: CatalogPort,
        search_index: SearchIndexPort,
        source_name: str = "openmetadata",
    ) -> None:
        self.metadata_source = metadata_source
        self.catalog = catalog
        self.search_index = search_index
        self.source_name = source_name

    def sync_full_metadata(self) -> MetadataIndexSyncResult:
        catalog_tables = sorted(
            self.metadata_source.list_tables(),
            key=lambda catalog_table: catalog_table.table_fqn,
        )
        source_table_fqns = {catalog_table.table_fqn for catalog_table in catalog_tables}
        deleted_table_fqns = [
            table_fqn
            for table_fqn in self.catalog.list_table_fqns()
            if table_fqn not in source_table_fqns
        ]
        search_documents = build_search_documents_for_tables(catalog_tables)
        metadata_version = self._build_metadata_version(catalog_tables)
        metadata_snapshot = MetadataSnapshot(
            snapshot_id=f"{self.source_name}:{metadata_version}",
            metadata_version=metadata_version,
            source_name=self.source_name,
            source_entity_count=len(catalog_tables),
            indexed_document_count=len(search_documents),
            deleted_entity_count=len(deleted_table_fqns),
            sync_error_count=0,
        )

        self.catalog.delete_tables(deleted_table_fqns)
        self.search_index.delete_search_documents_for_tables(
            [
                *deleted_table_fqns,
                *[catalog_table.table_fqn for catalog_table in catalog_tables],
            ]
        )
        self.catalog.upsert_tables(catalog_tables)
        self.search_index.upsert_search_documents(search_documents)
        self.catalog.record_metadata_snapshot(metadata_snapshot)
        self.search_index.record_metadata_snapshot(metadata_snapshot)

        return MetadataIndexSyncResult(
            metadata_snapshot=metadata_snapshot,
            upserted_table_count=len(catalog_tables),
            deleted_table_count=len(deleted_table_fqns),
            indexed_document_count=len(search_documents),
        )

    def _build_metadata_version(self, catalog_tables: list[CatalogTable]) -> str:
        version_payload = [
            {
                "table_fqn": catalog_table.table_fqn,
                "metadata_version": catalog_table.metadata_version,
                "updated_at": catalog_table.updated_at.isoformat()
                if catalog_table.updated_at
                else None,
                "column_fqns": [
                    catalog_column.column_fqn for catalog_column in catalog_table.columns
                ],
            }
            for catalog_table in catalog_tables
        ]
        serialized_payload = json.dumps(version_payload, sort_keys=True)
        return hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()[:16]
