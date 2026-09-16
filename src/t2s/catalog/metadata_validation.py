"""Validation Gate and Referential Health Checks for Metadata Sync.

Enforces cross-asset referential integrity, identity uniqueness, and anomaly
guards, strictly distinguishing blocking errors from out-of-scope pilot warnings.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from t2s.catalog.canonical_metadata import AssetIdentity, CatalogTable
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.metadata_snapshot import CanonicalMetadataSnapshot


class ValidationSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationIssue(BaseModel):
    """Detailed metadata validation finding."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    severity: ValidationSeverity
    table_fqn: str | None = None
    field_name: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class MetadataValidationResult(BaseModel):
    """Structured report of validation gate execution."""

    model_config = ConfigDict(frozen=True)

    issues: list[ValidationIssue] = Field(default_factory=list)
    valid_fk_count: int = 0
    broken_fk_count: int = 0
    unresolved_out_of_scope_fk_count: int = 0
    tables_with_description: int = 0
    columns_with_description: int = 0
    tables_with_pk: int = 0
    tables_with_fk: int = 0

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == ValidationSeverity.WARNING for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.WARNING)


class MetadataValidationGate:
    """Evaluates candidate metadata against multi-severity validation rules."""

    def __init__(
        self,
        maximum_allowed_drop_ratio: float = 0.5,
        anomaly_baseline_minimum_assets: int = 10,
    ) -> None:
        self.maximum_allowed_drop_ratio = maximum_allowed_drop_ratio
        self.anomaly_baseline_minimum_assets = anomaly_baseline_minimum_assets

    def validate(
        self,
        candidate_tables: list[CatalogTable],
        merged_tables: dict[str, CatalogTable],
        scope: MetadataScope,
        previous_snapshot: CanonicalMetadataSnapshot | None = None,
    ) -> MetadataValidationResult:
        issues: list[ValidationIssue] = []

        # 0. Candidate Scope Containment Guard (Strict Validation Boundary)
        for table in candidate_tables:
            if not scope.matches_table(
                table_name=table.table_name,
                schema_name=table.schema_name,
                database_name=table.database_name,
                asset_type=table.table_type,
            ):
                issues.append(
                    ValidationIssue(
                        code="CANDIDATE_OUTSIDE_SCOPE",
                        message=(
                            f"Candidate table '{table.table_fqn}' is outside authoritative scope "
                            f"(schema='{table.schema_name}', table='{table.table_name}'). "
                            "Provider returned assets violating requested boundary."
                        ),
                        severity=ValidationSeverity.ERROR,
                        table_fqn=table.table_fqn,
                    )
                )

        # 1. Duplicate canonical identity check in candidate batch
        seen_fqns: set[str] = set()
        for table in candidate_tables:
            if table.table_fqn in seen_fqns:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_CANONICAL_IDENTITY",
                        message=(
                            "Duplicate canonical table FQN detected in candidate batch: "
                            f"{table.table_fqn}"
                        ),
                        severity=ValidationSeverity.ERROR,
                        table_fqn=table.table_fqn,
                    )
                )
            seen_fqns.add(table.table_fqn)

        # 2. Referential integrity & structural health checks
        valid_fk_count = 0
        broken_fk_count = 0
        unresolved_out_of_scope_fk_count = 0
        tables_with_desc = 0
        columns_with_desc = 0
        tables_with_pk = 0
        tables_with_fk = 0

        for table in candidate_tables:
            # Metrics
            if table.description and table.description.strip():
                tables_with_desc += 1
            if table.primary_key_column_names:
                tables_with_pk += 1
            if table.foreign_keys:
                tables_with_fk += 1

            for col in table.columns:
                if col.description and col.description.strip():
                    columns_with_desc += 1

            # Informational quality warning (non-blocking)
            if not table.description or not table.description.strip():
                issues.append(
                    ValidationIssue(
                        code="MISSING_TABLE_DESCRIPTION",
                        message=f"Table '{table.table_fqn}' lacks a business description.",
                        severity=ValidationSeverity.WARNING,
                        table_fqn=table.table_fqn,
                    )
                )

            # Foreign key referential checks
            col_names = {c.column_name for c in table.columns}
            for fk in table.foreign_keys:
                rel_name = fk.relationship_name or "unnamed_fk"

                # Check local columns
                missing_local = [c for c in fk.from_column_names if c not in col_names]
                if missing_local:
                    issues.append(
                        ValidationIssue(
                            code="UNDEFINED_LOCAL_FK_COLUMN",
                            message=(
                                f"Foreign key '{rel_name}' on '{table.table_fqn}' references "
                                f"undefined local columns: {missing_local}"
                            ),
                            severity=ValidationSeverity.ERROR,
                            table_fqn=table.table_fqn,
                        )
                    )
                    broken_fk_count += 1
                    continue

                # Cross-asset target check
                target_table = merged_tables.get(fk.to_table_fqn)
                if target_table is not None:
                    # Target table exists in candidate/merged catalog
                    target_col_names = {c.column_name for c in target_table.columns}
                    missing_target_cols = [
                        c for c in fk.to_column_names if c not in target_col_names
                    ]
                    if missing_target_cols:
                        issues.append(
                            ValidationIssue(
                                code="BROKEN_FK_TARGET_COLUMNS",
                                message=(
                                    f"Foreign key '{rel_name}' on '{table.table_fqn}' "
                                    f"references undefined columns on target "
                                    f"'{fk.to_table_fqn}': {missing_target_cols}"
                                ),
                                severity=ValidationSeverity.ERROR,
                                table_fqn=table.table_fqn,
                            )
                        )
                        broken_fk_count += 1
                    else:
                        valid_fk_count += 1
                else:
                    # Target table does not exist in merged catalog.
                    # Determine whether target was within authoritative scope using structured
                    # coordinates or parsed canonical locators.
                    target_schema = fk.to_schema_name
                    target_table_name = fk.to_table_name
                    target_db = fk.to_database_name

                    if not (target_schema and target_table_name):
                        try:
                            _, parsed_db, parsed_schema, parsed_table = (
                                AssetIdentity.parse_canonical_locator(fk.to_table_fqn)
                            )
                            target_db = target_db or parsed_db
                            target_schema = target_schema or parsed_schema
                            target_table_name = target_table_name or parsed_table
                        except ValueError as exc:
                            issues.append(
                                ValidationIssue(
                                    code="MALFORMED_FK_TARGET_LOCATOR",
                                    message=(
                                        f"Foreign key '{rel_name}' on '{table.table_fqn}' has "
                                        f"unparseable target locator '{fk.to_table_fqn}': {exc}"
                                    ),
                                    severity=ValidationSeverity.ERROR,
                                    table_fqn=table.table_fqn,
                                )
                            )
                            broken_fk_count += 1
                            continue

                    target_is_in_scope = scope.matches_table(
                        table_name=target_table_name,
                        schema_name=target_schema,
                        database_name=target_db,
                    )

                    if target_is_in_scope:
                        # Target should have been synced in this scope but is missing -> ERROR
                        issues.append(
                            ValidationIssue(
                                code="BROKEN_REFERENCE_TARGET_MISSING_IN_SCOPE",
                                message=(
                                    f"Foreign key '{rel_name}' on '{table.table_fqn}' "
                                    f"targets '{fk.to_table_fqn}' which is within scope "
                                    "but missing from source."
                                ),
                                severity=ValidationSeverity.ERROR,
                                table_fqn=table.table_fqn,
                            )
                        )
                        broken_fk_count += 1
                    else:
                        # Target is outside current scope (e.g. pilot onboarding) -> WARNING only
                        issues.append(
                            ValidationIssue(
                                code="UNRESOLVED_OUT_OF_SCOPE_FK",
                                message=(
                                    f"Foreign key '{rel_name}' on '{table.table_fqn}' "
                                    f"references target '{fk.to_table_fqn}' which is "
                                    "outside current sync scope."
                                ),
                                severity=ValidationSeverity.WARNING,
                                table_fqn=table.table_fqn,
                            )
                        )
                        unresolved_out_of_scope_fk_count += 1

        # 3. Asset-Count Anomaly Guard
        if (
            previous_snapshot is not None
            and previous_snapshot.table_count >= self.anomaly_baseline_minimum_assets
            and previous_snapshot.scope_fingerprint == scope.compute_fingerprint()
        ):
            cand_count = len(candidate_tables)
            prev_count = previous_snapshot.table_count
            max_allowed_drop = prev_count * self.maximum_allowed_drop_ratio
            actual_drop = prev_count - cand_count
            if actual_drop > max_allowed_drop:
                drop_pct = int((actual_drop / prev_count) * 100)
                issues.append(
                    ValidationIssue(
                        code="ANOMALOUS_ASSET_COUNT_DROP",
                        message=(
                            f"Anomalous drop in asset count detected for identical scope: "
                            f"dropped by {drop_pct}% (from {prev_count} to {cand_count} assets). "
                            f"Exceeds threshold of {int(self.maximum_allowed_drop_ratio * 100)}%."
                        ),
                        severity=ValidationSeverity.ERROR,
                        context={"previous_count": prev_count, "candidate_count": cand_count},
                    )
                )

        return MetadataValidationResult(
            issues=issues,
            valid_fk_count=valid_fk_count,
            broken_fk_count=broken_fk_count,
            unresolved_out_of_scope_fk_count=unresolved_out_of_scope_fk_count,
            tables_with_description=tables_with_desc,
            columns_with_description=columns_with_desc,
            tables_with_pk=tables_with_pk,
            tables_with_fk=tables_with_fk,
        )
