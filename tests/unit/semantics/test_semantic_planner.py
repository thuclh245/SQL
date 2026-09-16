"""Unit tests for GroundedSemanticPlanner."""

import pytest

from t2s.contracts import ColumnContext, GroundingContext, QueryRequest, TableContext
from t2s.semantics.semantic_plan import (
    MetricAggregation,
    PlannerStatus,
    ResultShape,
)
from t2s.semantics.semantic_planner import GroundedSemanticPlanner


def _build_synthetic_grounding_context() -> GroundingContext:
    table = TableContext(
        fqn="analytics.user_events",
        sql_identifier="user_events",
        columns=[
            ColumnContext(
                name="event_id",
                data_type="INTEGER",
                is_primary_key=True,
                description="Primary key of event",
            ),
            ColumnContext(
                name="user_id",
                data_type="INTEGER",
                description="Foreign key of user",
            ),
            ColumnContext(
                name="event_count",
                data_type="INTEGER",
                description="Count of events per day",
            ),
            ColumnContext(
                name="revenue",
                data_type="NUMERIC",
                description="Revenue generated from transaction in USD",
            ),
        ],
    )
    return GroundingContext(scope_id="test-scope", tables=[table])


@pytest.mark.anyio
async def test_planner_empty_context_unresolved() -> None:
    planner = GroundedSemanticPlanner()
    context = GroundingContext(scope_id="test-scope", tables=[])
    req = QueryRequest(question="What is the total revenue?")
    plan = await planner.plan(query_request=req, grounding_context=context)
    assert plan.status == PlannerStatus.INSUFFICIENT_EVIDENCE
    assert plan.semantic_uncertainty_level == "HIGH"


@pytest.mark.anyio
async def test_planner_sum_aggregation_detected() -> None:
    planner = GroundedSemanticPlanner()
    context = _build_synthetic_grounding_context()
    req = QueryRequest(question="What is the total revenue?")
    plan = await planner.plan(query_request=req, grounding_context=context)
    assert plan.status == PlannerStatus.READY
    assert "user_events" in plan.relevant_tables
    assert plan.aggregation == MetricAggregation.SUM
    assert plan.expectation.expected_shape == ResultShape.SCALAR
    assert plan.expectation.can_be_empty is False


@pytest.mark.anyio
async def test_planner_average_aggregation_detected() -> None:
    planner = GroundedSemanticPlanner()
    context = _build_synthetic_grounding_context()
    req = QueryRequest(question="What is the average revenue?")
    plan = await planner.plan(query_request=req, grounding_context=context)
    assert plan.status == PlannerStatus.READY
    assert plan.aggregation == MetricAggregation.AVG


@pytest.mark.anyio
async def test_planner_missing_grain_flags_high_uncertainty() -> None:
    bare_table = TableContext(
        fqn="analytics.raw_metrics",
        sql_identifier="raw_metrics",
        columns=[
            ColumnContext(name="metric_val", data_type="NUMERIC"),
        ],
    )
    planner = GroundedSemanticPlanner()
    context = GroundingContext(scope_id="test-scope", tables=[bare_table])
    req = QueryRequest(question="Show me metric_val")
    plan = await planner.plan(query_request=req, grounding_context=context)
    assert plan.grain.source_grain == "unknown"
    assert plan.semantic_uncertainty_level == "HIGH"
    assert "UNKNOWN_METRIC_GRAIN" in plan.uncertainties
