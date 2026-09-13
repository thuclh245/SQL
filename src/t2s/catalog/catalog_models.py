from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TableType = Literal["regular", "view", "materialized_view", "external", "unknown"]
SqlIdentifierSource = Literal["explicit", "resolved", "unresolved"]
RelationshipProvenance = Literal[
    "declared_primary_key",
    "declared_foreign_key",
    "openmetadata_relationship",
]


class CatalogColumn(BaseModel):
    column_fqn: str
    column_name: str
    data_type: str
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


class CatalogForeignKey(BaseModel):
    relationship_name: str | None = None
    from_table_fqn: str
    from_column_names: list[str]
    to_table_fqn: str
    to_column_names: list[str]
    provenance: RelationshipProvenance = "declared_foreign_key"

    @field_validator("from_table_fqn", "to_table_fqn")
    @classmethod
    def validate_table_fqn_is_not_empty(cls, table_fqn: str) -> str:
        stripped_table_fqn = table_fqn.strip()
        if not stripped_table_fqn:
            raise ValueError("Foreign key table FQNs must not be empty.")
        return stripped_table_fqn


class CatalogTable(BaseModel):
    table_fqn: str
    source_entity_id: str | None = None
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


class MetadataSnapshot(BaseModel):
    snapshot_id: str
    metadata_version: str
    source_name: str
    source_entity_count: int = Field(ge=0)
    indexed_document_count: int = Field(ge=0)
    deleted_entity_count: int = Field(default=0, ge=0)
    sync_error_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
