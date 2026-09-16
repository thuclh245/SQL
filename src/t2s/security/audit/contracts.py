"""Core typed models for the T2S security, hygiene, and governance audit system."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditStatus(StrEnum):
    """Execution outcome status for an audit check."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"


class TriState(StrEnum):
    """Tri-state assertion for scientific provenance and evidence claims."""

    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class DatasetProvenanceLabel(StrEnum):
    """Standardized dataset partition provenance classification."""

    DEVELOPMENT = "DEVELOPMENT"
    EXPOSED = "EXPOSED"
    QUARANTINED = "QUARANTINED"
    CERTIFIED_UNTOUCHED = "CERTIFIED_UNTOUCHED"
    UNKNOWN = "UNKNOWN"


class HygieneClosureStatus(StrEnum):
    """High-level repository governance closure determination."""

    HYGIENE_CLOSURE_COMPLETE = "HYGIENE_CLOSURE_COMPLETE"
    HYGIENE_REMEDIATION_INCOMPLETE = "HYGIENE_REMEDIATION_INCOMPLETE"
    CRITICAL_LEAKAGE_REMAINS = "CRITICAL_LEAKAGE_REMAINS"


class AuditFinding(BaseModel):
    """Detailed record of a specific policy violation or finding."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str
    category: str
    location: str
    description: str
    evidence: str
    severity: str = "HIGH"


class TriStateEvidence(BaseModel):
    """Evidence-backed assertion for provenance claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: TriState
    evidence_paths: list[str] = Field(default_factory=list)
    evidence_type: str
    confidence: str = "HIGH"
    notes: str | None = None


class AuditResult(BaseModel):
    """Formal, evidence-backed audit check result structure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_name: str
    status: AuditStatus
    timestamp: str
    tool_or_function: str
    scope: str
    checked_count: int
    violation_count: int
    violations: list[AuditFinding] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
