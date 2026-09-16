"""Decides whether a solver's self-reported uncertainty actually blocks execution.

The solver returns ``unresolved`` as free text. Reading that text to decide
whether to abstain would mean encoding phrase rules, which overfit to whichever
failures were observed while writing them and silently change meaning across
languages and model versions. This module therefore ignores the wording entirely
and decides from structural facts that can be checked against the grounding
context:

* grounding could not resolve an executable identifier;
* the candidate references a relation that was never grounded;
* there is no candidate at all.

Anything else is treated as advisory. The reasoning is that a model which
emitted a parseable statement over grounded relations demonstrably *was* able to
formulate a query, so its prose caveat is a note about that query rather than a
reason to discard it. Safety, authorization and execution gates still run
afterwards and remain fail-closed.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from t2s.contracts import GroundingContext, SqlCandidate

UNRESOLVED_SQL_IDENTIFIER_CODE = "unresolved_sql_identifier"


class UnresolvedClassification(StrEnum):
    """Structural verdicts on a solver's uncertainty.

    Only classifications derivable from structured evidence are defined. Reason
    families such as semantic ambiguity or unsupported operations are real, but
    separating them from an ordinary caveat needs the solver to label its own
    blockers in structured output; until that contract exists they are reported
    as ``NON_BLOCKING_CAVEAT`` and caught downstream rather than guessed at here.
    """

    NON_BLOCKING_CAVEAT = "non_blocking_caveat"
    GROUNDING_INSUFFICIENT = "grounding_insufficient"
    STRUCTURAL_UNCERTAINTY = "structural_uncertainty"


class CandidateViabilityAssessment(BaseModel):
    """Whether a candidate may proceed, and the structural evidence behind that."""

    classification: UnresolvedClassification
    is_candidate_viable: bool
    has_solver_unresolved_notes: bool = False
    evidence: list[str] = Field(default_factory=list)


class UnresolvedClassifier:
    """Classifies solver uncertainty from structured evidence alone."""

    def assess_candidate(
        self,
        grounding_context: GroundingContext,
        sql_candidate: SqlCandidate | None,
    ) -> CandidateViabilityAssessment:
        """Return a structural verdict on whether the candidate can proceed."""
        if sql_candidate is None:
            return CandidateViabilityAssessment(
                classification=UnresolvedClassification.STRUCTURAL_UNCERTAINTY,
                is_candidate_viable=False,
                evidence=["solver_produced_no_candidate"],
            )

        has_notes = bool(sql_candidate.unresolved)

        identifier_issues = [
            issue
            for issue in grounding_context.unresolved
            if issue.code == UNRESOLVED_SQL_IDENTIFIER_CODE
        ]
        if identifier_issues:
            return CandidateViabilityAssessment(
                classification=UnresolvedClassification.GROUNDING_INSUFFICIENT,
                is_candidate_viable=False,
                has_solver_unresolved_notes=has_notes,
                evidence=[
                    f"{UNRESOLVED_SQL_IDENTIFIER_CODE}: {issue.message}"
                    for issue in identifier_issues
                ],
            )

        ungrounded_references = self._find_ungrounded_table_references(
            grounding_context, sql_candidate
        )
        if ungrounded_references:
            return CandidateViabilityAssessment(
                classification=UnresolvedClassification.GROUNDING_INSUFFICIENT,
                is_candidate_viable=False,
                has_solver_unresolved_notes=has_notes,
                evidence=[
                    f"referenced_but_not_grounded: {reference}"
                    for reference in ungrounded_references
                ],
            )

        return CandidateViabilityAssessment(
            classification=UnresolvedClassification.NON_BLOCKING_CAVEAT,
            is_candidate_viable=True,
            has_solver_unresolved_notes=has_notes,
            evidence=[f"solver_unresolved_note_count: {len(sql_candidate.unresolved)}"]
            if has_notes
            else [],
        )

    def _find_ungrounded_table_references(
        self,
        grounding_context: GroundingContext,
        sql_candidate: SqlCandidate,
    ) -> list[str]:
        """List relations the candidate names that grounding never supplied.

        Only table-level references are checked. Column-level comparison is
        deliberately omitted: aliases, computed projections and quoting styles make
        it unreliable, and a wrong verdict there would abstain on a correct query.
        The access validator still re-derives relations from the parsed AST, so a
        genuinely unauthorized reference cannot slip through this leniency.
        """
        grounded_identifiers = {table.sql_identifier for table in grounding_context.tables}
        grounded_identifiers.update(table.fqn for table in grounding_context.tables)
        return [
            reference
            for reference in sql_candidate.referenced_tables
            if reference not in grounded_identifiers
        ]
