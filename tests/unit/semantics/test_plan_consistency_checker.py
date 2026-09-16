"""Unit tests for SemanticPlanConsistencyChecker."""

from t2s.semantics.plan_consistency_checker import SemanticPlanConsistencyChecker
from t2s.semantics.semantic_plan import (
    MetricAggregation,
    PlannerStatus,
    SemanticPlan,
)


def test_consistency_checker_catches_missing_aggregation() -> None:
    plan = SemanticPlan(
        plan_id="plan-1",
        status=PlannerStatus.READY,
        metric_name="revenue",
        aggregation=MetricAggregation.SUM,
        relevant_tables=["user_events"],
    )
    sql = "SELECT revenue FROM user_events"
    checker = SemanticPlanConsistencyChecker()
    result = checker.check_alignment(plan=plan, sql=sql)
    assert not result.is_consistent
    assert any("aggregation" in m.lower() for m in result.mismatches)


def test_consistency_checker_accepts_valid_aggregation() -> None:
    plan = SemanticPlan(
        plan_id="plan-2",
        status=PlannerStatus.READY,
        metric_name="revenue",
        aggregation=MetricAggregation.SUM,
        relevant_tables=["user_events"],
    )
    sql = "SELECT SUM(revenue) AS total_revenue FROM user_events"
    checker = SemanticPlanConsistencyChecker()
    result = checker.check_alignment(plan=plan, sql=sql)
    assert result.is_consistent
    assert len(result.mismatches) == 0


def test_consistency_checker_catches_missing_group_by() -> None:
    plan = SemanticPlan(
        plan_id="plan-3",
        status=PlannerStatus.READY,
        metric_name="revenue",
        aggregation=MetricAggregation.SUM,
        dimensions=["user_id"],
        relevant_tables=["user_events"],
    )
    sql = "SELECT user_id, SUM(revenue) FROM user_events"
    checker = SemanticPlanConsistencyChecker()
    result = checker.check_alignment(plan=plan, sql=sql)
    assert not result.is_consistent
    assert any("group by" in m.lower() for m in result.mismatches)


def test_consistency_checker_accepts_valid_group_by() -> None:
    plan = SemanticPlan(
        plan_id="plan-4",
        status=PlannerStatus.READY,
        metric_name="revenue",
        aggregation=MetricAggregation.SUM,
        dimensions=["user_id"],
        relevant_tables=["user_events"],
    )
    sql = "SELECT user_id, SUM(revenue) FROM user_events GROUP BY user_id"
    checker = SemanticPlanConsistencyChecker()
    result = checker.check_alignment(plan=plan, sql=sql)
    assert result.is_consistent
    assert len(result.mismatches) == 0


def test_consistency_checker_handles_syntax_error() -> None:
    plan = SemanticPlan(
        plan_id="plan-5",
        status=PlannerStatus.READY,
        relevant_tables=["user_events"],
    )
    sql = "SELECT FROM WHERE INVALID SQL @@@"
    checker = SemanticPlanConsistencyChecker()
    result = checker.check_alignment(plan=plan, sql=sql)
    assert not result.is_consistent
    assert result.failure_code == "PLAN_SQL_PARSE_ERROR"
