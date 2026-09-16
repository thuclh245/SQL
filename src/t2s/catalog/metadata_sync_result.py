"""Metadata Sync Execution Result Contract.

Encapsulates the complete lifecycle outcome of a metadata sync operation,
including reconciliation counts, validation issues, LKG state, and latency.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from t2s.catalog.metadata_reconciler import ReconciliationSummary
from t2s.catalog.metadata_validation import MetadataValidationResult


class SyncStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NO_CHANGE = "NO_CHANGE"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class MetadataSyncResult(BaseModel):
    """Immutable audit record of a completed or rejected metadata sync operation."""

    model_config = ConfigDict(frozen=True)

    sync_id: str
    source_system: str
    scope_fingerprint: str
    status: SyncStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    reconciliation_summary: ReconciliationSummary | None = None
    validation_result: MetadataValidationResult | None = None
    active_snapshot_id: str | None = None
    promoted_snapshot_id: str | None = None
    message: str = ""

    @property
    def is_success(self) -> bool:
        return self.status in {SyncStatus.SUCCESS, SyncStatus.NO_CHANGE}
