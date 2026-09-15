from unittest.mock import AsyncMock, MagicMock

import pytest

from t2s.contracts import GenerationTrace, QueryRequest, SqlCandidate
from t2s.database import QueryExecutionPolicy, QueryExecutionResult
from t2s.orchestration.escalation_contracts import OrchestrationOutcome, OrchestrationResult
from t2s.runtime.runtime_contracts import (
    RuntimeState,
    RuntimeStatus,
    VerifierMode,
)
from t2s.runtime.text_to_sql_runtime import TextToSqlRuntime
from t2s.security import UserIdentity
from t2s.verification.contracts import (
    CheckStatus,
    SemanticCheckResult,
    VerificationDecision,
    VerificationResult,
)


def _make_verification_result(decision: VerificationDecision) -> VerificationResult:
    status = CheckStatus.PASS if decision == VerificationDecision.ACCEPT else CheckStatus.FAIL
    chk = SemanticCheckResult(status=status, short_reason="test")
    return VerificationResult(
        projection=chk,
        aggregation_and_grain=chk,
        filters_and_values=chk,
        join_semantics=chk,
        ordering_and_limit=chk,
        null_semantics=chk,
        schema_reference=chk,
        decision=decision,
        failed_checks=[] if decision == VerificationDecision.ACCEPT else ["projection"],
    )


@pytest.fixture
def mock_deps():
    orchestrator = MagicMock()
    candidate = SqlCandidate(
        sql="SELECT id FROM users",
        dialect="sqlite",
        generation_trace=GenerationTrace(
            run_id="test-run",
            prompt_version="v1",
            model_name="test-model",
            elapsed_ms=10,
        ),
    )
    from t2s.contracts.grounding_context import ColumnContext, GroundingContext, TableContext
    from t2s.orchestration.escalation_contracts import OrchestrationTrace

    ctx = GroundingContext(
        scope_id="test",
        tables=[
            TableContext(
                fqn="users",
                sql_identifier="users",
                columns=[ColumnContext(name="id", data_type="INTEGER")],
            )
        ],
    )
    orch_trace = OrchestrationTrace(
        run_id="test-run",
        outcome=OrchestrationOutcome.BASELINE_SUCCESS,
        total_grounding_calls=1,
        total_solver_calls=1,
    )
    orch_result = OrchestrationResult(
        outcome=OrchestrationOutcome.BASELINE_SUCCESS,
        sql_candidate=candidate,
        grounding_context=ctx,
        trace=orch_trace,
    )
    orchestrator.run = AsyncMock(return_value=orch_result)

    parser = MagicMock()
    parsed_sql = MagicMock()
    parsed_sql.referenced_table_identifiers.return_value = ["users"]
    parser.parse_single_statement.return_value = parsed_sql

    safety = MagicMock()
    safety.validate_read_only_sql.return_value = None

    access = MagicMock()
    access.validate_table_access.return_value = None

    executor = MagicMock()
    executor.execute_read_only_query.return_value = QueryExecutionResult(
        columns=["id"],
        rows=[{"id": 1}],
        row_count=1,
        elapsed_ms=5,
    )

    policy = QueryExecutionPolicy(timeout_seconds=5, max_row_limit=100)
    identity = UserIdentity(user_id="user1", roles=["analyst"])
    request = QueryRequest(question="Find all user IDs", target_hint="")

    return {
        "orchestrator": orchestrator,
        "parser": parser,
        "safety": safety,
        "access": access,
        "executor": executor,
        "policy": policy,
        "identity": identity,
        "request": request,
    }


@pytest.mark.anyio
async def test_verifier_gate_off_mode(mock_deps):
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock()

    runtime = TextToSqlRuntime(
        adaptive_orchestrator=mock_deps["orchestrator"],
        sql_ast_parser=mock_deps["parser"],
        sql_safety_validator=mock_deps["safety"],
        sql_access_validator=mock_deps["access"],
        query_executor=mock_deps["executor"],
        execution_policy=mock_deps["policy"],
        verifier=mock_verifier,
        verifier_mode=VerifierMode.OFF,
    )

    res = await runtime.execute_query_pipeline(
        query_request=mock_deps["request"],
        user_identity=mock_deps["identity"],
    )

    assert res.status == RuntimeStatus.COMPLETED
    assert res.sql == "SELECT id FROM users"
    mock_verifier.verify.assert_not_called()
    assert res.verifier_outcome is None


@pytest.mark.anyio
async def test_verifier_gate_accept_executes(mock_deps):
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(
        return_value=_make_verification_result(VerificationDecision.ACCEPT)
    )

    runtime = TextToSqlRuntime(
        adaptive_orchestrator=mock_deps["orchestrator"],
        sql_ast_parser=mock_deps["parser"],
        sql_safety_validator=mock_deps["safety"],
        sql_access_validator=mock_deps["access"],
        query_executor=mock_deps["executor"],
        execution_policy=mock_deps["policy"],
        verifier=mock_verifier,
        verifier_mode=VerifierMode.GATE_ONLY,
    )

    res = await runtime.execute_query_pipeline(
        query_request=mock_deps["request"],
        user_identity=mock_deps["identity"],
    )

    assert res.status == RuntimeStatus.COMPLETED
    assert res.sql == "SELECT id FROM users"
    mock_verifier.verify.assert_called_once()
    assert res.verifier_outcome is not None
    assert res.verifier_outcome.decision == "ACCEPT"
    mock_deps["executor"].execute_read_only_query.assert_called_once()


@pytest.mark.anyio
async def test_verifier_gate_reject_withholds_execution(mock_deps):
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(
        return_value=_make_verification_result(VerificationDecision.REJECT)
    )

    runtime = TextToSqlRuntime(
        adaptive_orchestrator=mock_deps["orchestrator"],
        sql_ast_parser=mock_deps["parser"],
        sql_safety_validator=mock_deps["safety"],
        sql_access_validator=mock_deps["access"],
        query_executor=mock_deps["executor"],
        execution_policy=mock_deps["policy"],
        verifier=mock_verifier,
        verifier_mode=VerifierMode.GATE_ONLY,
    )

    res = await runtime.execute_query_pipeline(
        query_request=mock_deps["request"],
        user_identity=mock_deps["identity"],
    )

    assert res.status == RuntimeStatus.UNRESOLVED
    assert res.sql is None
    mock_verifier.verify.assert_called_once()
    assert res.verifier_outcome is not None
    assert res.verifier_outcome.decision == "REJECT"
    mock_deps["executor"].execute_read_only_query.assert_not_called()
    assert res.trace.final_state == RuntimeState.UNRESOLVED


@pytest.mark.anyio
async def test_verifier_gate_abstain_withholds_execution(mock_deps):
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(
        return_value=_make_verification_result(VerificationDecision.ABSTAIN)
    )

    runtime = TextToSqlRuntime(
        adaptive_orchestrator=mock_deps["orchestrator"],
        sql_ast_parser=mock_deps["parser"],
        sql_safety_validator=mock_deps["safety"],
        sql_access_validator=mock_deps["access"],
        query_executor=mock_deps["executor"],
        execution_policy=mock_deps["policy"],
        verifier=mock_verifier,
        verifier_mode=VerifierMode.GATE_ONLY,
    )

    res = await runtime.execute_query_pipeline(
        query_request=mock_deps["request"],
        user_identity=mock_deps["identity"],
    )

    assert res.status == RuntimeStatus.UNRESOLVED
    assert res.sql is None
    mock_verifier.verify.assert_called_once()
    assert res.verifier_outcome is not None
    assert res.verifier_outcome.decision == "ABSTAIN"
    mock_deps["executor"].execute_read_only_query.assert_not_called()


@pytest.mark.anyio
async def test_verifier_gate_exception_fails_closed(mock_deps):
    mock_verifier = MagicMock()
    mock_verifier.verify = AsyncMock(side_effect=RuntimeError("OpenAI API unreachable"))

    runtime = TextToSqlRuntime(
        adaptive_orchestrator=mock_deps["orchestrator"],
        sql_ast_parser=mock_deps["parser"],
        sql_safety_validator=mock_deps["safety"],
        sql_access_validator=mock_deps["access"],
        query_executor=mock_deps["executor"],
        execution_policy=mock_deps["policy"],
        verifier=mock_verifier,
        verifier_mode=VerifierMode.GATE_ONLY,
    )

    res = await runtime.execute_query_pipeline(
        query_request=mock_deps["request"],
        user_identity=mock_deps["identity"],
    )

    assert res.status == RuntimeStatus.UNRESOLVED
    assert res.sql is None
    mock_verifier.verify.assert_called_once()
    assert res.verifier_outcome is not None
    assert res.verifier_outcome.decision == "ABSTAIN"
    assert "OpenAI API unreachable" in (res.verifier_outcome.error_message or "")
    mock_deps["executor"].execute_read_only_query.assert_not_called()
