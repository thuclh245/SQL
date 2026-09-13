from t2s.catalog.catalog_models import CatalogForeignKey, CatalogTable, MetadataSnapshot
from t2s.catalog.relationship_graph import RelationshipGraph
from t2s.errors import MetadataNotFoundError


class InMemoryCatalog:
    def __init__(self) -> None:
        self.catalog_tables_by_fqn: dict[str, CatalogTable] = {}
        self.metadata_snapshots: list[MetadataSnapshot] = []
        self.relationship_graph = RelationshipGraph([])

    def get_table_by_fqn(self, table_fqn: str) -> CatalogTable:
        try:
            return self.catalog_tables_by_fqn[table_fqn]
        except KeyError as exc:
            raise MetadataNotFoundError(f"Catalog table not found: {table_fqn}") from exc

    def get_tables_by_fqn(self, table_fqns: list[str]) -> list[CatalogTable]:
        return [self.get_table_by_fqn(table_fqn) for table_fqn in table_fqns]

    def list_table_fqns(self) -> list[str]:
        return sorted(self.catalog_tables_by_fqn)

    def get_relationships(self, table_fqn: str) -> list[CatalogForeignKey]:
        self.get_table_by_fqn(table_fqn)
        return self.relationship_graph.get_relationships(table_fqn)

    def upsert_tables(self, catalog_tables: list[CatalogTable]) -> None:
        for catalog_table in catalog_tables:
            self.catalog_tables_by_fqn[catalog_table.table_fqn] = catalog_table
        self._rebuild_relationship_graph()

    def delete_tables(self, table_fqns: list[str]) -> None:
        for table_fqn in table_fqns:
            self.catalog_tables_by_fqn.pop(table_fqn, None)
        self._rebuild_relationship_graph()

    def record_metadata_snapshot(self, metadata_snapshot: MetadataSnapshot) -> None:
        self.metadata_snapshots.append(metadata_snapshot)

    def _rebuild_relationship_graph(self) -> None:
        self.relationship_graph = RelationshipGraph(list(self.catalog_tables_by_fqn.values()))
