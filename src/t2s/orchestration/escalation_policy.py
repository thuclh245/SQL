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
from t2s.orchestration.unresolved_classification import (
    CandidateViabilityAssessment,
    UnresolvedClassifier,
)


class EscalationPolicy:
    """Deterministic policy that assesses uncertainty and recommends action.

    Every escalation decision is based on explicit, structured signals
    from GroundingContext and SqlCandidate outputs. No free-form reasoning.
    """

    def __init__(
        self,
        unresolved_classifier: UnresolvedClassifier | None = None,
        release_candidates_with_caveats: bool = True,
    ) -> None:
        """Configure the policy.

        ``release_candidates_with_caveats`` selects the abstention posture. The
        default lets a structurally sound candidate proceed carrying its caveats.
        Setting it False restores strict abstention, where any uncertainty the
        solver reports blocks the query — appropriate where an unreviewed answer
        is costlier than no answer, and the setting used to reproduce runs made
        before the structural policy existed.
        """
        self.unresolved_classifier = unresolved_classifier or UnresolvedClassifier()
        self.release_candidates_with_caveats = release_candidates_with_caveats

    def assess_candidate_viability(
        self,
        grounding_context: GroundingContext,
        sql_candidate: SqlCandidate | None,
    ) -> CandidateViabilityAssessment:
        """Expose the structural verdict so callers can act on it without re-deriving it."""
        assessment = self.unresolved_classifier.assess_candidate(grounding_context, sql_candidate)
        if assessment.has_solver_unresolved_notes and not self.release_candidates_with_caveats:
            return assessment.model_copy(update={"is_candidate_viable": False})
        return assessment

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

        # Solver-reported uncertainty escalates only when structural evidence shows
        # the candidate cannot stand. Free-text caveats attached to an otherwise
        # sound statement are advisory and must not cost the query.
        viability = self.unresolved_classifier.assess_candidate(grounding_context, sql_candidate)
        if not viability.is_candidate_viable or (
            viability.has_solver_unresolved_notes and not self.release_candidates_with_caveats
        ):
            return EscalationDecision(
                should_escalate=True,
                reason=(
                    EscalationReason.SCHEMA_REFERENCE_MISMATCH
                    if any(
                        item.startswith("referenced_but_not_grounded")
                        for item in viability.evidence
                    )
                    else EscalationReason.SOLVER_UNRESOLVED
                ),
                action=EscalationAction.REGROUND_WITH_EXPANDED_BUDGET,
                evidence=viability.evidence,
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
