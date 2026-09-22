"""Two-independent-reviewer merge, adjudication queue, advisory LLM contract."""

from __future__ import annotations

from t2s.evaluation.scoring.records import new_semantic_audit_record
from t2s.evaluation.scoring.semantic_audit import (
    AdvisoryLLMReview,
    AdvisoryLLMReviewInput,
    compute_disagreement,
    merge_reviews,
    reconcile_advisory_with_deterministic,
)
from t2s.evaluation.scoring.taxonomy import BSubtype, Grade


def _rev(reviewer: str, grade: Grade, subtype: BSubtype | None = None):
    return new_semantic_audit_record(
        case_id="c1",
        replicate_id="r1",
        classification=grade,
        subtype=subtype,
        rationale="test",
        reviewer_id_or_role=reviewer,
    )


def test_agreement_produces_consensus() -> None:
    merged = merge_reviews(_rev("A", Grade.A), _rev("B", Grade.A))
    assert merged.agree
    assert merged.consensus is not None
    assert merged.adjudication_item is None


def test_disagreement_goes_to_adjudication_no_majority_vote() -> None:
    merged = merge_reviews(_rev("A", Grade.B, BSubtype.B1_EXTRA_COLUMNS), _rev("B", Grade.D))
    assert not merged.agree
    assert merged.consensus is None  # never invents a winner from two opinions
    assert merged.adjudication_item is not None
    assert merged.adjudication_item.grade_a is Grade.B
    assert merged.adjudication_item.grade_b is Grade.D


def test_b_subtype_disagreement_is_flagged() -> None:
    merged = merge_reviews(
        _rev("A", Grade.B, BSubtype.B1_EXTRA_COLUMNS),
        _rev("B", Grade.B, BSubtype.B4_ROW_ORDER),
    )
    assert not merged.agree
    assert merged.adjudication_item is not None
    assert merged.adjudication_item.reason == "b_subtype_disagreement"


def test_disagreement_report_rate() -> None:
    reviews_a = [_rev("A", Grade.A), _rev("A", Grade.D)]
    reviews_b = [_rev("B", Grade.A), _rev("B", Grade.C)]
    reviews_b[1] = new_semantic_audit_record(
        case_id="c2", replicate_id="r1", classification=Grade.C,
        rationale="t", reviewer_id_or_role="B",
    )
    reviews_a[1] = new_semantic_audit_record(
        case_id="c2", replicate_id="r1", classification=Grade.D,
        rationale="t", reviewer_id_or_role="A",
    )
    report = compute_disagreement(reviews_a, reviews_b)
    assert report.total == 2
    assert report.agreements == 1
    assert len(report.adjudication_queue) == 1


def test_advisory_never_overrides_deterministic() -> None:
    deterministic = _rev("deterministic", Grade.A)
    advisory = AdvisoryLLMReview(
        proposed_grade=Grade.D,
        rationale="model thinks it's wrong",
        confidence=0.8,
        input_ref=AdvisoryLLMReviewInput(
            case_id="c1",
            replicate_id="r1",
            question="q",
            schema_context="s",
            candidate_sql="SELECT 1",
            gold_sql="SELECT 1",
            candidate_fingerprint="x",
            gold_fingerprint="x",
            rubric_version="rubric.v1",
            model="advisor-model",
            temperature=0.0,
        ),
    )
    reconciliation = reconcile_advisory_with_deterministic(deterministic, advisory)
    assert reconciliation.agrees is False
    # Authoritative record is ALWAYS the deterministic one.
    assert reconciliation.authoritative is deterministic
    assert reconciliation.authoritative.classification is Grade.A
