"""Metadata Provider Abstraction.

Defines the provider boundary between external metadata sources (PostgreSQL,
static manifests, cloud catalogs) and the T2S Canonical Metadata Model.
"""

from typing import Protocol

from t2s.catalog.canonical_metadata import CatalogTable
from t2s.catalog.metadata_scope import MetadataScope


class MetadataProviderPort(Protocol):
    """Provider boundary protocol for acquiring and canonicalizing metadata.

    Responsibilities:
    1. Connect to or read from the external metadata source.
    2. Apply controlled `MetadataScope` to restrict ingested assets.
    3. Normalize source data types, nullability, constraints, and descriptions.
    4. Construct immutable `CatalogTable` canonical representations.
    5. Enforce canonical structural and semantic validation before returning.

    Downstream consumer guarantees:
    - Downstream layers (`Grounding`, `InMemoryCatalog`, `RelationshipGraph`)
      consume strictly `list[CatalogTable]` and remain completely decoupled from
      source connection semantics, APIs, or database-specific catalogs.
    """

    @property
    def source_system(self) -> str:
        """Name of the external source system (e.g. 'postgresql', 'static')."""
        ...

    def fetch_metadata(self, scope: MetadataScope | None = None) -> list[CatalogTable]:
        """Acquire, filter, normalize, and validate canonical table metadata.

        Args:
            scope: Optional acquisition scope restricting databases, schemas,
                asset types, and include/exclude table patterns. If None, provider
                default business scope is acquired.

        Returns:
            A deterministically ordered list of valid `CatalogTable` domain objects.

        Raises:
            MetadataCatalogError: If source connection, query execution, or canonical
                validation fails. Partial metadata is never returned silently.
        """
        ...
