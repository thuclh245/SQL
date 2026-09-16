"""Controlled Metadata Scope for Source-Neutral Metadata Acquisition.

Defines the boundary filter contract governing incremental metadata onboarding.
Crucial Distinction:
`MetadataScope` controls catalog ingestion and provider acquisition. It is NOT
user-level ACL or runtime authorization.
"""

from fnmatch import fnmatchcase
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from t2s.catalog.canonical_metadata import AssetType


def _validate_pattern_strings(
    patterns: frozenset[str] | None, field_label: str
) -> frozenset[str] | None:
    if patterns is None:
        return None
    cleaned: set[str] = set()
    for item in patterns:
        stripped = item.strip()
        if not stripped:
            raise ValueError(f"{field_label} items must not be empty or whitespace-only.")
        cleaned.add(stripped)
    return frozenset(cleaned)


class MetadataScope(BaseModel):
    """Source-neutral specification for scoping metadata acquisition.

    Evaluation Rules:
    1. Schema exclusion: if an asset belongs to a schema in `exclude_schemas`, it is excluded.
    2. Schema inclusion: if `schema_names` is configured, the asset's schema must match.
    3. Database inclusion: if `database_names` is configured, the asset's database must match.
    4. Asset type inclusion: if `include_asset_types` is configured, the asset's type must match.
    5. Table exclusion: if an asset matches any pattern in `exclude_tables`, it is excluded
       (EXCLUDE WINS on conflict).
    6. Table inclusion: if `include_tables` is set, the asset must match at least one pattern.
    7. Default / None semantics: any filter set to `None` imposes no restriction.
    8. Empty set semantics: if an inclusion filter is explicitly set to an empty set,
       it restricts to zero items (matches nothing).
    """

    model_config = ConfigDict(frozen=True)

    database_names: frozenset[str] | set[str] | None = None
    schema_names: frozenset[str] | set[str] | None = None
    exclude_schemas: frozenset[str] | set[str] | None = None
    include_tables: frozenset[str] | set[str] | None = None
    exclude_tables: frozenset[str] | set[str] | None = None
    include_asset_types: frozenset[AssetType] | set[AssetType] | None = None

    @field_validator("database_names", mode="before")
    @classmethod
    def _coerce_database_names(cls, v: Any) -> frozenset[str] | None:
        if v is None:
            return None
        return _validate_pattern_strings(frozenset(v), "database_names")

    @field_validator("schema_names", mode="before")
    @classmethod
    def _coerce_schema_names(cls, v: Any) -> frozenset[str] | None:
        if v is None:
            return None
        return _validate_pattern_strings(frozenset(v), "schema_names")

    @field_validator("exclude_schemas", mode="before")
    @classmethod
    def _coerce_exclude_schemas(cls, v: Any) -> frozenset[str] | None:
        if v is None:
            return None
        return _validate_pattern_strings(frozenset(v), "exclude_schemas")

    @field_validator("include_tables", mode="before")
    @classmethod
    def _coerce_include_tables(cls, v: Any) -> frozenset[str] | None:
        if v is None:
            return None
        return _validate_pattern_strings(frozenset(v), "include_tables")

    @field_validator("exclude_tables", mode="before")
    @classmethod
    def _coerce_exclude_tables(cls, v: Any) -> frozenset[str] | None:
        if v is None:
            return None
        return _validate_pattern_strings(frozenset(v), "exclude_tables")

    @field_validator("include_asset_types", mode="before")
    @classmethod
    def _coerce_include_asset_types(cls, v: Any) -> frozenset[AssetType] | None:
        if v is None:
            return None
        return frozenset(v)

    def matches_database(self, database_name: str) -> bool:
        """Evaluate database-level inclusion."""
        if self.database_names is None:
            return True
        return database_name.strip() in self.database_names

    def matches_schema(self, schema_name: str) -> bool:
        """Evaluate schema-level inclusion and exclusion (exclude wins)."""
        stripped_schema = schema_name.strip()
        if self.exclude_schemas is not None:
            if any(self._match_pattern(stripped_schema, pat) for pat in self.exclude_schemas):
                return False
        if self.schema_names is None:
            return True
        return any(self._match_pattern(stripped_schema, pat) for pat in self.schema_names)

    def matches_asset_type(self, asset_type: AssetType) -> bool:
        """Evaluate asset-type inclusion."""
        if self.include_asset_types is None:
            return True
        return asset_type in self.include_asset_types

    def matches_table(
        self,
        table_name: str,
        schema_name: str,
        database_name: str | None = None,
        asset_type: AssetType = "table",
    ) -> bool:
        """Evaluate asset inclusion against all scope dimensions.

        Deterministic rule: EXCLUDE WINS.
        An asset must satisfy database, schema, asset_type, and table-name rules.
        """
        if database_name is not None and not self.matches_database(database_name):
            return False

        if not self.matches_schema(schema_name):
            return False

        if not self.matches_asset_type(asset_type):
            return False

        stripped_table = table_name.strip()
        scoped_fqn = f"{schema_name.strip()}.{stripped_table}"
        candidates = (stripped_table, scoped_fqn)

        # 1. Check table exclusions - Exclude wins on conflict
        if self.exclude_tables is not None:
            for pat in self.exclude_tables:
                if any(self._match_pattern(c, pat) for c in candidates):
                    return False

        # 2. Check table inclusions
        if self.include_tables is not None:
            matched = False
            for pat in self.include_tables:
                if any(self._match_pattern(c, pat) for c in candidates):
                    matched = True
                    break
            if not matched:
                return False

        return True

    @staticmethod
    def _match_pattern(candidate: str, pattern: str) -> bool:
        """Match identifier with exact match or glob pattern (preserving case)."""
        if candidate == pattern:
            return True
        if any(char in pattern for char in ("*", "?", "[", "]")):
            return fnmatchcase(candidate, pattern)
        return False

    def compute_fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint representing the scope specification."""
        import hashlib
        import json

        payload = {
            "database_names": sorted(self.database_names) if self.database_names else None,
            "schema_names": sorted(self.schema_names) if self.schema_names else None,
            "exclude_schemas": sorted(self.exclude_schemas) if self.exclude_schemas else None,
            "include_tables": sorted(self.include_tables) if self.include_tables else None,
            "exclude_tables": sorted(self.exclude_tables) if self.exclude_tables else None,
            "include_asset_types": (
                sorted(self.include_asset_types) if self.include_asset_types else None
            ),
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def is_unrestricted(self) -> bool:
        """Return True if scope does not restrict databases, schemas, or tables."""
        return (
            self.database_names is None
            and self.schema_names is None
            and self.include_tables is None
            and self.exclude_schemas is None
            and self.exclude_tables is None
            and self.include_asset_types is None
        )
