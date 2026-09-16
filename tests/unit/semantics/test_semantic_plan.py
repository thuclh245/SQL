"""Unit tests for typed SemanticPlan immutable contracts."""

import pytest
from pydantic import ValidationError

from t2s.semantics.semantic_plan import (
    ExpectedValueType,
    MetricAggregation,
    PlannerStatus,
    ResultExpectation,
    ResultShape,
    SemanticEvidence,
    SemanticFilter,
    SemanticGrain,
    SemanticPlan,
)


def test_semantic_plan_instantiation_and_immutability() -> None:
    plan = SemanticPlan(
        plan_id="plan-123",
        status=PlannerStatus.READY,
        metric_name="annual_fee",
        aggregation=MetricAggregation.SUM,
        dimensions=["plan_type"],
        filters=[
            SemanticFilter(
                column_name="status",
                operator="=",
                target_value="active",
                evidence_source="active subscriptions only",
            ),
        ],
        grain=SemanticGrain(
            requested_grain="yearly",
            source_grain="year",
            requires_normalization=False,
        ),
        relevant_tables=["subscriptions"],
        relevant_columns=["subscriptions.annual_fee"],
        expectation=ResultExpectation(
            expected_shape=ResultShape.LIST,
            expected_value_type=ExpectedValueType.NUMERIC,
            can_be_empty=False,
        ),
        evidence=[
            SemanticEvidence(
                source="metadata_description",
                entity="column",
                field="description",
                value="annual fee in usd",
                confidence=1.0,
            ),
        ],
        semantic_uncertainty_level="LOW",
    )

    assert plan.plan_id == "plan-123"
    assert plan.status == PlannerStatus.READY
    assert plan.metric_name == "annual_fee"
    assert plan.aggregation == MetricAggregation.SUM
    assert plan.grain.source_grain == "year"
    assert len(plan.filters) == 1
    assert plan.filters[0].column_name == "status"

    # Immutability check
    with pytest.raises((ValidationError, TypeError)):
        plan.status = PlannerStatus.UNCERTAIN  # type: ignore[misc]


def test_semantic_plan_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SemanticPlan(
            plan_id="plan-999",
            status=PlannerStatus.READY,
            unexpected_attribute="forbidden_payload",  # type: ignore[call-arg]
        )


def test_result_expectation_defaults() -> None:
    expectation = ResultExpectation()
    assert expectation.expected_shape == ResultShape.UNKNOWN
    assert expectation.expected_value_type == ExpectedValueType.UNKNOWN
    assert expectation.can_be_empty is False


def test_semantic_plan_unanchored_defaults_and_demotion() -> None:
    # 1. Blank plan defaults to INSUFFICIENT_EVIDENCE and HIGH uncertainty
    blank_plan = SemanticPlan(plan_id="blank-1")
    assert blank_plan.status == PlannerStatus.INSUFFICIENT_EVIDENCE
    assert blank_plan.semantic_uncertainty_level == "HIGH"

    # 2. Plan claiming READY without any anchors is demoted
    demoted_plan = SemanticPlan(
        plan_id="demoted-1",
        status=PlannerStatus.READY,
        semantic_uncertainty_level="LOW",
    )
    assert demoted_plan.status == PlannerStatus.INSUFFICIENT_EVIDENCE
    assert demoted_plan.semantic_uncertainty_level == "HIGH"
