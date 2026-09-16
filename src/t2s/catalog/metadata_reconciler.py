"""Metadata Reconciliation Engine.

Performs scope-aware change detection between previous accepted snapshots
and incoming candidate tables, classifying assets as NEW, CHANGED, UNCHANGED,
or DELETED without endangering unscoped assets.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from t2s.catalog.canonical_metadata import CatalogTable
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot


class ReconciliationStatus(StrEnum):
    NEW = "NEW"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    DELETED = "DELETED"


class ReconciledAsset(BaseModel):
    """Change status of an individual data asset."""

    model_config = ConfigDict(frozen=True)

    table_fqn: str
    status: ReconciliationStatus
    previous_hash: str | None = None
    candidate_hash: str | None = None


class ReconciliationSummary(BaseModel):
    """Aggregate change classification and merged candidate table dictionary."""

    model_config = ConfigDict(frozen=True)

    new_count: int = 0
    changed_count: int = 0
    unchanged_count: int = 0
    deleted_count: int = 0
    unscoped_preserved_count: int = 0
    total_candidate_count: int = 0
    total_result_count: int = 0
    assets: list[ReconciledAsset] = Field(default_factory=list)
    merged_tables: dict[str, CatalogTable] = Field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return self.new_count > 0 or self.changed_count > 0 or self.deleted_count > 0


class MetadataReconciler:
    """Computes scope-aware diffs between previous snapshot and candidate metadata."""

    @classmethod
    def reconcile(
        cls,
        previous_snapshot: CanonicalMetadataSnapshot | None,
        candidate_tables: list[CatalogTable],
        scope: MetadataScope,
    ) -> ReconciliationSummary:
        candidate_by_fqn: dict[str, CatalogTable] = {t.table_fqn: t for t in candidate_tables}
        previous_by_fqn: dict[str, CatalogTable] = (
            previous_snapshot.tables if previous_snapshot is not None else {}
        )

        reconciled_assets: list[ReconciledAsset] = []
        new_count = 0
        changed_count = 0
        unchanged_count = 0
        deleted_count = 0

        # Merged result dict: start with unscoped tables carried forward from previous
        merged_tables: dict[str, CatalogTable] = {}
        unscoped_preserved_count = 0

        # 1. Identify previous assets: deleted (in scope & missing) vs preserved (out of scope)
        for fqn, prev_table in previous_by_fqn.items():
            in_current_candidate = fqn in candidate_by_fqn

            is_within_authoritative_scope = scope.matches_table(
                table_name=prev_table.table_name,
                schema_name=prev_table.schema_name,
                database_name=prev_table.database_name,
                asset_type=prev_table.table_type,
            )

            if not in_current_candidate:
                if is_within_authoritative_scope:
                    # Within scope and absent in candidate -> DELETED
                    deleted_count += 1
                    reconciled_assets.append(
                        ReconciledAsset(
                            table_fqn=fqn,
                            status=ReconciliationStatus.DELETED,
                            previous_hash=prev_table.semantic_content_hash,
                            candidate_hash=None,
                        )
                    )
                else:
                    # Outside authoritative scope -> PRESERVED in merged state
                    merged_tables[fqn] = prev_table
                    unscoped_preserved_count += 1

        # 2. Reconcile candidate assets (NEW, CHANGED, UNCHANGED)
        for fqn in sorted(candidate_by_fqn.keys()):
            cand_table = candidate_by_fqn[fqn]
            merged_tables[fqn] = cand_table

            if fqn not in previous_by_fqn:
                new_count += 1
                reconciled_assets.append(
                    ReconciledAsset(
                        table_fqn=fqn,
                        status=ReconciliationStatus.NEW,
                        previous_hash=None,
                        candidate_hash=cand_table.semantic_content_hash,
                    )
                )
            else:
                prev_table = previous_by_fqn[fqn]
                cand_hash = cand_table.semantic_content_hash
                prev_hash = prev_table.semantic_content_hash

                if cand_hash != prev_hash:
                    changed_count += 1
                    reconciled_assets.append(
                        ReconciledAsset(
                            table_fqn=fqn,
                            status=ReconciliationStatus.CHANGED,
                            previous_hash=prev_hash,
                            candidate_hash=cand_hash,
                        )
                    )
                else:
                    unchanged_count += 1
                    reconciled_assets.append(
                        ReconciledAsset(
                            table_fqn=fqn,
                            status=ReconciliationStatus.UNCHANGED,
                            previous_hash=prev_hash,
                            candidate_hash=cand_hash,
                        )
                    )

        # Deterministic sorting of reconciliation assets by table_fqn
        reconciled_assets.sort(key=lambda a: a.table_fqn)

        return ReconciliationSummary(
            new_count=new_count,
            changed_count=changed_count,
            unchanged_count=unchanged_count,
            deleted_count=deleted_count,
            unscoped_preserved_count=unscoped_preserved_count,
            total_candidate_count=len(candidate_tables),
            total_result_count=len(merged_tables),
            assets=reconciled_assets,
            merged_tables=merged_tables,
        )
