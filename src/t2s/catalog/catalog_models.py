"""Catalog models re-exporting from canonical_metadata for backward compatibility."""

from t2s.catalog.canonical_metadata import (
    AssetIdentity,
    AssetType,
    CatalogColumn,
    CatalogForeignKey,
    CatalogTable,
    MetadataProvenance,
    MetadataSnapshot,
    RelationshipProvenance,
    SqlIdentifierSource,
    TableType,
)

__all__ = [
    "AssetIdentity",
    "AssetType",
    "CatalogColumn",
    "CatalogForeignKey",
    "CatalogTable",
    "MetadataProvenance",
    "MetadataSnapshot",
    "RelationshipProvenance",
    "SqlIdentifierSource",
    "TableType",
]
