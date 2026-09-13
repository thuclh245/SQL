from t2s.catalog.catalog_models import CatalogForeignKey, CatalogTable

RelationshipKey = tuple[str, str, tuple[str, ...], tuple[str, ...]]


class RelationshipGraph:
    def __init__(self, catalog_tables: list[CatalogTable]) -> None:
        self.relationships_by_table_fqn: dict[str, list[CatalogForeignKey]] = {}
        relationship_keys_by_table_fqn: dict[str, set[RelationshipKey]] = {}
        for catalog_table in catalog_tables:
            self.relationships_by_table_fqn.setdefault(catalog_table.table_fqn, [])
            for foreign_key in catalog_table.foreign_keys:
                relationship_key = (
                    foreign_key.from_table_fqn,
                    foreign_key.to_table_fqn,
                    tuple(foreign_key.from_column_names),
                    tuple(foreign_key.to_column_names),
                )
                for table_fqn in {foreign_key.from_table_fqn, foreign_key.to_table_fqn}:
                    relationship_keys = relationship_keys_by_table_fqn.setdefault(
                        table_fqn,
                        set(),
                    )
                    if relationship_key not in relationship_keys:
                        self.relationships_by_table_fqn.setdefault(table_fqn, []).append(
                            foreign_key
                        )
                        relationship_keys.add(relationship_key)

    def get_relationships(self, table_fqn: str) -> list[CatalogForeignKey]:
        return self.relationships_by_table_fqn.get(table_fqn, [])
