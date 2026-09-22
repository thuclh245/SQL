"""Layer 2 - structured semantic audit (E05 §4, §10, §12, §13, §15, §16).

This layer turns deterministic facts (Layer 1) plus governed evidence into an
A-F :class:`SemanticAuditRecord`. It provides:

* :func:`deterministic_semantic_audit` - a conservative, reproducible
  pre-classifier acting as one reviewer. It assigns A/B/E/F purely from
  deterministic evidence and only ever provisionally proposes D for a genuine
  result mismatch (never C, which requires a human rationale; never E without a
  proven counterexample). Missing evidence => F, always in the denominator.
* Two-independent-reviewer support (E05 §13): :func:`merge_reviews` compares two
  reviewers WITHOUT majority voting and routes disagreements to an adjudication
  queue.
* An **advisory, non-authoritative** LLM reviewer contract (E05 §12): its exact
  inputs and versioned rubric are persisted, and it can never silently overwrite
  deterministic metrics — :func:`reconcile_advisory_with_deterministic` only
  *surfaces* disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from t2s.evaluation.scoring.lucky_match import (
    LuckyMatchAssessment,
    LuckyMatchVerdict,
)
from t2s.evaluation.scoring.protocols import CaseRunEvidence
from t2s.evaluation.scoring.records import (
    ScoringRecord,
    SemanticAuditRecord,
    new_semantic_audit_record,
)
from t2s.evaluation.scoring.taxonomy import BSubtype, Grade, RootCause

DETERMINISTIC_REVIEWER = "deterministic-preclassifier"


def deterministic_semantic_audit(
    evidence: CaseRunEvidence,
    scoring: ScoringRecord,
    *,
    lucky_assessment: LuckyMatchAssessment | None = None,
) -> SemanticAuditRecord:
    """Conservative reproducible A-F pre-classification (one reviewer).

    Decision order (each step honest about what deterministic evidence can and
    cannot establish):

    1. Missing evidence (blockers) => **F**.
    2. Result-equivalent + proven lucky match => **E**.
    3. Result-equivalent, exact, no relaxations => **A**.
    4. Result-equivalent with harmless relaxations => **B** (+ subtype).
    5. Result mismatch with full evidence => provisional **D** (low confidence),
       flagged for semantic review to distinguish D / C / evaluator-defect.
    """

    blockers = scoring.determination_blockers
    if blockers:
        return new_semantic_audit_record(
            case_id=evidence.case_id,
            replicate_id=evidence.replicate_id,
            classification=Grade.F,
            rationale=f"insufficient evidence: {', '.join(blockers)}",
            reviewer_id_or_role=DETERMINISTIC_REVIEWER,
            strict_ex=scoring.strict_ex,
            deterministic_equivalence=scoring.deterministic_equivalent,
            evidence_refs=tuple(f"blocker:{b}" for b in blockers),
            semantic_correctness_assessed=False,
            root_cause_candidate=RootCause.UNKNOWN,
            confidence=1.0,
        )

    equivalent = scoring.deterministic_equivalent

    if equivalent is True:
        if lucky_assessment is not None and lucky_assessment.verdict is LuckyMatchVerdict.LUCKY:
            return new_semantic_audit_record(
                case_id=evidence.case_id,
                replicate_id=evidence.replicate_id,
                classification=Grade.E,
                rationale="result matches gold on primary fixture but diverges on a "
                "governed alternate fixture: logic is wrong (lucky match).",
                reviewer_id_or_role=DETERMINISTIC_REVIEWER,
                strict_ex=scoring.strict_ex,
                deterministic_equivalence=True,
                lucky_match_evidence=lucky_assessment.evidence,
                root_cause_candidate=RootCause.UNKNOWN,
                confidence=0.9,
            )
        relaxations = scoring.equivalence_relaxations
        if not relaxations and scoring.equivalence_level == "EXACT":
            return new_semantic_audit_record(
                case_id=evidence.case_id,
                replicate_id=evidence.replicate_id,
                classification=Grade.A,
                rationale="exact result-value match with identical shape.",
                reviewer_id_or_role=DETERMINISTIC_REVIEWER,
                strict_ex=scoring.strict_ex,
                deterministic_equivalence=True,
                confidence=1.0,
            )
        return new_semantic_audit_record(
            case_id=evidence.case_id,
            replicate_id=evidence.replicate_id,
            classification=Grade.B,
            subtype=relaxations[0] if relaxations else BSubtype.B5_EQUIVALENT_FORM,
            rationale="results equivalent up to harmless contract variance: "
            + ", ".join(r.value for r in relaxations),
            reviewer_id_or_role=DETERMINISTIC_REVIEWER,
            strict_ex=scoring.strict_ex,
            deterministic_equivalence=True,
            evidence_refs=tuple(r.value for r in relaxations),
            root_cause_candidate=RootCause.OUTPUT_CONTRACT,
            confidence=0.95,
        )

    if equivalent is None:
        # Results not comparable despite passing the blocker check (should be
        # rare) -> insufficient evidence.
        return new_semantic_audit_record(
            case_id=evidence.case_id,
            replicate_id=evidence.replicate_id,
            classification=Grade.F,
            rationale="result comparison indeterminate (no comparable result data).",
            reviewer_id_or_role=DETERMINISTIC_REVIEWER,
            strict_ex=scoring.strict_ex,
            deterministic_equivalence=None,
            semantic_correctness_assessed=False,
            confidence=1.0,
        )

    # equivalent is False: genuine mismatch, full evidence present.
    return new_semantic_audit_record(
        case_id=evidence.case_id,
        replicate_id=evidence.replicate_id,
        classification=Grade.D,
        rationale="candidate result differs from gold with full evidence present; "
        "provisional true error. Human/second reviewer required to rule out "
        "defensible ambiguity (C) or evaluator/gold defect.",
        reviewer_id_or_role=DETERMINISTIC_REVIEWER,
        strict_ex=scoring.strict_ex,
        deterministic_equivalence=False,
        root_cause_candidate=RootCause.UNKNOWN,
        confidence=0.4,
    )


# ---------------------------------------------------------------------------
# Two-independent-reviewer support (E05 §13)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdjudicationItem:
    """A case whose two reviewers disagreed; queued for independent adjudication."""

    case_id: str
    replicate_id: str
    reviewer_a: str
    reviewer_b: str
    grade_a: Grade
    grade_b: Grade
    subtype_a: BSubtype | None
    subtype_b: BSubtype | None
    reason: str


@dataclass
class ReviewMerge:
    """Outcome of comparing two independent reviewers for one replicate."""

    case_id: str
    replicate_id: str
    agree: bool
    #: The agreed record when reviewers agree; else None (goes to adjudication).
    consensus: SemanticAuditRecord | None
    adjudication_item: AdjudicationItem | None


def merge_reviews(
    review_a: SemanticAuditRecord,
    review_b: SemanticAuditRecord,
) -> ReviewMerge:
    """Compare two independent reviewers. Never majority-votes (E05 §13).

    Agreement requires the same grade (and, for B, the same subtype). Any
    disagreement produces an :class:`AdjudicationItem` and NO consensus record —
    the framework refuses to invent a winner from two opinions.
    """

    if review_a.case_id != review_b.case_id or review_a.replicate_id != review_b.replicate_id:
        raise ValueError("Cannot merge reviews for different (case, replicate).")

    same_grade = review_a.classification == review_b.classification
    same_subtype = review_a.subtype == review_b.subtype
    agree = same_grade and (review_a.classification is not Grade.B or same_subtype)

    if agree:
        return ReviewMerge(
            case_id=review_a.case_id,
            replicate_id=review_a.replicate_id,
            agree=True,
            consensus=review_a,
            adjudication_item=None,
        )

    reason = (
        "grade_disagreement"
        if not same_grade
        else "b_subtype_disagreement"
    )
    return ReviewMerge(
        case_id=review_a.case_id,
        replicate_id=review_a.replicate_id,
        agree=False,
        consensus=None,
        adjudication_item=AdjudicationItem(
            case_id=review_a.case_id,
            replicate_id=review_a.replicate_id,
            reviewer_a=review_a.reviewer_id_or_role,
            reviewer_b=review_b.reviewer_id_or_role,
            grade_a=review_a.classification,
            grade_b=review_b.classification,
            subtype_a=review_a.subtype,
            subtype_b=review_b.subtype,
            reason=reason,
        ),
    )


@dataclass
class DisagreementReport:
    total: int
    agreements: int
    adjudication_queue: list[AdjudicationItem]

    @property
    def agreement_rate(self) -> float:
        return round(self.agreements / self.total, 4) if self.total else 0.0


def compute_disagreement(
    reviews_a: list[SemanticAuditRecord],
    reviews_b: list[SemanticAuditRecord],
) -> DisagreementReport:
    """Pair two reviewers' records by (case, replicate) and queue disagreements."""

    index_b = {(r.case_id, r.replicate_id): r for r in reviews_b}
    total = 0
    agreements = 0
    queue: list[AdjudicationItem] = []
    for rec_a in reviews_a:
        rec_b = index_b.get((rec_a.case_id, rec_a.replicate_id))
        if rec_b is None:
            continue
        total += 1
        merged = merge_reviews(rec_a, rec_b)
        if merged.agree:
            agreements += 1
        elif merged.adjudication_item is not None:
            queue.append(merged.adjudication_item)
    return DisagreementReport(total=total, agreements=agreements, adjudication_queue=queue)


# ---------------------------------------------------------------------------
# Advisory (non-authoritative) LLM reviewer contract (E05 §12)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvisoryLLMReviewInput:
    """Exactly what an advisory LLM reviewer is shown; persisted verbatim."""

    case_id: str
    replicate_id: str
    question: str | None
    schema_context: str | None
    candidate_sql: str | None
    gold_sql: str | None
    candidate_fingerprint: str | None
    gold_fingerprint: str | None
    rubric_version: str
    model: str
    temperature: float


@dataclass(frozen=True)
class AdvisoryLLMReview:
    """An advisory opinion. NEVER authoritative over deterministic metrics."""

    proposed_grade: Grade
    rationale: str
    confidence: float
    input_ref: AdvisoryLLMReviewInput


class AdvisoryLLMReviewer(Protocol):
    """Optional advisory reviewer. Implementations must be pure w.r.t. runtime."""

    def review(self, review_input: AdvisoryLLMReviewInput) -> AdvisoryLLMReview: ...


@dataclass
class AdvisoryReconciliation:
    """Result of comparing an advisory opinion to the deterministic record."""

    deterministic: SemanticAuditRecord
    advisory: AdvisoryLLMReview
    agrees: bool
    #: The deterministic record is always kept as authoritative.
    authoritative: SemanticAuditRecord = field(init=False)

    def __post_init__(self) -> None:
        self.authoritative = self.deterministic


def reconcile_advisory_with_deterministic(
    deterministic: SemanticAuditRecord,
    advisory: AdvisoryLLMReview,
) -> AdvisoryReconciliation:
    """Surface (never resolve by overwrite) advisory-vs-deterministic conflict.

    The deterministic record remains authoritative (E05 §12). Disagreement is
    recorded for human adjudication, not silently applied.
    """

    return AdvisoryReconciliation(
        deterministic=deterministic,
        advisory=advisory,
        agrees=deterministic.classification == advisory.proposed_grade,
    )
