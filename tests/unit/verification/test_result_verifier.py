"""Unit tests for ResultVerifier evaluating query execution outputs."""

import pytest

from t2s.database.query_execution_result import QueryExecutionResult
from t2s.semantics.semantic_plan import (
    ExpectedValueType,
    MetricAggregation,
    PlannerStatus,
    ResultExpectation,
    ResultShape,
    SemanticPlan,
)
from t2s.verification.result_verifier import (
    ResultVerificationDecision,
    ResultVerifier,
)


def test_result_verifier_detects_suspicious_null_scalar() -> None:
    plan = SemanticPlan(
        plan_id="plan-1",
        status=PlannerStatus.READY,
        metric_name="sum_revenue",
        aggregation=MetricAggregation.SUM,
        relevant_tables=["transactions"],
        expectation=ResultExpectation(
            expected_shape=ResultShape.SCALAR,
            expected_value_type=ExpectedValueType.NUMERIC,
            can_be_empty=False,
        ),
    )
    exec_result = QueryExecutionResult(
        columns=["sum_revenue"],
        rows=[{"sum_revenue": None}],
        row_count=1,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan)
    assert outcome.is_suspicious
    assert outcome.decision == ResultVerificationDecision.SUSPICIOUS
    assert outcome.failure_code == "SUSPICIOUS_NULL_RESULT"
    assert outcome.recommended_probe == "METRIC_NON_NULL_PROBE"


def test_result_verifier_accepts_valid_zero() -> None:
    plan = SemanticPlan(
        plan_id="plan-2",
        status=PlannerStatus.READY,
        metric_name="sum_revenue",
        aggregation=MetricAggregation.SUM,
        relevant_tables=["transactions"],
        expectation=ResultExpectation(
            expected_shape=ResultShape.SCALAR,
            expected_value_type=ExpectedValueType.NUMERIC,
            can_be_empty=False,
        ),
    )
    exec_result = QueryExecutionResult(
        columns=["sum_revenue"],
        rows=[{"sum_revenue": 0}],
        row_count=1,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan)
    assert not outcome.is_suspicious
    assert outcome.decision == ResultVerificationDecision.ACCEPT


def test_result_verifier_detects_empty_result_when_disallowed() -> None:
    plan = SemanticPlan(
        plan_id="plan-3",
        status=PlannerStatus.READY,
        relevant_tables=["transactions"],
        expectation=ResultExpectation(
            expected_shape=ResultShape.LIST,
            can_be_empty=False,
        ),
    )
    exec_result = QueryExecutionResult(
        columns=["tx_id", "amount"],
        rows=[],
        row_count=0,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan)
    assert outcome.is_suspicious
    assert outcome.failure_code == "SUSPICIOUS_EMPTY_RESULT"
    assert outcome.recommended_probe == "POPULATION_COUNT_PROBE"


def test_result_verifier_accepts_empty_result_when_allowed() -> None:
    plan = SemanticPlan(
        plan_id="plan-4",
        status=PlannerStatus.READY,
        relevant_tables=["transactions"],
        expectation=ResultExpectation(
            expected_shape=ResultShape.LIST,
            can_be_empty=True,
        ),
    )
    exec_result = QueryExecutionResult(
        columns=["tx_id", "amount"],
        rows=[],
        row_count=0,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan)
    assert not outcome.is_suspicious
    assert outcome.decision == ResultVerificationDecision.ACCEPT


def test_result_verifier_detects_all_rows_null() -> None:
    plan = SemanticPlan(
        plan_id="plan-5",
        status=PlannerStatus.READY,
        relevant_tables=["transactions"],
    )
    exec_result = QueryExecutionResult(
        columns=["col_a", "col_b"],
        rows=[
            {"col_a": None, "col_b": None},
            {"col_a": None, "col_b": None},
        ],
        row_count=2,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan)
    assert outcome.is_suspicious
    assert outcome.failure_code == "ALL_ROWS_NULL"


def test_result_verifier_decoupled_mode_catches_empty_result() -> None:
    exec_result = QueryExecutionResult(
        columns=["id", "name"],
        rows=[],
        row_count=0,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan=None)
    assert outcome.is_suspicious
    assert outcome.failure_code == "SUSPICIOUS_EMPTY_RESULT"
    assert outcome.recommended_probe == "POPULATION_COUNT_PROBE"


def test_result_verifier_decoupled_mode_catches_null_scalar() -> None:
    exec_result = QueryExecutionResult(
        columns=["avg_salary"],
        rows=[{"avg_salary": None}],
        row_count=1,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan=None)
    assert outcome.is_suspicious
    assert outcome.failure_code == "SUSPICIOUS_NULL_RESULT"
    assert outcome.recommended_probe == "METRIC_NON_NULL_PROBE"


def test_result_verifier_decoupled_mode_preserves_zero() -> None:
    exec_result = QueryExecutionResult(
        columns=["total_count"],
        rows=[{"total_count": 0}],
        row_count=1,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan=None)
    assert not outcome.is_suspicious
    assert outcome.decision == ResultVerificationDecision.ACCEPT


def test_result_verifier_decoupled_mode_catches_all_rows_null() -> None:
    exec_result = QueryExecutionResult(
        columns=["col_a", "col_b"],
        rows=[
            {"col_a": None, "col_b": None},
            {"col_a": None, "col_b": None},
        ],
        row_count=2,
    )
    verifier = ResultVerifier()
    outcome = verifier.verify_result(exec_result, plan=None)
    assert outcome.is_suspicious
    assert outcome.failure_code == "ALL_ROWS_NULL"


@pytest.mark.anyio
async def test_runtime_planner_off_result_verifier_on_catches_empty() -> None:
    """Verify that TextToSqlRuntime supports Planner OFF + ResultVerifier ON."""
    from unittest.mock import AsyncMock, MagicMock

    from t2s.contracts import GenerationTrace, QueryRequest, SqlCandidate
    from t2s.contracts.grounding_context import GroundingContext
    from t2s.orchestration.escalation_contracts import (
        OrchestrationOutcome,
        OrchestrationResult,
        OrchestrationTrace,
    )
    from t2s.runtime.text_to_sql_runtime import TextToSqlRuntime
    from t2s.security import UserIdentity

    orchestrator = MagicMock()
    candidate = SqlCandidate(
        sql="SELECT id FROM users WHERE status = 'missing'",
        dialect="sqlite",
        generation_trace=GenerationTrace(
            run_id="test-run",
            prompt_version="v1",
            model_name="test-model",
            elapsed_ms=10,
        ),
    )
    orch_result = OrchestrationResult(
        outcome=OrchestrationOutcome.BASELINE_SUCCESS,
        sql_candidate=candidate,
        grounding_context=GroundingContext(scope_id="test", tables=[]),
        semantic_plan=None,  # Planner is OFF
        trace=OrchestrationTrace(
            run_id="test-run",
            outcome=OrchestrationOutcome.BASELINE_SUCCESS,
            total_grounding_calls=1,
            total_solver_calls=1,
        ),
    )
    orchestrator.run = AsyncMock(return_value=orch_result)

    parser = MagicMock()
    parsed_sql = MagicMock()
    parsed_sql.referenced_table_identifiers.return_value = ["users"]
    parser.parse_single_statement.return_value = parsed_sql

    safety = MagicMock()
    access = MagicMock()

    executor = MagicMock()
    # Query execution returns 0 rows
    executor.execute_read_only_query.return_value = QueryExecutionResult(
        columns=["id"],
        rows=[],
        row_count=0,
        elapsed_ms=1,
    )

    runtime = TextToSqlRuntime(
        adaptive_orchestrator=orchestrator,
        sql_access_validator=access,
        query_executor=executor,
        sql_ast_parser=parser,
        sql_safety_validator=safety,
        default_dialect="sqlite",
        result_verifier=ResultVerifier(),  # ResultVerifier is ON
    )

    res = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="Find missing users"),
        user_identity=UserIdentity(user_id="test-user"),
    )

    assert res.semantic_plan is None
    assert res.result_verification_outcome is not None
    assert res.result_verification_outcome.is_suspicious is True
    assert res.result_verification_outcome.failure_code == "SUSPICIOUS_EMPTY_RESULT"
