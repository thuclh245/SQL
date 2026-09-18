"""Versioned scoring / audit records (E05 §4, §14).

Three record types, one per architecture layer, kept deliberately separate so
the framework never collapses mechanical, semantic and aggregate signals into a
single number (E05 §4):

* :class:`ScoringRecord`     - Layer 1, deterministic mechanical scoring.
* :class:`SemanticAuditRecord` - Layer 2, structured A-F semantic audit.
* aggregate types live in :mod:`t2s.evaluation.scoring.aggregation` (Layer 3).

Every record carries the relevant version identifiers; a stored record is thus
self-describing and reproducible.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from t2s.evaluation.scoring.taxonomy import BSubtype, Grade, RootCause
from t2s.evaluation.scoring.versions import (
    EQUIVALENCE_RULES_VERSION,
    SCORER_VERSION,
    TAXONOMY_VERSION,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ScoringRecord:
    """Layer-1 deterministic result of scoring one replicate (E05 §4 Layer 1)."""

    case_id: str
    replicate_id: str
    db_id: str | None

    scorer_version: str
    equivalence_rules_version: str

    # Execution states (from evidence).
    runtime_status: str | None
    candidate_execution_ok: bool | None
    gold_execution_ok: bool | None

    # Strict execution accuracy: True/False/None (None = not determinable).
    strict_ex: bool | None

    # Deterministic equivalence (richer than strict EX).
    deterministic_equivalent: bool | None
    equivalence_level: str
    equivalence_relaxations: tuple[BSubtype, ...]
    equivalence_detail: str

    # Fingerprint equality (cheap exact check independent of row capture).
    fingerprint_match: bool | None

    # Shape.
    candidate_columns: int | None
    gold_columns: int | None

    # Evidence completeness (drives F downstream).
    determination_blockers: tuple[str, ...]

    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["equivalence_relaxations"] = [r.value for r in self.equivalence_relaxations]
        return data


@dataclass(frozen=True)
class SemanticAuditRecord:
    """Layer-2 structured semantic audit for one replicate (E05 §14).

    ``classification`` (grade) and ``root_cause_candidate`` are independent
    (E05 §16): a ``D`` may carry ``root_cause = UNKNOWN``. ``reviewer_id_or_role``
    identifies which reviewer produced this record so two independent reviewers
    (E05 §13) can be compared without majority voting.
    """

    taxonomy_version: str
    scorer_version: str

    case_id: str
    replicate_id: str

    strict_ex: bool | None
    deterministic_equivalence: bool | None

    classification: Grade
    subtype: BSubtype | None

    rationale: str
    evidence_refs: tuple[str, ...]

    semantic_correctness_assessed: bool
    reviewer_id_or_role: str

    root_cause_candidate: RootCause
    ambiguity_reason: str | None

    lucky_match_evidence: tuple[str, ...]

    confidence: float

    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["classification"] = self.classification.value
        data["subtype"] = self.subtype.value if self.subtype is not None else None
        data["root_cause_candidate"] = self.root_cause_candidate.value
        return data


def new_semantic_audit_record(
    *,
    case_id: str,
    replicate_id: str,
    classification: Grade,
    rationale: str,
    reviewer_id_or_role: str,
    strict_ex: bool | None = None,
    deterministic_equivalence: bool | None = None,
    subtype: BSubtype | None = None,
    evidence_refs: tuple[str, ...] = (),
    semantic_correctness_assessed: bool = True,
    root_cause_candidate: RootCause = RootCause.UNKNOWN,
    ambiguity_reason: str | None = None,
    lucky_match_evidence: tuple[str, ...] = (),
    confidence: float = 1.0,
) -> SemanticAuditRecord:
    """Construct a :class:`SemanticAuditRecord` with the current versions filled."""

    return SemanticAuditRecord(
        taxonomy_version=TAXONOMY_VERSION,
        scorer_version=SCORER_VERSION,
        case_id=case_id,
        replicate_id=replicate_id,
        strict_ex=strict_ex,
        deterministic_equivalence=deterministic_equivalence,
        classification=classification,
        subtype=subtype,
        rationale=rationale,
        evidence_refs=evidence_refs,
        semantic_correctness_assessed=semantic_correctness_assessed,
        reviewer_id_or_role=reviewer_id_or_role,
        root_cause_candidate=root_cause_candidate,
        ambiguity_reason=ambiguity_reason,
        lucky_match_evidence=lucky_match_evidence,
        confidence=confidence,
    )


__all__ = [
    "EQUIVALENCE_RULES_VERSION",
    "ScoringRecord",
    "SemanticAuditRecord",
    "new_semantic_audit_record",
]
