from typing import Any

from t2s.catalog.catalog_models import CatalogForeignKey


class OpenMetadataRelationshipMapper:
    def map_primary_key_column_names(
        self,
        raw_table: dict[str, Any],
        column_primary_key_names: list[str],
    ) -> list[str]:
        primary_key_names = list(column_primary_key_names)
        for raw_constraint in raw_table.get("tableConstraints") or []:
            if not isinstance(raw_constraint, dict):
                continue
            constraint_type = str(raw_constraint.get("constraintType") or "").upper()
            if constraint_type == "PRIMARY_KEY":
                primary_key_names.extend(
                    str(column) for column in raw_constraint.get("columns") or []
                )
        return list(dict.fromkeys(primary_key_names))

    def map_foreign_keys(
        self,
        raw_table: dict[str, Any],
        table_fqn: str,
    ) -> list[CatalogForeignKey]:
        foreign_keys: list[CatalogForeignKey] = []
        for raw_constraint in raw_table.get("tableConstraints") or []:
            if not isinstance(raw_constraint, dict):
                continue
            constraint_type = str(raw_constraint.get("constraintType") or "").upper()
            if constraint_type != "FOREIGN_KEY":
                continue
            referred_columns = [
                str(referred_column)
                for referred_column in raw_constraint.get("referredColumns") or []
            ]
            to_table_fqns = {
                self._table_fqn_from_column_fqn(referred_column)
                for referred_column in referred_columns
            }
            if len(to_table_fqns) != 1:
                continue
            foreign_keys.append(
                CatalogForeignKey(
                    relationship_name=raw_constraint.get("name"),
                    from_table_fqn=table_fqn,
                    from_column_names=[
                        str(column) for column in raw_constraint.get("columns") or []
                    ],
                    to_table_fqn=next(iter(to_table_fqns)),
                    to_column_names=[
                        self._column_name_from_column_fqn(referred_column)
                        for referred_column in referred_columns
                    ],
                    provenance="declared_foreign_key",
                )
            )
        return foreign_keys

    def _table_fqn_from_column_fqn(self, column_fqn: str) -> str:
        return ".".join(column_fqn.split(".")[:-1])

    def _column_name_from_column_fqn(self, column_fqn: str) -> str:
        return column_fqn.split(".")[-1]
