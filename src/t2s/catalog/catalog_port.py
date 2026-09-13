from typing import Protocol

from t2s.catalog.catalog_models import CatalogForeignKey, CatalogTable, MetadataSnapshot


class CatalogPort(Protocol):
    def get_table_by_fqn(self, table_fqn: str) -> CatalogTable:
        ...

    def get_tables_by_fqn(self, table_fqns: list[str]) -> list[CatalogTable]:
        ...

    def list_table_fqns(self) -> list[str]:
        ...

    def get_relationships(self, table_fqn: str) -> list[CatalogForeignKey]:
        ...

    def upsert_tables(self, catalog_tables: list[CatalogTable]) -> None:
        ...

    def delete_tables(self, table_fqns: list[str]) -> None:
        ...

    def record_metadata_snapshot(self, metadata_snapshot: MetadataSnapshot) -> None:
        ...
