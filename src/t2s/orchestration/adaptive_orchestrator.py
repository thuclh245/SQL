"""Adaptive orchestrator composing schema grounding and SQL solver with bounded escalation.

The orchestrator runs the baseline grounding → solver path, then assesses uncertainty.
If the escalation policy detects recoverable uncertainty and budget remains,
it performs one bounded corrective action (expanded regrounding + regeneration).

The baseline path is never modified. Grounding and solver remain independently callable.
"""

from collections.abc import Callable
from typing import Literal

from t2s.contracts import GroundingContext, QueryRequest, SqlCandidate
from t2s.errors import SolverError
from t2s.grounding import GroundingBudget, GroundingContextBuilder
from t2s.orchestration.escalation_budget import EscalationBudget
from t2s.orchestration.escalation_contracts import (
    EscalationAction,
    EscalationRecord,
    OrchestrationOutcome,
    OrchestrationResult,
    OrchestrationTrace,
    ValueGroundingTrace,
)
from t2s.orchestration.escalation_policy import EscalationPolicy
from t2s.security import UserIdentity
from t2s.semantics.semantic_plan import SemanticPlan
from t2s.semantics.semantic_planner import SemanticPlannerPort
from t2s.solver import DirectSqlSolver, SolverRequest


class AdaptiveOrchestrator:
    """Bounded adaptive orchestrator composing grounding and solver.

    Composes GroundingContextBuilder and DirectSqlSolver without absorbing them.
    Escalation is evidence-driven, bounded, and deterministic in control flow.
    """

    def __init__(
        self,
        grounding_context_builder: GroundingContextBuilder,
        solver: DirectSqlSolver,
        escalation_policy: EscalationPolicy,
        escalation_budget: EscalationBudget | None = None,
        semantic_planner: SemanticPlannerPort | None = None,
    ) -> None:
        self.grounding_context_builder = grounding_context_builder
        self.solver = solver
        self.escalation_policy = escalation_policy
        self.escalation_budget = escalation_budget or EscalationBudget()
        self.semantic_planner = semantic_planner

    async def run(
        self,
        query_request: QueryRequest,
        user_identity: UserIdentity,
        solver_request_factory: Callable[[GroundingContext, str], SolverRequest],
        run_id: str = "orchestration-run",
    ) -> OrchestrationResult:
        """Execute the adaptive orchestration pipeline.

        Args:
            query_request: The user's natural language query.
            user_identity: The authenticated user identity (never modified).
            solver_request_factory: Factory to build SolverRequest from context.
                Accepts (grounding_context, run_id) and returns SolverRequest.
            run_id: Correlation identifier for this orchestration run.

        Returns:
            OrchestrationResult with outcome, candidate, context, and trace.
        """
        escalation_records: list[EscalationRecord] = []
        total_grounding_calls = 0
        total_solver_calls = 0

        # --- Baseline: Ground ---
        baseline_context = self.grounding_context_builder.build_grounding_context(
            query_request=query_request,
            user_identity=user_identity,
        )
        total_grounding_calls += 1

        baseline_table_fqns = [table.fqn for table in baseline_context.tables]
        baseline_unresolved_codes = [issue.code for issue in baseline_context.unresolved]

        # --- Baseline: Plan ---
        semantic_plan: SemanticPlan | None = None
        if self.semantic_planner is not None:
            try:
                semantic_plan = await self.semantic_planner.plan(
                    query_request=query_request,
                    grounding_context=baseline_context,
                )
            except Exception:
                semantic_plan = None

        # --- Baseline: Generate ---
        baseline_candidate = await self._try_generate(
            solver_request_factory, baseline_context, run_id, semantic_plan
        )
        if baseline_candidate is not None:
            total_solver_calls += 1

        baseline_solver_unresolved = (
            list(baseline_candidate.unresolved) if baseline_candidate is not None else []
        )

        # --- Assess uncertainty ---
        budget_remaining = self.escalation_budget.max_escalations
        decision = self.escalation_policy.assess_and_decide(
            grounding_context=baseline_context,
            sql_candidate=baseline_candidate,
            budget_remaining=budget_remaining,
        )

        # --- No escalation needed: baseline is sufficient ---
        if not decision.should_escalate:
            if baseline_candidate is not None:
                outcome = OrchestrationOutcome.BASELINE_SUCCESS
            elif bool(baseline_context.tables):
                outcome = OrchestrationOutcome.FAILED
            else:
                outcome = OrchestrationOutcome.UNRESOLVED
            return OrchestrationResult(
                outcome=outcome,
                sql_candidate=baseline_candidate,
                grounding_context=baseline_context,
                semantic_plan=semantic_plan,
                trace=OrchestrationTrace(
                    run_id=run_id,
                    outcome=outcome,
                    total_grounding_calls=total_grounding_calls,
                    total_solver_calls=total_solver_calls,
                    escalation_records=escalation_records,
                    baseline_table_fqns=baseline_table_fqns,
                    baseline_unresolved_codes=baseline_unresolved_codes,
                    baseline_solver_unresolved=baseline_solver_unresolved,
                    final_table_fqns=baseline_table_fqns,
                    value_grounding=self._build_value_grounding_trace(
                        baseline_context, baseline_candidate
                    ),
                ),
            )

        # --- Escalation: perform one bounded corrective action ---
        assert decision.reason is not None  # should_escalate=True implies reason  # noqa: S101

        if decision.action == EscalationAction.STOP_UNRESOLVED:
            escalation_records.append(
                EscalationRecord(
                    attempt=1,
                    reason=decision.reason,
                    action=decision.action,
                    evidence=decision.evidence,
                    outcome="context_unchanged",
                )
            )
            stop_outcome = self._resolve_stop_outcome(baseline_context, baseline_candidate)
            return OrchestrationResult(
                outcome=stop_outcome,
                sql_candidate=baseline_candidate,
                grounding_context=baseline_context,
                semantic_plan=semantic_plan,
                trace=OrchestrationTrace(
                    run_id=run_id,
                    outcome=stop_outcome,
                    total_grounding_calls=total_grounding_calls,
                    total_solver_calls=total_solver_calls,
                    escalation_records=escalation_records,
                    baseline_table_fqns=baseline_table_fqns,
                    baseline_unresolved_codes=baseline_unresolved_codes,
                    baseline_solver_unresolved=baseline_solver_unresolved,
                    final_table_fqns=baseline_table_fqns,
                    value_grounding=self._build_value_grounding_trace(
                        baseline_context, baseline_candidate
                    ),
                ),
            )

        # --- Reground with expanded budget ---
        expanded_budget = self._build_expanded_budget()
        escalated_context = self.grounding_context_builder.build_grounding_context(
            query_request=query_request,
            user_identity=user_identity,
        )
        # Apply expanded budget by rebuilding with explicit budget override.
        escalated_context = self._reground_with_budget(
            query_request=query_request,
            user_identity=user_identity,
            budget=expanded_budget,
        )
        total_grounding_calls += 1

        # --- Same-context guard ---
        is_context_changed = self._has_context_changed(baseline_context, escalated_context)

        if not is_context_changed:
            escalation_records.append(
                EscalationRecord(
                    attempt=1,
                    reason=decision.reason,
                    action=decision.action,
                    evidence=decision.evidence,
                    outcome="context_unchanged",
                )
            )
            stop_outcome = self._resolve_stop_outcome(baseline_context, baseline_candidate)
            return OrchestrationResult(
                outcome=stop_outcome,
                sql_candidate=baseline_candidate,
                grounding_context=baseline_context,
                semantic_plan=semantic_plan,
                trace=OrchestrationTrace(
                    run_id=run_id,
                    outcome=stop_outcome,
                    total_grounding_calls=total_grounding_calls,
                    total_solver_calls=total_solver_calls,
                    escalation_records=escalation_records,
                    baseline_table_fqns=baseline_table_fqns,
                    baseline_unresolved_codes=baseline_unresolved_codes,
                    baseline_solver_unresolved=baseline_solver_unresolved,
                    final_table_fqns=[table.fqn for table in escalated_context.tables],
                    value_grounding=self._build_value_grounding_trace(
                        baseline_context, baseline_candidate
                    ),
                ),
            )

        # --- Regenerate with new context ---
        escalated_candidate = await self._try_generate(
            solver_request_factory, escalated_context, run_id, semantic_plan
        )
        if escalated_candidate is not None:
            total_solver_calls += 1

        escalation_outcome: Literal[
            "context_changed",
            "context_unchanged",
            "solver_succeeded",
            "solver_failed",
        ] = "solver_succeeded" if escalated_candidate is not None else "solver_failed"
        escalation_records.append(
            EscalationRecord(
                attempt=1,
                reason=decision.reason,
                action=decision.action,
                evidence=decision.evidence,
                outcome=escalation_outcome,
            )
        )

        final_outcome = (
            OrchestrationOutcome.ESCALATED_SUCCESS
            if escalated_candidate is not None
            else (
                OrchestrationOutcome.RESOLVED_WITH_CAVEATS
                if baseline_candidate is not None and baseline_candidate.sql and baseline_candidate.sql.strip()
                else OrchestrationOutcome.FAILED
            )
        )
        final_candidate = escalated_candidate or baseline_candidate

        return OrchestrationResult(
            outcome=final_outcome,
            sql_candidate=final_candidate,
            grounding_context=escalated_context,
            semantic_plan=semantic_plan,
            trace=OrchestrationTrace(
                run_id=run_id,
                outcome=final_outcome,
                total_grounding_calls=total_grounding_calls,
                total_solver_calls=total_solver_calls,
                escalation_records=escalation_records,
                baseline_table_fqns=baseline_table_fqns,
                baseline_unresolved_codes=baseline_unresolved_codes,
                baseline_solver_unresolved=baseline_solver_unresolved,
                final_table_fqns=[table.fqn for table in escalated_context.tables],
                value_grounding=self._build_value_grounding_trace(
                    escalated_context, final_candidate
                ),
            ),
        )

    def _build_value_grounding_trace(
        self,
        grounding_context: GroundingContext,
        sql_candidate: SqlCandidate | None,
    ) -> ValueGroundingTrace:
        """Summarise value grounding for the trace without copying literals."""
        value_bindings = grounding_context.value_bindings
        signals = grounding_context.retrieval_signals
        uses_value_evidence = False
        if sql_candidate is not None and value_bindings:
            candidate_sql = sql_candidate.sql
            uses_value_evidence = any(binding.value in candidate_sql for binding in value_bindings)
        return ValueGroundingTrace(
            binding_count=len(value_bindings),
            probe_count=int(signals.get("value_probe_count", 0.0)),
            latency_ms=signals.get("value_grounding_latency_ms", 0.0),
            bound_column_fqns=sorted({binding.column_fqn for binding in value_bindings}),
            candidate_uses_value_evidence=uses_value_evidence,
        )

    def _resolve_stop_outcome(
        self,
        grounding_context: GroundingContext,
        sql_candidate: SqlCandidate | None,
    ) -> OrchestrationOutcome:
        """Pick the outcome when escalation cannot make further progress.

        A structurally sound candidate is released with caveats instead of being
        thrown away; only a missing or ungrounded one stays UNRESOLVED.
        """
        viability = self.escalation_policy.assess_candidate_viability(
            grounding_context, sql_candidate
        )
        if sql_candidate is not None and viability.is_candidate_viable:
            return OrchestrationOutcome.RESOLVED_WITH_CAVEATS
        return OrchestrationOutcome.UNRESOLVED

    async def _try_generate(
        self,
        solver_request_factory: Callable[[GroundingContext, str], SolverRequest],
        grounding_context: GroundingContext,
        run_id: str,
        semantic_plan: SemanticPlan | None = None,
    ) -> SqlCandidate | None:
        """Attempt SQL generation, returning None on solver errors."""
        if not grounding_context.tables:
            return None
        try:
            solver_request = solver_request_factory(grounding_context, run_id)
            if semantic_plan is not None and solver_request.semantic_plan is None:
                solver_request = solver_request.model_copy(update={"semantic_plan": semantic_plan})
            return await self.solver.generate_sql_candidate(solver_request)
        except SolverError:
            return None

    def _build_expanded_budget(self) -> GroundingBudget:
        """Build an expanded grounding budget by adding configured deltas."""
        baseline = self.grounding_context_builder.grounding_budget
        return GroundingBudget(
            max_candidate_tables=baseline.max_candidate_tables,
            max_hydrated_tables=baseline.max_hydrated_tables
            + self.escalation_budget.grounding_table_delta,
            max_columns_per_table=baseline.max_columns_per_table,
            max_total_columns=baseline.max_total_columns
            + self.escalation_budget.grounding_column_delta,
            max_relationships=baseline.max_relationships
            + self.escalation_budget.grounding_relationship_delta,
        )

    def _reground_with_budget(
        self,
        query_request: QueryRequest,
        user_identity: UserIdentity,
        budget: GroundingBudget,
    ) -> GroundingContext:
        """Reground with an alternate budget without modifying the builder's default."""
        original_budget = self.grounding_context_builder.grounding_budget
        try:
            self.grounding_context_builder.grounding_budget = budget
            return self.grounding_context_builder.build_grounding_context(
                query_request=query_request,
                user_identity=user_identity,
            )
        finally:
            self.grounding_context_builder.grounding_budget = original_budget

    def _has_context_changed(
        self,
        baseline: GroundingContext,
        escalated: GroundingContext,
    ) -> bool:
        """Check if escalated grounding produced materially different context."""
        baseline_table_fqns = frozenset(table.fqn for table in baseline.tables)
        escalated_table_fqns = frozenset(table.fqn for table in escalated.tables)

        if baseline_table_fqns != escalated_table_fqns:
            return True

        baseline_column_count = sum(len(table.columns) for table in baseline.tables)
        escalated_column_count = sum(len(table.columns) for table in escalated.tables)

        if escalated_column_count > baseline_column_count:
            return True

        baseline_relationship_count = sum(len(table.relationships) for table in baseline.tables)
        escalated_relationship_count = sum(len(table.relationships) for table in escalated.tables)

        if escalated_relationship_count > baseline_relationship_count:
            return True

        return False
