"""Benchmark-facing wrapper over the production schema manifest loader."""

from pathlib import Path

from t2s.catalog.catalog_models import CatalogTable
from t2s.catalog.schema_manifest_loader import load_catalog_tables_from_manifest

__all__ = ["load_bird_catalog_tables"]


def load_bird_catalog_tables(db_id: str, tables_json_path: Path) -> list[CatalogTable]:
    """Load catalog tables for one database of a benchmark ``tables.json`` manifest."""
    return load_catalog_tables_from_manifest(
        database_id=db_id,
        manifest_path=tables_json_path,
    )
