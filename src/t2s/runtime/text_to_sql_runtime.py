"""Production-oriented safe Text-to-SQL application runtime."""

import asyncio
from collections.abc import Callable
from time import perf_counter
from typing import Any, Literal
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
    ValidatorMode,
    ValidatorRuntimeAction,
    ValidatorRuntimeOutcome,
    VerifierMode,
    VerifierRuntimeOutcome,
)
from t2s.runtime.sql_risk_controller import SqlRiskController
from t2s.security import UserIdentity
from t2s.semantics import SemanticPlanConsistencyChecker
from t2s.solver import DirectSqlPromptBuilder, SolverRequest
from t2s.verification import (
    DiagnosticProbeOutcome,
    DiagnosticProbeRunner,
    ResultVerificationOutcome,
    ResultVerifier,
    SqlAccessValidator,
    SqlAstParser,
    SqlSafetyValidator,
    SqlVerifier,
    VerificationDecision,
    VerificationInput,
)
from t2s.verification.sql_semantic_risk_validator import ValidationInput


class TextToSqlRuntime:
    """Orchestrates end-to-end question processing with fail-closed safety gating.

    Coordinates:
    Orchestration -> Semantic Verifier Gate (Optional)
    -> AST Safety -> Authorization -> Read-Only Execution
    -> Result-Aware Verification & Diagnostic Probing
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
        verifier: SqlVerifier | None = None,
        verifier_mode: VerifierMode = VerifierMode.OFF,
        risk_controller: SqlRiskController | None = None,
        validator_mode: ValidatorMode = ValidatorMode.SHADOW,
        plan_consistency_checker: SemanticPlanConsistencyChecker | None = None,
        result_verifier: ResultVerifier | None = None,
        diagnostic_probe_runner: DiagnosticProbeRunner | None = None,
        enable_self_correction: bool = False,
    ) -> None:
        self.adaptive_orchestrator = adaptive_orchestrator
        self.sql_access_validator = sql_access_validator
        self.query_executor = query_executor
        self.sql_ast_parser = sql_ast_parser or SqlAstParser()
        self.sql_safety_validator = sql_safety_validator or SqlSafetyValidator()
        self.execution_policy = execution_policy or QueryExecutionPolicy()
        self.query_audit_sink = query_audit_sink
        self.default_dialect = default_dialect
        self.verifier = verifier
        self.verifier_mode = verifier_mode
        self.risk_controller = risk_controller or SqlRiskController()
        self.validator_mode = validator_mode
        self.plan_consistency_checker = plan_consistency_checker
        self.result_verifier = result_verifier
        self.diagnostic_probe_runner = diagnostic_probe_runner
        self.enable_self_correction = enable_self_correction

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

        target_dialect: SupportedSqlDialect = query_request.database_dialect or self.default_dialect

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

        # --- Stage 1: Adaptive Orchestration ---
        orchestration_result = await self.adaptive_orchestrator.run(
            query_request=query_request,
            user_identity=user_identity,
            solver_request_factory=active_factory,
            run_id=active_run_id,
        )

        semantic_plan = orchestration_result.semantic_plan
        plan_consistency_warnings: list[str] = []

        # A candidate released with caveats still runs every downstream gate; the
        # caveats travel with the answer so the caller can judge it, rather than
        # being dropped along with the query.
        if orchestration_result.outcome == OrchestrationOutcome.RESOLVED_WITH_CAVEATS and (
            orchestration_result.sql_candidate is not None
        ):
            plan_consistency_warnings.extend(
                f"SOLVER_CAVEAT: {note}"
                for note in orchestration_result.sql_candidate.unresolved
            )

        if orchestration_result.outcome == OrchestrationOutcome.UNRESOLVED:
            transition_to(RuntimeState.UNRESOLVED)
            return self._build_result(
                run_id=active_run_id,
                status=RuntimeStatus.UNRESOLVED,
                current_state=current_state,
                state_history=state_history,
                pipeline_started_at=pipeline_started_at,
                sql_candidate=orchestration_result.sql_candidate,
                orchestration_outcome=orchestration_result.outcome,
                orchestration_trace=orchestration_result.trace,
                semantic_plan=semantic_plan,
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

        # --- Optional Stage: Semantic Verifier Gate (Phase 8B) ---
        verifier_outcome: VerifierRuntimeOutcome | None = None
        if self.verifier_mode == VerifierMode.GATE_ONLY and self.verifier is not None:
            v_start = perf_counter()
            final_ctx = orchestration_result.grounding_context
            auth_schema = (
                DirectSqlPromptBuilder()._format_authorized_schema(final_ctx) if final_ctx else ""
            )
            auth_tables = [t.fqn for t in final_ctx.tables] if final_ctx else []
            auth_cols = (
                {
                    t.sql_identifier: [c.name for c in t.columns]
                    for t in final_ctx.tables
                    if t.sql_identifier
                }
                if final_ctx
                else {}
            )
            v_input = VerificationInput(
                question=query_request.question,
                evidence=query_request.target_hint or "",
                dialect=sql_candidate.dialect,
                authorized_schema=auth_schema,
                candidate_sql=sql_candidate.sql,
                authorized_tables=auth_tables,
                authorized_columns=auth_cols,
            )
            try:
                v_res = await self.verifier.verify(v_input)
                v_latency = round((perf_counter() - v_start) * 1000, 3)
                verifier_outcome = VerifierRuntimeOutcome(
                    invoked=True,
                    mode=self.verifier_mode,
                    decision=v_res.decision.value,
                    projection_status=v_res.projection.status.value,
                    aggregation_status=v_res.aggregation_and_grain.status.value,
                    filter_status=v_res.filters_and_values.status.value,
                    join_status=v_res.join_semantics.status.value,
                    ordering_status=v_res.ordering_and_limit.status.value,
                    null_status=v_res.null_semantics.status.value,
                    schema_status=v_res.schema_reference.status.value,
                    latency_ms=v_latency,
                )
                if v_res.decision != VerificationDecision.ACCEPT:
                    transition_to(RuntimeState.UNRESOLVED)
                    return self._build_result(
                        run_id=active_run_id,
                        status=RuntimeStatus.UNRESOLVED,
                        current_state=current_state,
                        state_history=state_history,
                        pipeline_started_at=pipeline_started_at,
                        sql_candidate=sql_candidate,
                        orchestration_outcome=orchestration_result.outcome,
                        orchestration_trace=orchestration_result.trace,
                        error_message="Candidate SQL withheld by semantic verifier gate.",
                        verifier_outcome=verifier_outcome,
                    )
            except Exception as exc:
                v_latency = round((perf_counter() - v_start) * 1000, 3)
                verifier_outcome = VerifierRuntimeOutcome(
                    invoked=True,
                    mode=self.verifier_mode,
                    decision=VerificationDecision.ABSTAIN.value,
                    latency_ms=v_latency,
                    error_message=str(exc),
                )
                transition_to(RuntimeState.UNRESOLVED)
                return self._build_result(
                    run_id=active_run_id,
                    status=RuntimeStatus.UNRESOLVED,
                    current_state=current_state,
                    state_history=state_history,
                    pipeline_started_at=pipeline_started_at,
                    sql_candidate=sql_candidate,
                    orchestration_outcome=orchestration_result.outcome,
                    orchestration_trace=orchestration_result.trace,
                    error_message="Candidate SQL withheld due to verifier provider failure.",
                    verifier_outcome=verifier_outcome,
                )

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
                verifier_outcome=verifier_outcome,
            )

        transition_to(RuntimeState.VERIFIED)
        ast_referenced_tables = sorted(parsed_sql.referenced_table_identifiers())

        # Deterministic Semantic Plan Consistency Check
        if self.plan_consistency_checker is not None and semantic_plan is not None:
            try:
                consistency = self.plan_consistency_checker.check_alignment(
                    plan=semantic_plan,
                    sql=sql_candidate.sql,
                    dialect=sql_candidate.dialect,
                )
                if not consistency.is_consistent:
                    for mismatch in consistency.mismatches:
                        plan_consistency_warnings.append(f"PLAN_INCONSISTENCY: {mismatch}")
            except Exception as exc:
                plan_consistency_warnings.append(f"PLAN_CONSISTENCY_CHECK_FAILED: {exc}")

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
                verifier_outcome=verifier_outcome,
            )

        transition_to(RuntimeState.AUTHORIZED)

        # --- Stage 3b: Deterministic Semantic Validation (feature-flagged) ---
        validator_outcome: ValidatorRuntimeOutcome | None = None
        if self.validator_mode != ValidatorMode.DISABLED:
            final_ctx = orchestration_result.grounding_context
            auth_schema = (
                DirectSqlPromptBuilder()._format_authorized_schema(final_ctx) if final_ctx else ""
            )
            auth_tables = [t.fqn for t in final_ctx.tables] if final_ctx else []
            auth_cols = (
                {
                    t.sql_identifier: [c.name for c in t.columns]
                    for t in final_ctx.tables
                    if t.sql_identifier
                }
                if final_ctx
                else {}
            )
            validation_input = ValidationInput(
                question=query_request.question,
                candidate_sql=sql_candidate.sql,
                evidence=query_request.target_hint,
                schema_context={
                    "dialect": sql_candidate.dialect,
                    "authorized_schema": auth_schema,
                    "authorized_tables": auth_tables,
                    "authorized_columns": auth_cols,
                },
            )
            validator_outcome = self.risk_controller.evaluate(
                validation_input,
                mode=self.validator_mode,
                existing_runtime_action=ValidatorRuntimeAction.ACCEPT,
                run_id=active_run_id,
            )
            if (
                self.validator_mode == ValidatorMode.ENFORCE
                and validator_outcome.effective_runtime_action
                == ValidatorRuntimeAction.NEEDS_SEMANTIC_REVIEW
            ):
                transition_to(RuntimeState.UNRESOLVED)
                return self._build_result(
                    run_id=active_run_id,
                    status=RuntimeStatus.UNRESOLVED,
                    current_state=current_state,
                    state_history=state_history,
                    pipeline_started_at=pipeline_started_at,
                    sql_candidate=sql_candidate,
                    orchestration_outcome=orchestration_result.outcome,
                    orchestration_trace=orchestration_result.trace,
                    ast_referenced_tables=ast_referenced_tables,
                    safety_check_passed=True,
                    access_check_passed=True,
                    error_message="Candidate SQL withheld by deterministic semantic validator.",
                    verifier_outcome=verifier_outcome,
                    validator_outcome=validator_outcome,
                )

        # --- Stage 4: Read-Only Database Execution ---
        try:
            # Executors are synchronous by contract; keep their blocking socket I/O
            # off the event loop so one slow query cannot stall other requests.
            execution_result = await asyncio.to_thread(
                self.query_executor.execute_read_only_query,
                sql_candidate.sql,
                self.execution_policy,
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
                verifier_outcome=verifier_outcome,
                validator_outcome=validator_outcome,
            )
        except QueryExecutionError as exc:
            # Self-correction: attempt single-turn refinement if enabled and solver is available
            corrected_candidate: SqlCandidate | None = None
            solver = getattr(self.adaptive_orchestrator, "solver", None)
            if self.enable_self_correction and solver is not None and hasattr(solver, "refine_sql_candidate"):
                try:
                    s_req = active_factory(
                        orchestration_result.grounding_context,
                        f"{active_run_id}_correction",
                    )
                    corrected_candidate = await solver.refine_sql_candidate(
                        solver_request=s_req,
                        failed_sql=sql_candidate.sql,
                        error_message=str(exc),
                    )
                    parsed_sql = self.sql_ast_parser.parse_single_statement(
                        sql=corrected_candidate.sql,
                        dialect=corrected_candidate.dialect,
                    )
                    self.sql_safety_validator.validate_read_only_sql(parsed_sql)
                    self.sql_access_validator.validate_table_access(user_identity, parsed_sql)
                    execution_result = await asyncio.to_thread(
                        self.query_executor.execute_read_only_query,
                        corrected_candidate.sql,
                        self.execution_policy,
                    )
                    sql_candidate = corrected_candidate
                    ast_referenced_tables = sorted(parsed_sql.referenced_table_identifiers())
                    plan_consistency_warnings.append(
                        f"SELF_CORRECTED: Original SQL execution failed with: {exc}"
                    )
                except Exception as corr_exc:
                    corrected_candidate = None

            if corrected_candidate is None:
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
                    verifier_outcome=verifier_outcome,
                    validator_outcome=validator_outcome,
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
                verifier_outcome=verifier_outcome,
                validator_outcome=validator_outcome,
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

        result_verification_outcome: ResultVerificationOutcome | None = None
        diagnostic_probe_outcome: DiagnosticProbeOutcome | None = None
        if self.result_verifier is not None:
            try:
                result_verification_outcome = self.result_verifier.verify_result(
                    execution_result=execution_result,
                    plan=semantic_plan,
                )
                if (
                    result_verification_outcome.is_suspicious
                    and self.diagnostic_probe_runner is not None
                ):
                    diagnostic_probe_outcome = (
                        self.diagnostic_probe_runner.probe_suspicious_result(
                            candidate_sql=sql_candidate.sql,
                            dialect=sql_candidate.dialect,
                            user_identity=user_identity,
                            recommended_probe=result_verification_outcome.recommended_probe,
                            execution_policy=self.execution_policy,
                        )
                    )
            except Exception as exc:
                plan_consistency_warnings.append(f"RESULT_VERIFICATION_ERROR: {exc}")

        # Self-correction on suspicious empty results ( V2-P00R: execution-guided empty result recovery )
        if (
            self.enable_self_correction
            and execution_result.row_count == 0
            and result_verification_outcome is not None
            and result_verification_outcome.is_suspicious
        ):
            solver = getattr(self.adaptive_orchestrator, "solver", None)
            if solver is not None and hasattr(solver, "refine_sql_candidate"):
                probe_hint = (
                    f" Diagnostic probe finding: {diagnostic_probe_outcome.findings}"
                    if diagnostic_probe_outcome is not None and diagnostic_probe_outcome.findings
                    else ""
                )
                empty_error_msg = (
                    f"Query executed successfully but returned 0 rows (empty result), which is unexpected.{probe_hint} "
                    "Your WHERE filters, JOIN conditions, or literal string casing may be overly restrictive or mismatching "
                    "actual stored values. Please inspect the schema/evidence and relax or correct the filters."
                )
                try:
                    s_req = active_factory(
                        orchestration_result.grounding_context,
                        f"{active_run_id}_empty_correction",
                    )
                    refined_candidate = await solver.refine_sql_candidate(
                        solver_request=s_req,
                        failed_sql=sql_candidate.sql,
                        error_message=empty_error_msg,
                    )
                    refined_parsed = self.sql_ast_parser.parse_single_statement(
                        sql=refined_candidate.sql,
                        dialect=refined_candidate.dialect,
                    )
                    self.sql_safety_validator.validate_read_only_sql(refined_parsed)
                    self.sql_access_validator.validate_table_access(user_identity, refined_parsed)
                    refined_execution_result = await asyncio.to_thread(
                        self.query_executor.execute_read_only_query,
                        refined_candidate.sql,
                        self.execution_policy,
                    )
                    # If refined query produces data or executes cleanly, adopt it
                    if refined_execution_result.row_count > 0 or execution_result.row_count == 0:
                        sql_candidate = refined_candidate
                        execution_result = refined_execution_result
                        ast_referenced_tables = sorted(refined_parsed.referenced_table_identifiers())
                        plan_consistency_warnings.append(
                            f"SELF_CORRECTED_EMPTY_RESULT: Refined SQL returned {execution_result.row_count} rows."
                        )
                except Exception as corr_exc:
                    plan_consistency_warnings.append(f"EMPTY_RESULT_CORRECTION_FAILED: {corr_exc}")

        combined_warnings = list(execution_result.warnings) + plan_consistency_warnings

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
            warnings=combined_warnings,
            verifier_outcome=verifier_outcome,
            validator_outcome=validator_outcome,
            semantic_plan=semantic_plan,
            result_verification_outcome=result_verification_outcome,
            diagnostic_probe_outcome=diagnostic_probe_outcome,
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
        verifier_outcome: VerifierRuntimeOutcome | None = None,
        validator_outcome: ValidatorRuntimeOutcome | None = None,
        semantic_plan: Any | None = None,
        result_verification_outcome: Any | None = None,
        diagnostic_probe_outcome: Any | None = None,
    ) -> RuntimeExecutionResult:
        total_latency_ms = round((perf_counter() - pipeline_started_at) * 1000, 3)
        return RuntimeExecutionResult(
            run_id=run_id,
            status=status,
            sql=(
                sql_candidate.sql if (sql_candidate and status == RuntimeStatus.COMPLETED) else None
            ),
            dialect=(
                sql_candidate.dialect
                if (sql_candidate and status == RuntimeStatus.COMPLETED)
                else None
            ),
            columns=columns or [],
            rows=rows or [],
            row_count=row_count,
            has_more_rows=has_more_rows,
            execution_time_ms=execution_time_ms,
            total_latency_ms=total_latency_ms,
            orchestration_outcome=orchestration_outcome,
            error_message=error_message,
            warnings=warnings or [],
            verifier_outcome=verifier_outcome,
            validator_outcome=validator_outcome,
            semantic_plan=semantic_plan,
            result_verification_outcome=result_verification_outcome,
            diagnostic_probe_outcome=diagnostic_probe_outcome,
            trace=RuntimeTrace(
                run_id=run_id,
                state_history=state_history,
                final_state=current_state,
                orchestration_trace=orchestration_trace,  # type: ignore[arg-type]
                ast_referenced_tables=ast_referenced_tables or [],
                safety_check_passed=safety_check_passed,
                access_check_passed=access_check_passed,
                execution_passed=execution_passed,
                rejected_candidate=sql_candidate if status == RuntimeStatus.UNRESOLVED else None,
                candidate_assumptions=(
                    sql_candidate.assumptions if sql_candidate is not None else []
                ),
                verifier_outcome=verifier_outcome,
                validator_outcome=validator_outcome,
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
