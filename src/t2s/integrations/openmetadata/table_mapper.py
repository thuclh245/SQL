from datetime import UTC, datetime
from typing import Any

from t2s.catalog.canonical_metadata import (
    AssetIdentity,
    CatalogTable,
    MetadataProvenance,
    SqlIdentifierSource,
    TableType,
)
from t2s.errors import MetadataMappingError
from t2s.integrations.openmetadata.column_mapper import OpenMetadataColumnMapper
from t2s.integrations.openmetadata.relationship_mapper import OpenMetadataRelationshipMapper


class OpenMetadataTableMapper:
    def __init__(
        self,
        column_mapper: OpenMetadataColumnMapper | None = None,
        relationship_mapper: OpenMetadataRelationshipMapper | None = None,
        default_service_name: str = "openmetadata",
    ) -> None:
        self.column_mapper = column_mapper or OpenMetadataColumnMapper()
        self.relationship_mapper = relationship_mapper or OpenMetadataRelationshipMapper()
        self.default_service_name = default_service_name

    def map_table(self, raw_table: dict[str, Any]) -> CatalogTable:
        source_fqn = str(raw_table.get("fullyQualifiedName") or "").strip()
        table_name = str(raw_table.get("name") or raw_table.get("displayName") or "").strip()
        service_name = self._entity_name(raw_table.get("service")).strip()
        database_name = self._entity_name(raw_table.get("database")).strip()
        schema_name = self._entity_name(raw_table.get("databaseSchema")).strip()

        # Fallback to source_fqn parsing if structured entities are missing
        if source_fqn and (
            not service_name or not database_name or not schema_name or not table_name
        ):
            try:
                s_svc, s_db, s_sch, s_tbl = AssetIdentity.parse_canonical_locator(source_fqn)
                if not service_name:
                    service_name = s_svc
                if not database_name:
                    database_name = s_db
                if not schema_name:
                    schema_name = s_sch
                if not table_name:
                    table_name = s_tbl
            except ValueError:
                segments = source_fqn.split(".")
                if len(segments) >= 4:
                    if not service_name:
                        service_name = segments[0]
                    if not database_name:
                        database_name = segments[1]
                    if not schema_name:
                        schema_name = segments[2]
                    if not table_name:
                        table_name = segments[3]

        if not service_name:
            service_name = self.default_service_name

        self._validate_required_identity(
            source_fqn=source_fqn,
            service_name=service_name,
            database_name=database_name,
            schema_name=schema_name,
            table_name=table_name,
        )

        table_type = self._map_table_type(raw_table.get("tableType"))
        identity = AssetIdentity.from_parts(
            service_name=service_name,
            database_name=database_name,
            schema_name=schema_name,
            asset_name=table_name,
            asset_type=table_type,
        )
        canonical_fqn = identity.canonical_fqn

        columns = [
            self.column_mapper.map_column(raw_column, canonical_fqn, ordinal_position)
            for ordinal_position, raw_column in enumerate(raw_table.get("columns") or [], start=1)
            if isinstance(raw_column, dict)
        ]
        primary_key_column_names = self.relationship_mapper.map_primary_key_column_names(
            raw_table,
            [
                catalog_column.column_name
                for catalog_column in columns
                if catalog_column.is_primary_key
            ],
        )
        sql_identifier, sql_identifier_source = self._build_sql_identifier(raw_table)
        foreign_keys = self.relationship_mapper.map_foreign_keys(
            raw_table=raw_table,
            table_fqn=canonical_fqn,
            service_name=service_name,
            database_name=database_name,
            schema_name=schema_name,
        )

        provenance = MetadataProvenance(
            source_system="openmetadata",
            source_entity_id=self._optional_string(raw_table.get("id")),
            source_locator=source_fqn or None,
            source_version=self._optional_string(raw_table.get("version")),
            source_updated_at=self._parse_updated_at(raw_table),
        )

        # OpenMetadata 2.x renamed these to plural list-valued fields
        # (owners/domains); keep singular fallback for older servers.
        owner_val = self._entity_name(raw_table.get("owners") or raw_table.get("owner")) or None
        domain_val = self._entity_name(raw_table.get("domains") or raw_table.get("domain")) or None

        return CatalogTable(
            table_fqn=canonical_fqn,
            service_name=service_name,
            database_name=database_name,
            schema_name=schema_name,
            table_name=table_name,
            table_type=table_type,
            description=raw_table.get("description"),
            sql_identifier=sql_identifier,
            sql_identifier_source=sql_identifier_source,
            columns=columns,
            primary_key_column_names=primary_key_column_names,
            foreign_keys=foreign_keys,
            tags=self.column_mapper._extract_tag_labels(raw_table, source_name="Tag"),
            glossary_terms=self.column_mapper._extract_tag_labels(
                raw_table,
                source_name="Glossary",
            ),
            owner=owner_val,
            domain=domain_val,
            provenance=provenance,
        )

    def _validate_required_identity(
        self,
        source_fqn: str,
        service_name: str,
        database_name: str,
        schema_name: str,
        table_name: str,
    ) -> None:
        missing_fields = [
            field_name
            for field_name, field_value in [
                ("service.name", service_name),
                ("database.name", database_name),
                ("databaseSchema.name", schema_name),
                ("name", table_name),
            ]
            if not field_value.strip()
        ]
        if missing_fields:
            table_identity = source_fqn or table_name or "<unknown>"
            joined_missing_fields = ", ".join(missing_fields)
            raise MetadataMappingError(
                f"OpenMetadata table {table_identity} is missing required identity fields: "
                f"{joined_missing_fields}."
            )

    def _entity_name(self, raw_entity: object) -> str:
        if isinstance(raw_entity, list):
            return self._entity_name(raw_entity[0]) if raw_entity else ""
        if isinstance(raw_entity, dict):
            value = (
                raw_entity.get("name")
                or raw_entity.get("fullyQualifiedName")
                or raw_entity.get("displayName")
                or ""
            )
            return str(value)
        if raw_entity is None:
            return ""
        return str(raw_entity)

    def _optional_string(self, raw_value: object) -> str | None:
        if raw_value is None:
            return None
        return str(raw_value)

    def _map_table_type(self, raw_table_type: object) -> TableType:
        normalized_table_type = str(raw_table_type or "").lower()
        if normalized_table_type in {"regular", "view", "materialized_view", "external"}:
            return normalized_table_type  # type: ignore[return-value]
        return "unknown"

    def _build_sql_identifier(
        self,
        raw_table: dict[str, Any],
    ) -> tuple[str | None, SqlIdentifierSource]:
        raw_extension = raw_table.get("extension")
        extension: dict[str, Any] = raw_extension if isinstance(raw_extension, dict) else {}
        explicit_identifier = raw_table.get("sqlIdentifier") or extension.get("sqlIdentifier")
        if explicit_identifier:
            return str(explicit_identifier), "explicit"
        return None, "unresolved"

    def _parse_updated_at(self, raw_table: dict[str, Any]) -> datetime | None:
        updated_at = raw_table.get("updatedAt")
        if isinstance(updated_at, int | float):
            return datetime.fromtimestamp(updated_at / 1000, tz=UTC)
        return None
