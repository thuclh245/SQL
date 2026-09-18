"""Compact per-case audit view for human / agent reviewers (E05 §23).

Assembles every artifact a reviewer needs into one record so they do not have to
search five directories: the question, schema/context, candidate & gold SQL,
result fingerprints, strict EX, deterministic equivalence, the A-F grade, its
rationale, root-cause candidate and evidence links.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from t2s.evaluation.scoring.protocols import CaseRunEvidence
from t2s.evaluation.scoring.records import ScoringRecord, SemanticAuditRecord


@dataclass(frozen=True)
class CaseAuditView:
    case_id: str
    replicate_id: str
    db_id: str | None
    question: str | None
    schema_context: str | None
    candidate_sql: str | None
    gold_sql: str | None
    candidate_fingerprint: str | None
    gold_fingerprint: str | None
    strict_ex: bool | None
    deterministic_equivalence: bool | None
    equivalence_level: str
    equivalence_relaxations: list[str]
    grade: str
    subtype: str | None
    rationale: str
    root_cause_candidate: str
    ambiguity_reason: str | None
    lucky_match_evidence: list[str]
    confidence: float
    evidence_refs: list[str]
    reviewer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "replicate_id": self.replicate_id,
            "db_id": self.db_id,
            "question": self.question,
            "schema_context": self.schema_context,
            "candidate_sql": self.candidate_sql,
            "gold_sql": self.gold_sql,
            "candidate_fingerprint": self.candidate_fingerprint,
            "gold_fingerprint": self.gold_fingerprint,
            "strict_ex": self.strict_ex,
            "deterministic_equivalence": self.deterministic_equivalence,
            "equivalence_level": self.equivalence_level,
            "equivalence_relaxations": self.equivalence_relaxations,
            "grade": self.grade,
            "subtype": self.subtype,
            "rationale": self.rationale,
            "root_cause_candidate": self.root_cause_candidate,
            "ambiguity_reason": self.ambiguity_reason,
            "lucky_match_evidence": self.lucky_match_evidence,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "reviewer": self.reviewer,
        }


def build_case_audit_view(
    evidence: CaseRunEvidence,
    scoring: ScoringRecord,
    audit: SemanticAuditRecord,
) -> CaseAuditView:
    """Fuse evidence + Layer-1 + Layer-2 into one reviewer-facing record."""

    return CaseAuditView(
        case_id=evidence.case_id,
        replicate_id=evidence.replicate_id,
        db_id=evidence.db_id,
        question=evidence.question,
        schema_context=evidence.evidence_context,
        candidate_sql=evidence.candidate_sql,
        gold_sql=evidence.gold_sql,
        candidate_fingerprint=evidence.candidate_fingerprint,
        gold_fingerprint=evidence.gold_fingerprint,
        strict_ex=scoring.strict_ex,
        deterministic_equivalence=scoring.deterministic_equivalent,
        equivalence_level=scoring.equivalence_level,
        equivalence_relaxations=[r.value for r in scoring.equivalence_relaxations],
        grade=audit.classification.value,
        subtype=audit.subtype.value if audit.subtype is not None else None,
        rationale=audit.rationale,
        root_cause_candidate=audit.root_cause_candidate.value,
        ambiguity_reason=audit.ambiguity_reason,
        lucky_match_evidence=list(audit.lucky_match_evidence),
        confidence=audit.confidence,
        evidence_refs=list(audit.evidence_refs),
        reviewer=audit.reviewer_id_or_role,
    )
