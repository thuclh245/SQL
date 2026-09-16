"""Metadata Quarantine for Rejected Candidates and Validation Defects.

Preserves structural diagnostics and error details from rejected sync operations
without exposing secrets, passwords, or connection credentials.
"""

import threading
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from t2s.catalog.metadata_validation import ValidationIssue


class QuarantineRecord(BaseModel):
    """Immutable record of a rejected metadata candidate or validation failure."""

    model_config = ConfigDict(frozen=True)

    sync_id: str
    source_system: str
    scope_fingerprint: str
    rejection_reason: str
    issues: list[ValidationIssue] = Field(default_factory=list)
    rejected_table_fqns: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetadataQuarantinePort(Protocol):
    """Storage boundary protocol for recording metadata quarantine events."""

    def record_quarantine(self, record: QuarantineRecord) -> None:
        """Store a quarantine record."""
        ...

    def get_quarantine_records(self) -> list[QuarantineRecord]:
        """Retrieve historical quarantine records."""
        ...


class InMemoryMetadataQuarantine(MetadataQuarantinePort):
    """Thread-safe in-memory store for metadata quarantine diagnostics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: list[QuarantineRecord] = []

    def record_quarantine(self, record: QuarantineRecord) -> None:
        with self._lock:
            self._records.append(record)

    def get_quarantine_records(self) -> list[QuarantineRecord]:
        with self._lock:
            return list(self._records)
