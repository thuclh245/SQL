"""Metadata Snapshot Storage Abstraction and Last-Known-Good Store.

Provides atomic snapshot retrieval and promotion, ensuring that downstream
consumers (Grounding, Retrieval) never observe half-applied or corrupted states.
"""

import threading
from typing import Protocol

from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot
from t2s.catalog.metadata_sync_result import MetadataSyncResult


class MetadataSnapshotStorePort(Protocol):
    """Storage protocol for active snapshots, history, and sync audit records."""

    def get_active_snapshot(self) -> CanonicalMetadataSnapshot | None:
        """Return the current active Last-Known-Good canonical snapshot."""
        ...

    def promote_snapshot(self, snapshot: CanonicalMetadataSnapshot) -> None:
        """Atomically promote a validated candidate snapshot to active state."""
        ...

    def get_snapshot_history(self) -> list[CanonicalMetadataSnapshot]:
        """Return historical accepted snapshots in chronological order."""
        ...

    def record_sync_result(self, result: MetadataSyncResult) -> None:
        """Store an operational sync result audit record."""
        ...

    def get_sync_results(self) -> list[MetadataSyncResult]:
        """Return historical sync results."""
        ...


class InMemoryMetadataSnapshotStore(MetadataSnapshotStorePort):
    """Thread-safe in-memory store providing atomic snapshot promotion and LKG preservation."""

    def __init__(self, initial_snapshot: CanonicalMetadataSnapshot | None = None) -> None:
        self._lock = threading.RLock()
        self._active_snapshot: CanonicalMetadataSnapshot | None = initial_snapshot
        self._snapshot_history: list[CanonicalMetadataSnapshot] = (
            [initial_snapshot] if initial_snapshot is not None else []
        )
        self._sync_results: list[MetadataSyncResult] = []

    def get_active_snapshot(self) -> CanonicalMetadataSnapshot | None:
        with self._lock:
            return self._active_snapshot

    def promote_snapshot(self, snapshot: CanonicalMetadataSnapshot) -> None:
        """Atomically promote candidate to active status under lock."""
        with self._lock:
            self._snapshot_history.append(snapshot)
            self._active_snapshot = snapshot

    def get_snapshot_history(self) -> list[CanonicalMetadataSnapshot]:
        with self._lock:
            return list(self._snapshot_history)

    def record_sync_result(self, result: MetadataSyncResult) -> None:
        with self._lock:
            self._sync_results.append(result)

    def get_sync_results(self) -> list[MetadataSyncResult]:
        with self._lock:
            return list(self._sync_results)
