"""Escalation contracts for the adaptive orchestration layer."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from t2s.contracts import GroundingContext, SqlCandidate


class EscalationReason(StrEnum):
    """Explicit taxonomy of escalation triggers.

    Each reason corresponds to a specific, detectable signal in grounding
    or solver output. No free-form reasoning.
    """

    GROUNDING_INCOMPLETE = "grounding_incomplete"
    RELATIONSHIP_AMBIGUITY = "relationship_ambiguity"
    UNRESOLVED_IDENTIFIER = "unresolved_identifier"
    SOLVER_UNRESOLVED = "solver_unresolved"
    SCHEMA_REFERENCE_MISMATCH = "schema_reference_mismatch"


class EscalationAction(StrEnum):
    """Actions the orchestrator may take on escalation."""

    REGROUND_WITH_EXPANDED_BUDGET = "reground_with_expanded_budget"
    REGENERATE_WITH_RESOLVED_CONTEXT = "regenerate_with_resolved_context"
    STOP_UNRESOLVED = "stop_unresolved"


class OrchestrationOutcome(StrEnum):
    """Distinguishable outcomes of an orchestration run."""

    BASELINE_SUCCESS = "baseline_success"
    ESCALATED_SUCCESS = "escalated_success"
    # Escalation could not improve the context, but the candidate held up
    # structurally, so it proceeds to the safety and execution gates carrying its
    # caveats rather than being discarded.
    RESOLVED_WITH_CAVEATS = "resolved_with_caveats"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


class EscalationDecision(BaseModel):
    """Result of the escalation policy assessment.

    Deterministic and structured — never derived from LLM reasoning.
    """

    should_escalate: bool
    reason: EscalationReason | None = None
    action: EscalationAction
    evidence: list[str] = Field(default_factory=list)


class EscalationRecord(BaseModel):
    """Structured record of a single escalation attempt."""

    attempt: int = Field(ge=1)
    reason: EscalationReason
    action: EscalationAction
    evidence: list[str] = Field(default_factory=list)
    outcome: Literal[
        "context_changed",
        "context_unchanged",
        "solver_succeeded",
        "solver_failed",
    ]


class ValueGroundingTrace(BaseModel):
    """Observability for value grounding within one orchestration run.

    Column locations and counts are recorded; the literals themselves are not, so
    a trace never becomes a copy of column contents.
    """

    binding_count: int = Field(default=0, ge=0)
    probe_count: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    bound_column_fqns: list[str] = Field(default_factory=list)
    # Whether the generated SQL actually adopted one of the grounded literals.
    candidate_uses_value_evidence: bool = False


class OrchestrationTrace(BaseModel):
    """Complete trace of an orchestration run for observability."""

    run_id: str
    outcome: OrchestrationOutcome
    total_grounding_calls: int = Field(ge=1)
    total_solver_calls: int = Field(ge=0)
    escalation_records: list[EscalationRecord] = Field(default_factory=list)
    baseline_table_fqns: list[str] = Field(default_factory=list)
    baseline_unresolved_codes: list[str] = Field(default_factory=list)
    baseline_solver_unresolved: list[str] = Field(default_factory=list)
    final_table_fqns: list[str] = Field(default_factory=list)
    value_grounding: ValueGroundingTrace = Field(default_factory=lambda: ValueGroundingTrace())


class OrchestrationResult(BaseModel):
    """Final result of the adaptive orchestration pipeline."""

    outcome: OrchestrationOutcome
    sql_candidate: SqlCandidate | None = None
    grounding_context: GroundingContext
    semantic_plan: Any | None = None
    trace: OrchestrationTrace
