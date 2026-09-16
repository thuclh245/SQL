"""Schema mutation tests demonstrating metadata resilience against renamed identifiers."""

import pytest

from t2s.contracts import ColumnContext, GroundingContext, QueryRequest, TableContext
from t2s.semantics.semantic_plan import MetricAggregation, PlannerStatus
from t2s.semantics.semantic_planner import GroundedSemanticPlanner


@pytest.mark.anyio
async def test_schema_mutation_preserves_semantic_grounding() -> None:
    baseline_table = TableContext(
        fqn="corp.usage_records",
        sql_identifier="usage_records",
        columns=[
            ColumnContext(name="record_id", data_type="INTEGER", is_primary_key=True),
            ColumnContext(
                name="total_usage_kwh",
                data_type="NUMERIC",
                description="Total electricity usage recorded in kWh units per billing period",
            ),
        ],
    )
    mutated_table = TableContext(
        fqn="corp.data_table_771",
        sql_identifier="data_table_771",
        columns=[
            ColumnContext(name="c_id", data_type="INTEGER", is_primary_key=True),
            ColumnContext(
                name="m_val_99",
                data_type="NUMERIC",
                description="Total electricity usage recorded in kWh units per billing period",
            ),
        ],
    )

    planner = GroundedSemanticPlanner()
    req = QueryRequest(question="What is the total electricity usage?")

    baseline_plan = await planner.plan(
        query_request=req,
        grounding_context=GroundingContext(scope_id="test-scope", tables=[baseline_table]),
    )
    mutated_plan = await planner.plan(
        query_request=req,
        grounding_context=GroundingContext(scope_id="test-scope", tables=[mutated_table]),
    )

    assert baseline_plan.status == PlannerStatus.READY
    assert mutated_plan.status == PlannerStatus.READY

    assert baseline_plan.aggregation == MetricAggregation.SUM
    assert mutated_plan.aggregation == MetricAggregation.SUM

    assert mutated_plan.metric_name == "m_val_99"
    assert "data_table_771" in mutated_plan.relevant_tables
