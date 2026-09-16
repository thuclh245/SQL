"""Metamorphic test suite for semantic planning across linguistic variations."""

import pytest

from t2s.contracts import ColumnContext, GroundingContext, QueryRequest, TableContext
from t2s.semantics.semantic_plan import MetricAggregation, PlannerStatus
from t2s.semantics.semantic_planner import GroundedSemanticPlanner


def _build_synthetic_enterprise_schema() -> GroundingContext:
    accounts = TableContext(
        fqn="corp.accounts",
        sql_identifier="accounts",
        columns=[
            ColumnContext(name="account_id", data_type="INTEGER", is_primary_key=True),
            ColumnContext(name="account_name", data_type="TEXT"),
            ColumnContext(name="region_id", data_type="INTEGER"),
        ],
    )
    usage = TableContext(
        fqn="corp.usage_records",
        sql_identifier="usage_records",
        columns=[
            ColumnContext(name="record_id", data_type="INTEGER", is_primary_key=True),
            ColumnContext(name="account_id", data_type="INTEGER"),
            ColumnContext(
                name="total_usage_kwh",
                data_type="NUMERIC",
                description="Total electricity usage recorded in kWh units per billing period",
            ),
        ],
    )
    return GroundingContext(scope_id="test-scope", tables=[accounts, usage])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "phrase_pair",
    [
        (
            "What is the total electricity usage across all accounts?",
            "Calculate the sum of electricity usage for accounts.",
        ),
        (
            "What is the total electricity usage?",
            "Tổng lượng tiêu thụ điện là bao nhiêu?",
        ),
        (
            "How much total electricity was used?",
            "Total electricity usage recorded.",
        ),
    ],
)
async def test_metamorphic_semantic_plan_invariance(phrase_pair: tuple[str, str]) -> None:
    q1, q2 = phrase_pair
    planner = GroundedSemanticPlanner()
    context = _build_synthetic_enterprise_schema()

    req1 = QueryRequest(question=q1)
    req2 = QueryRequest(question=q2)

    plan1 = await planner.plan(query_request=req1, grounding_context=context)
    plan2 = await planner.plan(query_request=req2, grounding_context=context)

    assert plan1.status == PlannerStatus.READY
    assert plan2.status == PlannerStatus.READY

    assert plan1.aggregation == MetricAggregation.SUM
    assert plan2.aggregation == MetricAggregation.SUM

    assert "usage_records" in plan1.relevant_tables
    assert "usage_records" in plan2.relevant_tables
