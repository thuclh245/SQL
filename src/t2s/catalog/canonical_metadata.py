"""Canonical Metadata Model Foundation.

Establishes provider-agnostic, domain-first metadata contracts for data assets,
columns, structural constraints (PK/FK), business semantics, and provenance.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AssetType = Literal["table", "regular", "view", "materialized_view", "external", "unknown"]
TableType = AssetType
SqlIdentifierSource = Literal["explicit", "resolved", "unresolved"]
RelationshipProvenance = Literal[
    "declared_foreign_key",
    "declared_primary_key",
    "inferred_foreign_key",
]


class AssetIdentity(BaseModel):
    """Structured identity for a catalog data asset in T2S.

    Semantic Contract:
    - `canonical_fqn`: The deterministic T2S-internal canonical locator
      (`<service>.<database>.<schema>.<asset>`) used for grounding, relationship
      edges, and cache indexing across all metadata providers.
    - Source-specific external locators (such as OpenMetadata REST FQN, PostgreSQL
      catalog OID, or cloud ARN) belong in `MetadataProvenance.source_entity_id`,
      preventing provider-specific namespaces from fragmenting T2S identity.
    """

    model_config = ConfigDict(frozen=True)

    service_name: str
    database_name: str
    schema_name: str
    asset_name: str
    asset_type: AssetType = "table"
    canonical_fqn: str

    @classmethod
    def build_canonical_fqn(
        cls,
        service_name: str,
        database_name: str,
        schema_name: str,
        asset_name: str,
    ) -> str:
        """Deterministic T2S canonical locator construction."""
        parts = [
            service_name.strip(),
            database_name.strip(),
            schema_name.strip(),
            asset_name.strip(),
        ]
        if any(not p for p in parts):
            raise ValueError("Cannot build canonical FQN with empty path segments.")
        return ".".join(parts)

    @classmethod
    def from_parts(
        cls,
        service_name: str,
        database_name: str,
        schema_name: str,
        asset_name: str,
        asset_type: AssetType = "table",
    ) -> "AssetIdentity":
        """Construct an AssetIdentity with a deterministically generated canonical FQN."""
        fqn = cls.build_canonical_fqn(service_name, database_name, schema_name, asset_name)
        return cls(
            service_name=service_name,
            database_name=database_name,
            schema_name=schema_name,
            asset_name=asset_name,
            asset_type=asset_type,
            canonical_fqn=fqn,
        )

    @classmethod
    def parse_canonical_locator(cls, locator: str) -> tuple[str, str, str, str]:
        """Safely parse a canonical locator into (service, database, schema, asset).

        Handles quoted segments (e.g. `svc.db."complex.schema".tbl`) and ensures
        exactly 4 path segments are resolved.
        """
        stripped = locator.strip()
        if not stripped:
            raise ValueError("Cannot parse empty canonical locator.")

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
                if not segment:
                    raise ValueError(f"Invalid canonical locator with empty segment: '{locator}'")
                parts.append(segment)
                current = []
            else:
                current.append(char)

        last_segment = "".join(current).strip()
        if not last_segment:
            raise ValueError(f"Invalid canonical locator with empty trailing segment: '{locator}'")
        parts.append(last_segment)

        if len(parts) != 4:
            raise ValueError(
                f"Canonical locator '{locator}' must contain exactly 4 segments "
                f"(service.database.schema.asset), got {len(parts)} segments."
            )
        return parts[0], parts[1], parts[2], parts[3]

    @field_validator(
        "service_name",
        "database_name",
        "schema_name",
        "asset_name",
        "canonical_fqn",
    )
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Asset identity text fields must not be empty or whitespace-only.")
        return stripped


class MetadataProvenance(BaseModel):
    """Provider-neutral provenance and freshness metadata."""

    model_config = ConfigDict(frozen=True)

    source_system: str
    source_entity_id: str | None = None
    source_version: str | None = None
    source_updated_at: datetime | None = None
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("source_system")
    @classmethod
    def validate_source_system(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Metadata provenance source_system must not be empty.")
        return stripped


class CatalogColumn(BaseModel):
    """Canonical representation of a table or view column."""

    model_config = ConfigDict(frozen=True)

    column_fqn: str
    column_name: str
    data_type: str
    native_type: str | None = None
    description: str | None = None
    is_nullable: bool | None = None
    is_primary_key: bool = False
    ordinal_position: int | None = None
    tags: list[str] = Field(default_factory=list)
    glossary_terms: list[str] = Field(default_factory=list)

    @field_validator("column_fqn", "column_name", "data_type")
    @classmethod
    def validate_required_text_is_not_empty(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Catalog column required text fields must not be empty.")
        return stripped_value

    @field_validator("ordinal_position")
    @classmethod
    def validate_ordinal_position(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("Column ordinal position must be a positive integer (>= 1).")
        return value

    @field_validator("tags", "glossary_terms")
    @classmethod
    def deduplicate_labels(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v.strip()]
        return list(dict.fromkeys(cleaned))

    @property
    def effective_native_type(self) -> str:
        """Return native type if available, otherwise general data type."""
        return self.native_type or self.data_type


class CatalogForeignKey(BaseModel):
    """Declared structural foreign key constraint between tables."""

    model_config = ConfigDict(frozen=True)

    relationship_name: str | None = None
    from_table_fqn: str
    from_column_names: list[str]
    to_table_fqn: str
    to_column_names: list[str]
    provenance: RelationshipProvenance = "declared_foreign_key"
    to_service_name: str | None = None
    to_database_name: str | None = None
    to_schema_name: str | None = None
    to_table_name: str | None = None

    @field_validator("from_table_fqn", "to_table_fqn")
    @classmethod
    def validate_table_fqn_is_not_empty(cls, table_fqn: str) -> str:
        stripped_table_fqn = table_fqn.strip()
        if not stripped_table_fqn:
            raise ValueError("Foreign key table FQNs must not be empty.")
        return stripped_table_fqn

    @field_validator("from_column_names", "to_column_names")
    @classmethod
    def validate_columns_list(cls, columns: list[str]) -> list[str]:
        if not columns:
            raise ValueError("Foreign key column lists must not be empty.")
        cleaned = [c.strip() for c in columns]
        if any(not c for c in cleaned):
            raise ValueError("Foreign key column names must not be empty or whitespace-only.")
        return cleaned

    @model_validator(mode="after")
    def validate_foreign_key_cardinality(self) -> "CatalogForeignKey":
        if len(self.from_column_names) != len(self.to_column_names):
            raise ValueError(
                f"Foreign key column cardinality mismatch: from_column_names has "
                f"{len(self.from_column_names)} column(s) while to_column_names has "
                f"{len(self.to_column_names)} column(s)."
            )
        return self


class CatalogTable(BaseModel):
    """Canonical domain model representing a relational table or view asset."""

    model_config = ConfigDict(frozen=True)

    table_fqn: str
    service_name: str
    database_name: str
    schema_name: str
    table_name: str
    table_type: TableType = "unknown"
    description: str | None = None
    sql_identifier: str | None = None
    sql_identifier_source: SqlIdentifierSource = "unresolved"
    columns: list[CatalogColumn] = Field(default_factory=list)
    primary_key_column_names: list[str] = Field(default_factory=list)
    foreign_keys: list[CatalogForeignKey] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    glossary_terms: list[str] = Field(default_factory=list)
    owner: str | None = None
    domain: str | None = None
    provenance: MetadataProvenance | None = None
    source_entity_id: str | None = None
    metadata_version: str | None = None
    updated_at: datetime | None = None

    @field_validator(
        "table_fqn",
        "service_name",
        "database_name",
        "schema_name",
        "table_name",
    )
    @classmethod
    def validate_required_text_is_not_empty(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Catalog table required text fields must not be empty.")
        return stripped_value

    @field_validator("sql_identifier")
    @classmethod
    def validate_sql_identifier_is_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Catalog table SQL identifier must not be empty when provided.")
        return stripped_value

    @field_validator("tags", "glossary_terms")
    @classmethod
    def deduplicate_labels(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("primary_key_column_names")
    @classmethod
    def deduplicate_primary_keys(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v.strip()]
        return list(dict.fromkeys(cleaned))

    @model_validator(mode="before")
    @classmethod
    def harmonize_provenance_and_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        prov = data.get("provenance")
        legacy_entity_id = data.get("source_entity_id")
        legacy_version = data.get("metadata_version")
        legacy_updated_at = data.get("updated_at")

        if prov is not None:
            prov_entity_id = (
                prov.source_entity_id
                if isinstance(prov, MetadataProvenance)
                else prov.get("source_entity_id")
                if isinstance(prov, dict)
                else None
            )
            prov_version = (
                prov.source_version
                if isinstance(prov, MetadataProvenance)
                else prov.get("source_version")
                if isinstance(prov, dict)
                else None
            )
            prov_updated_at = (
                prov.source_updated_at
                if isinstance(prov, MetadataProvenance)
                else prov.get("source_updated_at")
                if isinstance(prov, dict)
                else None
            )

            if legacy_entity_id is not None and prov_entity_id is not None:
                if str(legacy_entity_id) != str(prov_entity_id):
                    raise ValueError(
                        f"Provenance conflict on source_entity_id: legacy value "
                        f"'{legacy_entity_id}' conflicts with provenance value '{prov_entity_id}'."
                    )
            if legacy_version is not None and prov_version is not None:
                if str(legacy_version) != str(prov_version):
                    raise ValueError(
                        f"Provenance conflict on metadata_version: legacy value "
                        f"'{legacy_version}' conflicts with provenance value '{prov_version}'."
                    )
            if legacy_updated_at is not None and prov_updated_at is not None:
                if legacy_updated_at != prov_updated_at:
                    raise ValueError(
                        f"Provenance conflict on updated_at: legacy value '{legacy_updated_at}' "
                        f"conflicts with provenance value '{prov_updated_at}'."
                    )

            if legacy_entity_id is None and prov_entity_id is not None:
                data["source_entity_id"] = prov_entity_id
            if legacy_version is None and prov_version is not None:
                data["metadata_version"] = prov_version
            if legacy_updated_at is None and prov_updated_at is not None:
                data["updated_at"] = prov_updated_at

        elif legacy_entity_id or legacy_version or legacy_updated_at:
            service_name = data.get("service_name") or "unknown"
            data["provenance"] = MetadataProvenance(
                source_system=str(service_name),
                source_entity_id=str(legacy_entity_id) if legacy_entity_id is not None else None,
                source_version=str(legacy_version) if legacy_version is not None else None,
                source_updated_at=legacy_updated_at,
            )
        return data

    @model_validator(mode="after")
    def validate_table_structural_invariants(self) -> "CatalogTable":
        col_names = [col.column_name for col in self.columns]
        if len(col_names) != len(set(col_names)):
            duplicates = {name for name in col_names if col_names.count(name) > 1}
            raise ValueError(
                f"Catalog table '{self.table_fqn}' contains duplicate column definitions: "
                f"{duplicates}."
            )

        if self.columns:
            declared_columns = set(col_names)
            missing_pk_cols = [
                pk for pk in self.primary_key_column_names if pk not in declared_columns
            ]
            if missing_pk_cols:
                raise ValueError(
                    f"Catalog table '{self.table_fqn}' primary key references undefined columns: "
                    f"{missing_pk_cols}."
                )

            for fk in self.foreign_keys:
                if fk.from_table_fqn == self.table_fqn:
                    missing_fk_cols = [
                        col for col in fk.from_column_names if col not in declared_columns
                    ]
                    if missing_fk_cols:
                        rel_name = fk.relationship_name or "unnamed"
                        raise ValueError(
                            f"Catalog table '{self.table_fqn}' foreign key '{rel_name}' "
                            f"references undefined local columns: {missing_fk_cols}."
                        )
        return self

    @property
    def asset_identity(self) -> AssetIdentity:
        """Structured asset identity value object."""
        return AssetIdentity(
            service_name=self.service_name,
            database_name=self.database_name,
            schema_name=self.schema_name,
            asset_name=self.table_name,
            asset_type=self.table_type,
            canonical_fqn=self.table_fqn,
        )

    def get_column(self, column_name: str) -> CatalogColumn | None:
        """Lookup a column by exact or case-insensitive name."""
        for col in self.columns:
            if col.column_name == column_name:
                return col
        normalized = column_name.strip().lower()
        for col in self.columns:
            if col.column_name.lower() == normalized:
                return col
        return None

    def compute_content_hash(self) -> str:
        """Compute a deterministic SHA-256 digest of semantic table metadata.

        Contract:
        - Hashes semantic schema elements: identity, columns, types, descriptions,
          constraints (PK/FK), business semantics (tags, glossary, domain, owner),
          and executable SQL identifiers.
        - Excludes operational observation and freshness fields (`provenance`,
          `source_entity_id`, `metadata_version`, `updated_at`), guaranteeing that
          change detection is invariant to sync timestamps or source versions.
        """
        serialized = self.model_dump_json(
            exclude={"provenance", "source_entity_id", "metadata_version", "updated_at"}
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def semantic_content_hash(self) -> str:
        """Alias for compute_content_hash representing pure semantic change detection."""
        return self.compute_content_hash()


class MetadataSnapshot(BaseModel):
    """Metadata sync and snapshot telemetry."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    metadata_version: str
    source_name: str
    source_entity_count: int = Field(ge=0)
    indexed_document_count: int = Field(ge=0)
    deleted_entity_count: int = Field(default=0, ge=0)
    sync_error_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("snapshot_id", "metadata_version", "source_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Metadata snapshot text fields must not be empty.")
        return stripped
