import threading

from t2s.catalog.catalog_models import CatalogForeignKey, CatalogTable, MetadataSnapshot
from t2s.catalog.relationship_graph import RelationshipGraph
from t2s.errors import MetadataNotFoundError


class InMemoryCatalog:
    """Thread-safe in-memory catalog storage and serving state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.catalog_tables_by_fqn: dict[str, CatalogTable] = {}
        self.metadata_snapshots: list[MetadataSnapshot] = []
        self.relationship_graph = RelationshipGraph([])
        self.active_snapshot_id: str | None = None

    def get_table_by_fqn(self, table_fqn: str) -> CatalogTable:
        with self._lock:
            try:
                return self.catalog_tables_by_fqn[table_fqn]
            except KeyError as exc:
                raise MetadataNotFoundError(f"Catalog table not found: {table_fqn}") from exc

    def get_tables_by_fqn(self, table_fqns: list[str]) -> list[CatalogTable]:
        with self._lock:
            return [self.get_table_by_fqn(table_fqn) for table_fqn in table_fqns]

    def list_table_fqns(self) -> list[str]:
        with self._lock:
            return sorted(self.catalog_tables_by_fqn)

    def get_relationships(self, table_fqn: str) -> list[CatalogForeignKey]:
        with self._lock:
            self.get_table_by_fqn(table_fqn)
            return self.relationship_graph.get_relationships(table_fqn)

    def sync_snapshot(self, tables: list[CatalogTable], snapshot_id: str) -> None:
        """Atomically swap the complete serving catalog state to match the given snapshot."""
        with self._lock:
            new_tables_by_fqn = {t.table_fqn: t for t in tables}
            new_graph = RelationshipGraph(list(new_tables_by_fqn.values()))
            self.catalog_tables_by_fqn = new_tables_by_fqn
            self.relationship_graph = new_graph
            self.active_snapshot_id = snapshot_id

    def upsert_tables(self, catalog_tables: list[CatalogTable]) -> None:
        with self._lock:
            for catalog_table in catalog_tables:
                self.catalog_tables_by_fqn[catalog_table.table_fqn] = catalog_table
            self._rebuild_relationship_graph()

    def delete_tables(self, table_fqns: list[str]) -> None:
        with self._lock:
            for table_fqn in table_fqns:
                self.catalog_tables_by_fqn.pop(table_fqn, None)
            self._rebuild_relationship_graph()

    def record_metadata_snapshot(self, metadata_snapshot: MetadataSnapshot) -> None:
        with self._lock:
            self.metadata_snapshots.append(metadata_snapshot)

    def _rebuild_relationship_graph(self) -> None:
        self.relationship_graph = RelationshipGraph(list(self.catalog_tables_by_fqn.values()))
