"""Production-oriented safe Text-to-SQL application runtime."""

from collections.abc import Callable
from time import perf_counter
from typing import Literal
from uuid import uuid4

from t2s.contracts import GroundingContext, QueryRequest, SqlCandidate
from t2s.contracts.sql_candidate import SupportedSqlDialect
from t2s.database import QueryExecutionPolicy, QueryExecutorPort
from t2s.database.secure_query_executor import QueryAuditEvent, QueryAuditSinkPort
from t2s.errors import (
    QueryExecutionError,
    QueryExecutionTimeoutError,
    UnauthorizedDataAccessError,
    UnsafeSqlError,
)
from t2s.observability.correlation import read_correlation_context
from t2s.orchestration import AdaptiveOrchestrator, OrchestrationOutcome
from t2s.runtime.runtime_contracts import (
    RuntimeExecutionResult,
    RuntimeState,
    RuntimeStatus,
    RuntimeTrace,
    StateTransitionRecord,
)
from t2s.security import UserIdentity
from t2s.solver import SolverRequest
from t2s.verification import SqlAccessValidator, SqlAstParser, SqlSafetyValidator


class TextToSqlRuntime:
    """Orchestrates end-to-end question processing with fail-closed safety gating.

    Coordinates:
    Orchestration (P5) -> AST Safety (P1) -> Authorization (P1) -> Read-Only Execution (P1)
    """

    def __init__(
        self,
        adaptive_orchestrator: AdaptiveOrchestrator,
        sql_access_validator: SqlAccessValidator,
        query_executor: QueryExecutorPort,
        sql_ast_parser: SqlAstParser | None = None,
        sql_safety_validator: SqlSafetyValidator | None = None,
        execution_policy: QueryExecutionPolicy | None = None,
        query_audit_sink: QueryAuditSinkPort | None = None,
        default_dialect: SupportedSqlDialect = "sqlite",
    ) -> None:
        self.adaptive_orchestrator = adaptive_orchestrator
        self.sql_access_validator = sql_access_validator
        self.query_executor = query_executor
        self.sql_ast_parser = sql_ast_parser or SqlAstParser()
        self.sql_safety_validator = sql_safety_validator or SqlSafetyValidator()
        self.execution_policy = execution_policy or QueryExecutionPolicy()
        self.query_audit_sink = query_audit_sink
        self.default_dialect = default_dialect

    async def execute_query_pipeline(
        self,
        query_request: QueryRequest,
        user_identity: UserIdentity,
        run_id: str | None = None,
        solver_request_factory: Callable[[GroundingContext, str], SolverRequest] | None = None,
    ) -> RuntimeExecutionResult:
        """Execute the end-to-end query lifecycle with fail-closed safety gates."""
        pipeline_started_at = perf_counter()
        active_run_id = run_id or str(uuid4())
        state_history: list[StateTransitionRecord] = []
        current_state = RuntimeState.RECEIVED

        def transition_to(target_state: RuntimeState) -> None:
            nonlocal current_state
            elapsed_ms = round((perf_counter() - pipeline_started_at) * 1000, 3)
            state_history.append(
                StateTransitionRecord(
                    from_state=current_state,
                    to_state=target_state,
                    elapsed_ms=elapsed_ms,
                )
            )
            current_state = target_state

        target_dialect: SupportedSqlDialect = (
            query_request.database_dialect or self.default_dialect
        )

        def default_solver_request_factory(
            grounding_context: GroundingContext,
            run_identifier: str,
        ) -> SolverRequest:
            return SolverRequest(
                run_id=run_identifier,
                query_request=query_request,
                target_dialect=target_dialect,
                grounding_context=grounding_context,
            )

        active_factory = solver_request_factory or default_solver_request_factory

        # --- Stage 1: P5 Adaptive Orchestration ---
        orchestration_result = await self.adaptive_orchestrator.run(
            query_request=query_request,
            user_identity=user_identity,
            solver_request_factory=active_factory,
            run_id=active_run_id,
        )

        if orchestration_result.outcome == OrchestrationOutcome.UNRESOLVED:
            transition_to(RuntimeState.UNRESOLVED)
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.UNRESOLVED,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                error_message="Query could not be resolved by orchestration.",
            )

        if (
            orchestration_result.outcome == OrchestrationOutcome.FAILED
            or orchestration_result.sql_candidate is None
        ):
            transition_to(RuntimeState.GENERATION_FAILED)
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.GENERATION_FAILED,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                error_message="SQL generation failed during orchestration.",
            )

        transition_to(RuntimeState.GROUNDED_GENERATED)
        sql_candidate = orchestration_result.sql_candidate

        # --- Stage 2: SQL AST Parsing and Safety Validation ---
        try:
            parsed_sql = self.sql_ast_parser.parse_single_statement(
                sql=sql_candidate.sql,
                dialect=sql_candidate.dialect,
            )
            self.sql_safety_validator.validate_read_only_sql(parsed_sql)
        except UnsafeSqlError as exc:
            transition_to(RuntimeState.SAFETY_REJECTED)
            self._record_audit_event(
                user_identity=user_identity,
                sql_candidate=sql_candidate,
                action="execute",
                outcome="blocked",
                reason=str(exc),
                run_id=active_run_id,
            )
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.SAFETY_REJECTED,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                sql_candidate=sql_candidate,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                error_message=str(exc),
            )

        transition_to(RuntimeState.VERIFIED)
        ast_referenced_tables = sorted(parsed_sql.referenced_table_identifiers())

        # --- Stage 3: Independent Authorization Check (AST evidence) ---
        try:
            self.sql_access_validator.validate_table_access(user_identity, parsed_sql)
        except UnauthorizedDataAccessError as exc:
            transition_to(RuntimeState.ACCESS_DENIED)
            self._record_audit_event(
                user_identity=user_identity,
                sql_candidate=sql_candidate,
                action="execute",
                outcome="blocked",
                reason=str(exc),
                run_id=active_run_id,
            )
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.ACCESS_DENIED,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                sql_candidate=sql_candidate,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                ast_referenced_tables=ast_referenced_tables,
                safety_check_passed=True,
                error_message=str(exc),
            )

        transition_to(RuntimeState.AUTHORIZED)

        # --- Stage 4: Read-Only Database Execution ---
        try:
            execution_result = self.query_executor.execute_read_only_query(
                sql=sql_candidate.sql,
                execution_policy=self.execution_policy,
            )
        except QueryExecutionTimeoutError as exc:
            transition_to(RuntimeState.TIMEOUT)
            self._record_audit_event(
                user_identity=user_identity,
                sql_candidate=sql_candidate,
                action="execute",
                outcome="failed",
                reason=str(exc),
                run_id=active_run_id,
            )
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.TIMEOUT,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                sql_candidate=sql_candidate,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                ast_referenced_tables=ast_referenced_tables,
                safety_check_passed=True,
                access_check_passed=True,
                error_message=str(exc),
            )
        except QueryExecutionError as exc:
            transition_to(RuntimeState.EXECUTION_FAILED)
            self._record_audit_event(
                user_identity=user_identity,
                sql_candidate=sql_candidate,
                action="execute",
                outcome="failed",
                reason=str(exc),
                run_id=active_run_id,
            )
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.EXECUTION_FAILED,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                sql_candidate=sql_candidate,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                ast_referenced_tables=ast_referenced_tables,
                safety_check_passed=True,
                access_check_passed=True,
                error_message=str(exc),
            )
        except Exception as exc:
            transition_to(RuntimeState.EXECUTION_FAILED)
            self._record_audit_event(
                user_identity=user_identity,
                sql_candidate=sql_candidate,
                action="execute",
                outcome="failed",
                reason=str(exc),
                run_id=active_run_id,
            )
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.EXECUTION_FAILED,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                sql_candidate=sql_candidate,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                ast_referenced_tables=ast_referenced_tables,
                safety_check_passed=True,
                access_check_passed=True,
                error_message=str(exc),
            )

        transition_to(RuntimeState.EXECUTED)
        transition_to(RuntimeState.COMPLETED)
        self._record_audit_event(
            user_identity=user_identity,
            sql_candidate=sql_candidate,
            action="execute",
            outcome="succeeded",
            run_id=active_run_id,
        )

        return self._build_result(
            run_id=active_run_id,
            status=RuntimeStatus.COMPLETED,
            current_state=current_state,
            state_history=state_history,
            pipeline_started_at=pipeline_started_at,
            sql_candidate=sql_candidate,
            orchestration_outcome=orchestration_result.outcome,
            orchestration_trace=orchestration_result.trace,
            ast_referenced_tables=ast_referenced_tables,
            safety_check_passed=True,
            access_check_passed=True,
            execution_passed=True,
            columns=execution_result.columns,
            rows=execution_result.rows,
            row_count=execution_result.row_count,
            has_more_rows=execution_result.has_more_rows,
            execution_time_ms=execution_result.elapsed_ms,
            warnings=execution_result.warnings,
        )

    def _build_result(
        self,
        run_id: str,
        status: RuntimeStatus,
        current_state: RuntimeState,
        state_history: list[StateTransitionRecord],
        pipeline_started_at: float,
        sql_candidate: SqlCandidate | None = None,
        orchestration_outcome: OrchestrationOutcome | None = None,
        orchestration_trace: object = None,
        ast_referenced_tables: list[str] | None = None,
        safety_check_passed: bool = False,
        access_check_passed: bool = False,
        execution_passed: bool = False,
        columns: list[str] | None = None,
        rows: list[dict[str, object]] | None = None,
        row_count: int = 0,
        has_more_rows: bool = False,
        execution_time_ms: int | None = None,
        error_message: str | None = None,
        warnings: list[str] | None = None,
    ) -> RuntimeExecutionResult:
        total_latency_ms = round((perf_counter() - pipeline_started_at) * 1000, 3)
        return RuntimeExecutionResult(
            run_id=run_id,
            status=status,
            sql=sql_candidate.sql if sql_candidate else None,
            dialect=sql_candidate.dialect if sql_candidate else None,
            columns=columns or [],
            rows=rows or [],
            row_count=row_count,
            has_more_rows=has_more_rows,
            execution_time_ms=execution_time_ms,
            total_latency_ms=total_latency_ms,
            orchestration_outcome=orchestration_outcome,
            error_message=error_message,
            warnings=warnings or [],
            trace=RuntimeTrace(
                run_id=run_id,
                state_history=state_history,
                final_state=current_state,
                orchestration_trace=orchestration_trace,  # type: ignore[arg-type]
                ast_referenced_tables=ast_referenced_tables or [],
                safety_check_passed=safety_check_passed,
                access_check_passed=access_check_passed,
                execution_passed=execution_passed,
            ),
        )

    def _record_audit_event(
        self,
        user_identity: UserIdentity,
        sql_candidate: SqlCandidate,
        action: Literal["explain", "execute"],
        outcome: Literal["blocked", "failed", "succeeded"],
        reason: str | None = None,
        run_id: str | None = None,
    ) -> None:
        if self.query_audit_sink is None:
            return
        correlation_context = read_correlation_context()
        self.query_audit_sink.record_query_audit_event(
            QueryAuditEvent(
                action=action,
                outcome=outcome,
                user_id=user_identity.user_id,
                run_id=run_id
                or correlation_context.get("run_id")
                or sql_candidate.generation_trace.run_id,
                request_id=correlation_context.get("request_id"),
                trace_id=correlation_context.get("trace_id"),
                dialect=sql_candidate.dialect,
                sql=sql_candidate.sql,
                reason=reason,
            )
        )
