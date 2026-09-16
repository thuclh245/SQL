"""Static / JSON File Metadata Provider.

Adapts existing schema manifest and static JSON catalog table loaders into the
canonical `MetadataProviderPort` interface, enforcing scope filtering and
canonical validation.
"""

import json
from pathlib import Path

from t2s.catalog.canonical_metadata import CatalogTable
from t2s.catalog.metadata_provider import MetadataProviderPort
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.schema_manifest_loader import load_catalog_tables_from_manifest
from t2s.errors.application_errors import ConfigurationError, MetadataMappingError


class StaticMetadataProvider(MetadataProviderPort):
    """Acquires canonical metadata from static JSON files or pre-loaded tables."""

    def __init__(
        self,
        catalog_tables_path: Path | None = None,
        database_id: str | None = None,
        tables: list[CatalogTable] | None = None,
    ) -> None:
        if catalog_tables_path is None and tables is None:
            raise ConfigurationError(
                "StaticMetadataProvider requires either 'catalog_tables_path' or 'tables'."
            )
        self.catalog_tables_path = catalog_tables_path
        self.database_id = database_id
        self._preloaded_tables = list(tables) if tables is not None else None

    @property
    def source_system(self) -> str:
        return "static"

    def fetch_metadata(self, scope: MetadataScope | None = None) -> list[CatalogTable]:
        tables = self._load_raw_tables()

        # Apply controlled metadata scope
        if scope is not None:
            tables = [
                table
                for table in tables
                if scope.matches_table(
                    table_name=table.table_name,
                    schema_name=table.schema_name,
                    database_name=table.database_name,
                    asset_type=table.table_type,
                )
            ]

        # Enforce canonical validation and deterministic sorting
        validated_tables: list[CatalogTable] = []
        for table in tables:
            try:
                # If already a CatalogTable, ensure invariants
                validated = CatalogTable.model_validate(table)
                validated_tables.append(validated)
            except Exception as exc:
                fqn = getattr(table, "table_fqn", "unknown")
                raise MetadataMappingError(
                    f"Static metadata validation failed for table '{fqn}': {exc}"
                ) from exc

        return sorted(validated_tables, key=lambda t: t.table_fqn)

    def _load_raw_tables(self) -> list[CatalogTable]:
        if self._preloaded_tables is not None:
            return list(self._preloaded_tables)

        assert self.catalog_tables_path is not None
        if not self.catalog_tables_path.is_file():
            raise ConfigurationError(
                f"Catalog tables file does not exist: {self.catalog_tables_path}"
            )

        if self.database_id:
            return load_catalog_tables_from_manifest(
                database_id=self.database_id,
                manifest_path=self.catalog_tables_path,
            )

        try:
            payload = json.loads(self.catalog_tables_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MetadataMappingError(
                f"Failed to parse static catalog JSON at {self.catalog_tables_path}: {exc}"
            ) from exc

        if not isinstance(payload, list):
            raise ConfigurationError(
                f"Catalog tables path must contain a JSON list: {self.catalog_tables_path}"
            )

        try:
            return [CatalogTable.model_validate(item) for item in payload]
        except Exception as exc:
            raise MetadataMappingError(
                f"Static metadata validation failed in {self.catalog_tables_path}: {exc}"
            ) from exc
