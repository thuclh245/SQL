from typing import Any

from t2s.catalog.canonical_metadata import AssetIdentity, CatalogForeignKey


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
                    str(column).strip() for column in raw_constraint.get("columns") or []
                )
        return list(dict.fromkeys(name for name in primary_key_names if name))

    def map_foreign_keys(
        self,
        raw_table: dict[str, Any],
        table_fqn: str,
        service_name: str = "openmetadata",
        database_name: str = "default",
        schema_name: str = "public",
    ) -> list[CatalogForeignKey]:
        foreign_keys: list[CatalogForeignKey] = []
        for raw_constraint in raw_table.get("tableConstraints") or []:
            if not isinstance(raw_constraint, dict):
                continue
            constraint_type = str(raw_constraint.get("constraintType") or "").upper()
            if constraint_type != "FOREIGN_KEY":
                continue

            raw_from_columns = [str(col).strip() for col in raw_constraint.get("columns") or []]
            from_columns = [c for c in raw_from_columns if c]
            if not from_columns:
                continue

            raw_referred = [str(rc).strip() for rc in raw_constraint.get("referredColumns") or []]
            referred_columns = [rc for rc in raw_referred if rc]
            if not referred_columns or len(from_columns) != len(referred_columns):
                continue

            # Parse target coordinates for each referred column
            parsed_targets = [
                self._parse_referred_column(
                    ref_col,
                    default_service=service_name,
                    default_database=database_name,
                    default_schema=schema_name,
                )
                for ref_col in referred_columns
            ]

            # All referred columns in a composite FK must point to the same target table
            target_tables = {
                (t[0], t[1], t[2], t[3], t[5])  # (svc, db, sch, tbl, fqn)
                for t in parsed_targets
            }
            if len(target_tables) != 1:
                continue

            to_svc, to_db, to_sch, to_tbl, to_fqn = next(iter(target_tables))
            to_cols = [t[4] for t in parsed_targets]

            foreign_keys.append(
                CatalogForeignKey(
                    relationship_name=raw_constraint.get("name"),
                    from_table_fqn=table_fqn,
                    from_column_names=from_columns,
                    to_table_fqn=to_fqn,
                    to_column_names=to_cols,
                    to_service_name=to_svc,
                    to_database_name=to_db,
                    to_schema_name=to_sch,
                    to_table_name=to_tbl,
                    provenance="declared_foreign_key",
                )
            )
        return foreign_keys

    def _parse_referred_column(
        self,
        referred_column: str,
        default_service: str,
        default_database: str,
        default_schema: str,
    ) -> tuple[str, str, str, str, str, str]:
        """Parse referred column into (service, database, schema, table, column, table_fqn)."""
        # Split respecting potential quotes
        segments = self._split_locator(referred_column)
        if len(segments) >= 5:
            svc, db, sch, tbl, col = segments[0], segments[1], segments[2], segments[3], segments[4]
        elif len(segments) == 4:
            if segments[0].lower() == default_service.lower():
                svc, db, sch, tbl, col = (
                    default_service,
                    default_database,
                    segments[1],
                    segments[2],
                    segments[3],
                )
            else:
                svc, db, sch, tbl, col = (
                    default_service,
                    segments[0],
                    segments[1],
                    segments[2],
                    segments[3],
                )
        elif len(segments) == 3:
            svc, db, sch, tbl, col = (
                default_service,
                default_database,
                segments[0],
                segments[1],
                segments[2],
            )
        elif len(segments) == 2:
            svc, db, sch, tbl, col = (
                default_service,
                default_database,
                default_schema,
                segments[0],
                segments[1],
            )
        else:
            svc, db, sch, tbl, col = (
                default_service,
                default_database,
                default_schema,
                "unknown",
                segments[0],
            )

        canonical_tbl_fqn = AssetIdentity.build_canonical_fqn(svc, db, sch, tbl)
        return svc, db, sch, tbl, col, canonical_tbl_fqn

    def _split_locator(self, locator: str) -> list[str]:
        stripped = locator.strip()
        parts: list[str] = []
        current: list[str] = []
        in_quotes = False
        quote_char = ""

        for char in stripped:
            if char in ('"', "'"):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = ""
                else:
                    current.append(char)
            elif char == "." and not in_quotes:
                segment = "".join(current).strip()
                if segment:
                    parts.append(segment)
                current = []
            else:
                current.append(char)

        last_segment = "".join(current).strip()
        if last_segment:
            parts.append(last_segment)
        return parts or [stripped]
