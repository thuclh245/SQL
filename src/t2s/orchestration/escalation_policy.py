"""Deterministic escalation policy for adaptive orchestration.

The policy examines structured evidence from grounding and solver outputs
to decide whether escalation is warranted. It never consults an LLM.
"""

from t2s.contracts import GroundingContext, SqlCandidate
from t2s.orchestration.escalation_contracts import (
    EscalationAction,
    EscalationDecision,
    EscalationReason,
)


class EscalationPolicy:
    """Deterministic policy that assesses uncertainty and recommends action.

    Every escalation decision is based on explicit, structured signals
    from GroundingContext and SqlCandidate outputs. No free-form reasoning.
    """

    def assess_and_decide(
        self,
        grounding_context: GroundingContext,
        sql_candidate: SqlCandidate | None,
        budget_remaining: int,
    ) -> EscalationDecision:
        """Assess uncertainty evidence and decide whether to escalate.

        Args:
            grounding_context: The grounding output to assess.
            sql_candidate: The solver output to assess (None if solver failed).
            budget_remaining: Number of escalation attempts still available.

        Returns:
            A structured EscalationDecision.
        """
        if budget_remaining <= 0:
            return EscalationDecision(
                should_escalate=False,
                action=EscalationAction.STOP_UNRESOLVED,
            )

        # Check for unresolved SQL identifiers — not recoverable by regrounding.
        unresolved_identifier_issues = [
            issue
            for issue in grounding_context.unresolved
            if issue.code == "unresolved_sql_identifier"
        ]
        if unresolved_identifier_issues:
            return EscalationDecision(
                should_escalate=False,
                reason=EscalationReason.UNRESOLVED_IDENTIFIER,
                action=EscalationAction.STOP_UNRESOLVED,
                evidence=[
                    f"unresolved_sql_identifier: {issue.message}"
                    for issue in unresolved_identifier_issues
                ],
            )

        # Check for other grounding issues — potentially recoverable.
        recoverable_grounding_issues = [
            issue
            for issue in grounding_context.unresolved
            if issue.code != "unresolved_sql_identifier"
        ]
        if recoverable_grounding_issues:
            return EscalationDecision(
                should_escalate=True,
                reason=EscalationReason.GROUNDING_INCOMPLETE,
                action=EscalationAction.REGROUND_WITH_EXPANDED_BUDGET,
                evidence=[
                    f"{issue.code}: {issue.message}" for issue in recoverable_grounding_issues
                ],
            )

        # If solver failed completely, no structured evidence to assess.
        if sql_candidate is None:
            return EscalationDecision(
                should_escalate=False,
                action=EscalationAction.STOP_UNRESOLVED,
                evidence=["solver_produced_no_candidate"],
            )

        # Check for solver-reported unresolved items.
        if sql_candidate.unresolved:
            return EscalationDecision(
                should_escalate=True,
                reason=EscalationReason.SOLVER_UNRESOLVED,
                action=EscalationAction.REGROUND_WITH_EXPANDED_BUDGET,
                evidence=[
                    f"solver_unresolved: {item}" for item in sql_candidate.unresolved
                ],
            )

        # Check for schema reference mismatch: solver references tables
        # not present in the grounding context.
        grounded_sql_identifiers = {
            table.sql_identifier for table in grounding_context.tables
        }
        mismatched_references = [
            ref
            for ref in sql_candidate.referenced_tables
            if ref not in grounded_sql_identifiers
        ]
        if mismatched_references:
            return EscalationDecision(
                should_escalate=True,
                reason=EscalationReason.SCHEMA_REFERENCE_MISMATCH,
                action=EscalationAction.REGROUND_WITH_EXPANDED_BUDGET,
                evidence=[
                    f"referenced_but_not_grounded: {ref}" for ref in mismatched_references
                ],
            )

        # Check for relationship ambiguity: multiple tables but zero
        # relationship evidence despite grounding producing them.
        if len(grounding_context.tables) >= 2:
            has_any_relationship = any(
                len(table.relationships) > 0 for table in grounding_context.tables
            )
            if not has_any_relationship:
                return EscalationDecision(
                    should_escalate=True,
                    reason=EscalationReason.RELATIONSHIP_AMBIGUITY,
                    action=EscalationAction.REGROUND_WITH_EXPANDED_BUDGET,
                    evidence=[
                        f"tables_without_relationships: "
                        f"{[table.fqn for table in grounding_context.tables]}"
                    ],
                )

        # No recoverable uncertainty detected.
        return EscalationDecision(
            should_escalate=False,
            action=EscalationAction.STOP_UNRESOLVED,
        )
