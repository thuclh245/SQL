"""Unit tests for P6 runtime contracts and lifecycle state machine."""

from t2s.orchestration.escalation_contracts import OrchestrationOutcome
from t2s.runtime import (
    RuntimeExecutionResult,
    RuntimeState,
    RuntimeStatus,
    RuntimeTrace,
    StateTransitionRecord,
)


def test_runtime_state_values() -> None:
    assert RuntimeState.RECEIVED.value == "received"
    assert RuntimeState.COMPLETED.value == "completed"
    assert RuntimeState.SAFETY_REJECTED.value == "safety_rejected"
    assert RuntimeState.ACCESS_DENIED.value == "access_denied"
    assert RuntimeState.EXECUTION_FAILED.value == "execution_failed"
    assert RuntimeState.TIMEOUT.value == "timeout"


def test_state_transition_record() -> None:
    record = StateTransitionRecord(
        from_state=RuntimeState.RECEIVED,
        to_state=RuntimeState.GROUNDED_GENERATED,
        elapsed_ms=12.5,
    )
    assert record.from_state == RuntimeState.RECEIVED
    assert record.to_state == RuntimeState.GROUNDED_GENERATED
    assert record.elapsed_ms == 12.5


def test_completed_result_to_query_response_conversion() -> None:
    result = RuntimeExecutionResult(
        run_id="run-123",
        status=RuntimeStatus.COMPLETED,
        sql="SELECT id, name FROM customers",
        dialect="sqlite",
        columns=["id", "name"],
        rows=[{"id": 1, "name": "Ada"}],
        row_count=1,
        execution_time_ms=5,
        total_latency_ms=25.0,
        orchestration_outcome=OrchestrationOutcome.BASELINE_SUCCESS,
        trace=RuntimeTrace(
            run_id="run-123",
            final_state=RuntimeState.COMPLETED,
            ast_referenced_tables=["customers"],
            safety_check_passed=True,
            access_check_passed=True,
            execution_passed=True,
        ),
    )

    query_response = result.to_query_response(request_id="req-1", trace_id="tr-1")
    assert query_response.request_id == "req-1"
    assert query_response.run_id == "run-123"
    assert query_response.trace_id == "tr-1"
    assert query_response.status == "answer"
    assert query_response.answer is not None
    assert query_response.answer.columns == ["id", "name"]
    assert len(query_response.answer.rows) == 1
    assert query_response.sql == "SELECT id, name FROM customers"


def test_unresolved_result_to_query_response_conversion() -> None:
    result = RuntimeExecutionResult(
        run_id="run-unresolved",
        status=RuntimeStatus.UNRESOLVED,
        error_message="Query could not be resolved.",
        trace=RuntimeTrace(
            run_id="run-unresolved",
            final_state=RuntimeState.UNRESOLVED,
        ),
    )

    query_response = result.to_query_response(request_id="req-2", trace_id="tr-2")
    assert query_response.status == "abstain"
    assert query_response.answer is None
    assert query_response.decision.policy == "safe-runtime-v1"
    assert query_response.decision.reason == "unresolved"


def test_safety_rejected_result_to_query_response_conversion() -> None:
    result = RuntimeExecutionResult(
        run_id="run-unsafe",
        status=RuntimeStatus.SAFETY_REJECTED,
        sql="DROP TABLE customers",
        error_message="SQL root statement must be read-only.",
        trace=RuntimeTrace(
            run_id="run-unsafe",
            final_state=RuntimeState.SAFETY_REJECTED,
        ),
    )

    query_response = result.to_query_response(request_id="req-3", trace_id="tr-3")
    assert query_response.status == "abstain"
    assert query_response.answer is None
    assert query_response.decision.policy == "security-gate-v1"
    assert query_response.decision.reason == "safety_rejected"


def test_access_denied_result_to_query_response_conversion() -> None:
    result = RuntimeExecutionResult(
        run_id="run-denied",
        status=RuntimeStatus.ACCESS_DENIED,
        sql="SELECT salary FROM secret_payroll",
        error_message="SQL references unauthorized resources: secret_payroll",
        trace=RuntimeTrace(
            run_id="run-denied",
            final_state=RuntimeState.ACCESS_DENIED,
        ),
    )

    query_response = result.to_query_response(request_id="req-4", trace_id="tr-4")
    assert query_response.status == "abstain"
    assert query_response.decision.policy == "security-gate-v1"
    assert query_response.decision.reason == "access_denied"


def test_execution_failed_result_to_query_response_conversion() -> None:
    result = RuntimeExecutionResult(
        run_id="run-failed",
        status=RuntimeStatus.EXECUTION_FAILED,
        sql="SELECT missing FROM customers",
        error_message="no such column: missing",
        trace=RuntimeTrace(
            run_id="run-failed",
            final_state=RuntimeState.EXECUTION_FAILED,
        ),
    )

    query_response = result.to_query_response(request_id="req-5", trace_id="tr-5")
    assert query_response.status == "error"
    assert query_response.decision.policy == "execution-gate-v1"
    assert query_response.decision.reason == "execution_failed"
