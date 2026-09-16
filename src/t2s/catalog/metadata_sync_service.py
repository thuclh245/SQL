"""Metadata Sync and Reconciliation Service.

Coordinates acquisition, full-catalog safety gates, scope-aware reconciliation,
cross-asset validation, quarantine diagnostics, and atomic LKG snapshot promotion.
"""

import time
from datetime import UTC, datetime

from t2s.catalog.catalog_port import CatalogPort
from t2s.catalog.metadata_provider import MetadataProviderPort
from t2s.catalog.metadata_quarantine import (
    InMemoryMetadataQuarantine,
    MetadataQuarantinePort,
    QuarantineRecord,
)
from t2s.catalog.metadata_reconciler import MetadataReconciler
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot
from t2s.catalog.metadata_snapshot_store import (
    InMemoryMetadataSnapshotStore,
    MetadataSnapshotStorePort,
)
from t2s.catalog.metadata_sync_result import MetadataSyncResult, SyncStatus
from t2s.catalog.metadata_validation import (
    MetadataValidationGate,
    ValidationIssue,
    ValidationSeverity,
)
from t2s.security.error_sanitizer import sanitize_error_message


class MetadataSyncService:
    """Orchestrates controlled metadata synchronization and LKG lifecycle."""

    def __init__(
        self,
        provider: MetadataProviderPort,
        snapshot_store: MetadataSnapshotStorePort | None = None,
        quarantine: MetadataQuarantinePort | None = None,
        validation_gate: MetadataValidationGate | None = None,
        catalog_storage: CatalogPort | None = None,
        allow_full_catalog_sync: bool = False,
    ) -> None:
        self.provider = provider
        self.snapshot_store = snapshot_store or InMemoryMetadataSnapshotStore()
        self.quarantine = quarantine or InMemoryMetadataQuarantine()
        self.validation_gate = validation_gate or MetadataValidationGate()
        self.catalog_storage = catalog_storage
        self.allow_full_catalog_sync = allow_full_catalog_sync

    def sync_metadata(
        self,
        scope: MetadataScope,
        allow_full_catalog_sync: bool | None = None,
    ) -> MetadataSyncResult:
        """Execute a controlled metadata synchronization cycle.

        Guarantees:
        1. Full-catalog safety: unrestricted scope without explicit permission fails closed.
        2. LKG invariant: provider failure or validation rejection never alters active snapshot.
        3. Scope-aware: assets outside authoritative scope are never marked deleted.
        4. Atomic promotion: active snapshot is replaced atomically in store and catalog.
        5. Source transition: authority changes (e.g. pg -> om) trigger promotion even if
           content is unchanged.
        6. Secret safety: all exception strings are sanitized before storage or logging.
        """
        effective_allow_full = (
            allow_full_catalog_sync
            if allow_full_catalog_sync is not None
            else self.allow_full_catalog_sync
        )
        started_at = datetime.now(UTC)
        start_monotonic = time.monotonic()
        scope_fp = scope.compute_fingerprint()
        sync_id = f"sync_{scope_fp[:8]}_{int(started_at.timestamp())}"

        current_active = self.snapshot_store.get_active_snapshot()
        active_id = current_active.snapshot_id if current_active is not None else None

        # 1. Full-Catalog Safety Gate
        if scope.is_unrestricted and not effective_allow_full:
            rejection_issue = ValidationIssue(
                code="FULL_CATALOG_SYNC_RESTRICTED",
                message=(
                    "Full-catalog sync rejected: unrestricted scope requires explicit "
                    "allow_full_catalog_sync=True to prevent unintended enterprise "
                    "catalog ingestion."
                ),
                severity=ValidationSeverity.ERROR,
            )
            quarantine_record = QuarantineRecord(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                rejection_reason="Unrestricted scope rejected by full-catalog safety gate.",
                issues=[rejection_issue],
                rejected_table_fqns=[],
                created_at=started_at,
            )
            self.quarantine.record_quarantine(quarantine_record)

            result = MetadataSyncResult(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                status=SyncStatus.REJECTED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                active_snapshot_id=active_id,
                message=rejection_issue.message,
            )
            self.snapshot_store.record_sync_result(result)
            return result

        # 2. Acquire candidate metadata from provider
        try:
            candidate_tables = self.provider.fetch_metadata(scope=scope)
        except Exception as exc:
            # Provider failure: preserve LKG active snapshot! Scrub secret in error message.
            clean_err = sanitize_error_message(str(exc))
            result = MetadataSyncResult(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                status=SyncStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                active_snapshot_id=active_id,
                message=f"Metadata acquisition from provider failed: {clean_err}",
            )
            self.snapshot_store.record_sync_result(result)
            return result

        # 3. Scope-Aware Reconciliation
        reconciliation = MetadataReconciler.reconcile(
            previous_snapshot=current_active,
            candidate_tables=candidate_tables,
            scope=scope,
        )

        # Detect Source Authority Transition (e.g. postgresql -> openmetadata)
        is_source_transition = (
            current_active is not None
            and current_active.source_system != self.provider.source_system
        )

        # 4. Check for No-Change Early Exit (only valid if source authority is also unchanged)
        if (
            current_active is not None
            and not reconciliation.has_changes
            and not is_source_transition
        ):
            result = MetadataSyncResult(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                status=SyncStatus.NO_CHANGE,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                reconciliation_summary=reconciliation,
                active_snapshot_id=active_id,
                message="Metadata state identical to current active snapshot. No promotion needed.",
            )
            self.snapshot_store.record_sync_result(result)
            return result

        # 5. Validation Gate Execution (enforces candidate scope containment & referential health)
        validation = self.validation_gate.validate(
            candidate_tables=candidate_tables,
            merged_tables=reconciliation.merged_tables,
            scope=scope,
            previous_snapshot=current_active,
        )

        # 6. Check for Validation Rejection
        if validation.has_errors:
            # Quarantine rejected metadata candidate
            quarantine_record = QuarantineRecord(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                rejection_reason=(
                    f"Candidate failed validation with {validation.error_count} error(s)."
                ),
                issues=validation.issues,
                rejected_table_fqns=[t.table_fqn for t in candidate_tables],
                created_at=datetime.now(UTC),
            )
            self.quarantine.record_quarantine(quarantine_record)

            # LKG active snapshot remains active!
            result = MetadataSyncResult(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                status=SyncStatus.REJECTED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                reconciliation_summary=reconciliation,
                validation_result=validation,
                active_snapshot_id=active_id,
                message=(
                    f"Candidate rejected: {validation.error_count} blocking validation error(s)."
                ),
            )
            self.snapshot_store.record_sync_result(result)
            return result

        # 7. Build and Check Candidate Snapshot
        candidate_snapshot = CanonicalMetadataSnapshot.create(
            source_system=self.provider.source_system,
            scope_fingerprint=scope_fp,
            tables=reconciliation.merged_tables,
        )

        # Semantic content equality check (must respect source transition)
        if (
            current_active is not None
            and current_active.semantic_content_hash == candidate_snapshot.semantic_content_hash
            and not is_source_transition
        ):
            # Semantic content unchanged
            result = MetadataSyncResult(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                status=SyncStatus.NO_CHANGE,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                reconciliation_summary=reconciliation,
                validation_result=validation,
                active_snapshot_id=active_id,
                message=(
                    "Candidate semantic content hash matches active snapshot. No promotion needed."
                ),
            )
            self.snapshot_store.record_sync_result(result)
            return result

        # 8. Atomic Serving Promotion
        # Update serving catalog FIRST; abort promotion if catalog fails
        merged_table_list = list(reconciliation.merged_tables.values())
        if self.catalog_storage is not None:
            try:
                # Prefer atomic sync_snapshot if supported
                if hasattr(self.catalog_storage, "sync_snapshot"):
                    self.catalog_storage.sync_snapshot(
                        tables=merged_table_list,
                        snapshot_id=candidate_snapshot.snapshot_id,
                    )
                else:
                    self.catalog_storage.upsert_tables(merged_table_list)
            except Exception as exc:
                # Serving catalog update failed: abort promotion, preserve LKG active snapshot!
                clean_err = sanitize_error_message(str(exc))
                result = MetadataSyncResult(
                    sync_id=sync_id,
                    source_system=self.provider.source_system,
                    scope_fingerprint=scope_fp,
                    status=SyncStatus.FAILED,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                    reconciliation_summary=reconciliation,
                    validation_result=validation,
                    active_snapshot_id=active_id,
                    message=f"Serving catalog update failed: {clean_err}",
                )
                self.snapshot_store.record_sync_result(result)
                return result

        # 9. Atomic Promotion to Active LKG Snapshot Store with Catalog Rollback
        previous_tables = list(current_active.tables.values()) if current_active is not None else []
        previous_snap_id = current_active.snapshot_id if current_active is not None else ""

        try:
            self.snapshot_store.promote_snapshot(candidate_snapshot)
        except Exception as store_exc:
            # Snapshot store promotion failed! Roll back serving catalog to previous state!
            if self.catalog_storage is not None:
                try:
                    if hasattr(self.catalog_storage, "sync_snapshot"):
                        self.catalog_storage.sync_snapshot(previous_tables, previous_snap_id)
                    else:
                        self.catalog_storage.delete_tables(
                            list(reconciliation.merged_tables.keys())
                        )
                        self.catalog_storage.upsert_tables(previous_tables)
                except Exception:
                    pass
            clean_err = sanitize_error_message(str(store_exc))
            result = MetadataSyncResult(
                sync_id=sync_id,
                source_system=self.provider.source_system,
                scope_fingerprint=scope_fp,
                status=SyncStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                reconciliation_summary=reconciliation,
                validation_result=validation,
                active_snapshot_id=active_id,
                message=f"Snapshot store promotion failed: {clean_err}",
            )
            self.snapshot_store.record_sync_result(result)
            return result

        success_message = (
            f"Source authority transitioned from '{current_active.source_system}' to "
            f"'{self.provider.source_system}'. Promoted new active LKG snapshot."
            if is_source_transition and current_active is not None
            else "Candidate snapshot successfully validated and promoted to active LKG state."
        )

        result = MetadataSyncResult(
            sync_id=sync_id,
            source_system=self.provider.source_system,
            scope_fingerprint=scope_fp,
            status=SyncStatus.SUCCESS,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            duration_ms=int((time.monotonic() - start_monotonic) * 1000),
            reconciliation_summary=reconciliation,
            validation_result=validation,
            active_snapshot_id=candidate_snapshot.snapshot_id,
            promoted_snapshot_id=candidate_snapshot.snapshot_id,
            message=success_message,
        )
        self.snapshot_store.record_sync_result(result)
        return result

    sync = sync_metadata
