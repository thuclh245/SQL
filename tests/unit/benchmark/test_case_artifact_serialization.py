from datetime import UTC, datetime

from t2s.benchmark.case_loader import BenchmarkCaseBundle, InferenceBenchmarkCase, ScoringGold
from t2s.benchmark.runner import _build_infrastructure_failure_result, _serialize_case_result
from t2s.runtime import RuntimeExecutionResult, RuntimeStatus, RuntimeTrace
from t2s.runtime.runtime_contracts import RuntimeState


def test_case_artifact_serialization_excludes_gold_sql() -> None:
    case_bundle = BenchmarkCaseBundle(
        inference_case=InferenceBenchmarkCase(
            case_id="case-1",
            question_id=1,
            db_id="db",
            question="Question",
            evidence="Evidence",
            bird_difficulty="simple",
            t2s_stratum="S1",
        ),
        scoring_gold=ScoringGold(
            official_sql="SELECT secret_gold FROM hidden_table",
            curated_sql=None,
        ),
    )
    runtime_result = RuntimeExecutionResult(
        run_id="run-1",
        status=RuntimeStatus.COMPLETED,
        sql="SELECT name FROM customers",
        dialect="sqlite",
        columns=["name"],
        rows=[{"name": "Ada"}],
        row_count=1,
        total_latency_ms=12.5,
        trace=RuntimeTrace(
            run_id="run-1",
            final_state=RuntimeState.COMPLETED,
            safety_check_passed=True,
            access_check_passed=True,
            execution_passed=True,
        ),
    )

    artifact = _serialize_case_result(
        case_bundle=case_bundle,
        runtime_result=runtime_result,
        execution_correct=True,
        gold_execution_ok=True,
    )

    assert artifact["runtime_status"] == "SUCCESS"
    assert artifact["generated_sql"] == "SELECT name FROM customers"
    assert "gold" not in artifact
    assert "SELECT secret_gold" not in str(artifact)


def test_completed_incorrect_result_is_classified_as_sql_incorrect() -> None:
    artifact = _serialize_case_result(
        case_bundle=_case_bundle(),
        runtime_result=_runtime_result(RuntimeStatus.COMPLETED),
        execution_correct=False,
        gold_execution_ok=True,
    )

    assert artifact["failure_taxonomy"] == "SQL_INCORRECT"


def test_non_semantic_runtime_failures_are_not_classified_as_sql_incorrect() -> None:
    safety_artifact = _serialize_case_result(
        case_bundle=_case_bundle(),
        runtime_result=_runtime_result(RuntimeStatus.SAFETY_REJECTED),
        execution_correct=None,
        gold_execution_ok=False,
    )
    execution_artifact = _serialize_case_result(
        case_bundle=_case_bundle(),
        runtime_result=_runtime_result(RuntimeStatus.EXECUTION_FAILED),
        execution_correct=None,
        gold_execution_ok=False,
    )
    provider_artifact = _build_infrastructure_failure_result(
        case_bundle=_case_bundle(),
        exc=TimeoutError("provider timeout"),
        started_at=datetime.now(UTC),
    )

    assert safety_artifact["failure_taxonomy"] == "SAFETY_REJECTED"
    assert execution_artifact["failure_taxonomy"] == "EXECUTION_ERROR"
    assert provider_artifact["failure_taxonomy"] != "SQL_INCORRECT"


def _case_bundle() -> BenchmarkCaseBundle:
    return BenchmarkCaseBundle(
        inference_case=InferenceBenchmarkCase(
            case_id="case-1",
            question_id=1,
            db_id="db",
            question="Question",
            evidence="Evidence",
            bird_difficulty="simple",
            t2s_stratum="S1",
        ),
        scoring_gold=ScoringGold(
            official_sql="SELECT secret_gold FROM hidden_table",
            curated_sql=None,
        ),
    )


def _runtime_result(status: RuntimeStatus) -> RuntimeExecutionResult:
    return RuntimeExecutionResult(
        run_id="run-1",
        status=status,
        sql="SELECT name FROM customers" if status == RuntimeStatus.COMPLETED else None,
        dialect="sqlite",
        columns=["name"] if status == RuntimeStatus.COMPLETED else [],
        rows=[{"name": "Ada"}] if status == RuntimeStatus.COMPLETED else [],
        row_count=1 if status == RuntimeStatus.COMPLETED else 0,
        total_latency_ms=12.5,
        trace=RuntimeTrace(
            run_id="run-1",
            final_state=(
                RuntimeState.COMPLETED
                if status == RuntimeStatus.COMPLETED
                else RuntimeState.EXECUTION_FAILED
            ),
            safety_check_passed=status != RuntimeStatus.SAFETY_REJECTED,
            access_check_passed=status
            not in {RuntimeStatus.SAFETY_REJECTED, RuntimeStatus.ACCESS_DENIED},
            execution_passed=status == RuntimeStatus.COMPLETED,
        ),
    )
