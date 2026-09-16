"""Proves the runtime keeps blocking executor I/O off the asyncio event loop.

Executors satisfy a synchronous port, so a networked one (PostgreSQL) blocks its
thread for the whole query. If the runtime awaited that inline, a single slow query
would stall every other request, health checks included.
"""

import asyncio
import threading

import pytest

from t2s.contracts import GroundingContext, QueryRequest
from t2s.contracts.sql_candidate import GenerationTrace, SqlCandidate
from t2s.database import QueryExecutionPolicy, QueryExecutionResult, QueryExplainResult
from t2s.orchestration.escalation_contracts import (
    OrchestrationOutcome,
    OrchestrationResult,
    OrchestrationTrace,
)
from t2s.runtime import RuntimeStatus, TextToSqlRuntime
from t2s.runtime.runtime_contracts import ValidatorMode
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.verification import SqlAccessValidator

BLOCKING_CALL_TIMEOUT_SECONDS = 5.0


class StaticAccessPolicy:
    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return [
            AuthorizedSqlResource(
                catalog_fqn="warehouse.main.customers",
                sql_identifier="customers",
            )
        ]


class StubOrchestrator:
    """Returns a fixed candidate so the test isolates the execution stage."""

    async def run(self, **kwargs: object) -> OrchestrationResult:
        run_id = str(kwargs.get("run_id", "run-id"))
        return OrchestrationResult(
            outcome=OrchestrationOutcome.BASELINE_SUCCESS,
            sql_candidate=SqlCandidate(
                sql="SELECT id FROM customers",
                dialect="postgres",
                generation_trace=GenerationTrace(
                    run_id=run_id,
                    model_name="stub-model",
                    prompt_version="v001",
                ),
            ),
            grounding_context=GroundingContext(scope_id="scope-1", tables=[]),
            trace=OrchestrationTrace(
                run_id=run_id,
                outcome=OrchestrationOutcome.BASELINE_SUCCESS,
                total_grounding_calls=1,
                total_solver_calls=1,
            ),
        )


class GatedBlockingQueryExecutor:
    """Blocks its calling thread until another task releases it.

    If the executor ran on the event loop, the releasing task could never be
    scheduled and the call would deadlock instead of returning.
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.executing_thread_name: str | None = None

    def explain_query(self, sql: str, execution_policy: QueryExecutionPolicy) -> QueryExplainResult:
        raise NotImplementedError

    def execute_read_only_query(
        self,
        sql: str,
        execution_policy: QueryExecutionPolicy,
    ) -> QueryExecutionResult:
        self.executing_thread_name = threading.current_thread().name
        self.entered.set()
        if not self.release.wait(timeout=BLOCKING_CALL_TIMEOUT_SECONDS):
            raise AssertionError("Executor was never released; the event loop was blocked.")
        return QueryExecutionResult(columns=["id"], rows=[{"id": 1}], row_count=1)


def _build_runtime(query_executor: GatedBlockingQueryExecutor) -> TextToSqlRuntime:
    authorization_service = AuthorizationService(StaticAccessPolicy())
    return TextToSqlRuntime(
        adaptive_orchestrator=StubOrchestrator(),  # type: ignore[arg-type]
        sql_access_validator=SqlAccessValidator(authorization_service),
        query_executor=query_executor,
        default_dialect="postgres",
        validator_mode=ValidatorMode.DISABLED,
    )


@pytest.mark.anyio
async def test_event_loop_stays_responsive_while_a_query_blocks() -> None:
    query_executor = GatedBlockingQueryExecutor()
    runtime = _build_runtime(query_executor)

    async def release_once_the_query_is_running() -> None:
        # Only reachable if the event loop is still scheduling tasks.
        while not query_executor.entered.is_set():
            await asyncio.sleep(0.01)
        query_executor.release.set()

    pipeline_task = runtime.execute_query_pipeline(
        query_request=QueryRequest(question="How many customers?", database_dialect="postgres"),
        user_identity=UserIdentity(user_id="analyst-1"),
        run_id="run-1",
    )

    result, _ = await asyncio.wait_for(
        asyncio.gather(pipeline_task, release_once_the_query_is_running()),
        timeout=BLOCKING_CALL_TIMEOUT_SECONDS,
    )

    assert result.status == RuntimeStatus.COMPLETED
    assert result.rows == [{"id": 1}]


@pytest.mark.anyio
async def test_blocking_execution_runs_off_the_event_loop_thread() -> None:
    query_executor = GatedBlockingQueryExecutor()
    query_executor.release.set()
    runtime = _build_runtime(query_executor)

    main_thread_name = threading.current_thread().name
    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="How many customers?", database_dialect="postgres"),
        user_identity=UserIdentity(user_id="analyst-1"),
        run_id="run-1",
    )

    assert result.status == RuntimeStatus.COMPLETED
    assert query_executor.executing_thread_name != main_thread_name
