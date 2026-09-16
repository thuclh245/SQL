"""Canonical Metadata Snapshot Model.

Represents an immutable, verified, accepted metadata state with aggregate
semantic hashing, scope fingerprinting, and deterministic serialization.
"""

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from t2s.catalog.canonical_metadata import CatalogTable


class CanonicalMetadataSnapshot(BaseModel):
    """Immutable snapshot of accepted canonical metadata.

    Invariants:
    1. Pure domain objects: contains strictly valid `CatalogTable` entities.
    2. Aggregate hash: deterministic SHA-256 digest computed across sorted assets
       (table_fqn:semantic_content_hash).
    3. Scope fingerprint: records the authoritative scope used during ingestion.
    4. Determinism: lookup by canonical FQN is O(1).
    """

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    source_system: str
    scope_fingerprint: str
    schema_version: str = "1.0.0"
    tables: dict[str, CatalogTable] = Field(default_factory=dict)
    semantic_content_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def compute_aggregate_semantic_hash(
        cls, tables: Sequence[CatalogTable] | dict[str, CatalogTable]
    ) -> str:
        """Compute deterministic SHA-256 aggregate hash of semantic table contents."""
        table_list = list(tables.values()) if isinstance(tables, dict) else list(tables)
        sorted_tables = sorted(table_list, key=lambda t: t.table_fqn)
        lines = [f"{t.table_fqn}:{t.semantic_content_hash}\n" for t in sorted_tables]
        return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        source_system: str,
        scope_fingerprint: str,
        tables: Sequence[CatalogTable] | dict[str, CatalogTable],
        schema_version: str = "1.0.0",
        snapshot_timestamp: datetime | None = None,
    ) -> "CanonicalMetadataSnapshot":
        """Construct an accepted snapshot with deterministic ID and aggregate hash."""
        now = snapshot_timestamp or datetime.now(UTC)
        table_dict = (
            {t.table_fqn: t for t in tables} if not isinstance(tables, dict) else dict(tables)
        )
        agg_hash = cls.compute_aggregate_semantic_hash(table_dict)
        ts_suffix = int(now.timestamp())
        snapshot_id = f"snap_{agg_hash[:12]}_{ts_suffix}"
        return cls(
            snapshot_id=snapshot_id,
            source_system=source_system,
            scope_fingerprint=scope_fingerprint,
            schema_version=schema_version,
            tables=table_dict,
            semantic_content_hash=agg_hash,
            created_at=now,
        )

    def get_table(self, table_fqn: str) -> CatalogTable | None:
        """Lookup table by canonical FQN."""
        return self.tables.get(table_fqn)

    def list_table_fqns(self) -> list[str]:
        """List canonical table FQNs in deterministic sorted order."""
        return sorted(self.tables.keys())

    @property
    def table_count(self) -> int:
        return len(self.tables)
