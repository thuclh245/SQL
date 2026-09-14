"""Contracts and lifecycle state machine definitions for P6 Safe Runtime."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from t2s.contracts import AnswerPayload, QueryDecision, QueryResponse
from t2s.orchestration.escalation_contracts import OrchestrationOutcome, OrchestrationTrace


class RuntimeState(StrEnum):
    """Explicit lifecycle states for request execution.

    Transitions through states in strict order:
    RECEIVED -> GROUNDED_GENERATED -> VERIFIED -> AUTHORIZED -> EXECUTED -> COMPLETED
    Terminal failure states:
    UNRESOLVED, GENERATION_FAILED, SAFETY_REJECTED, ACCESS_DENIED, EXECUTION_FAILED, TIMEOUT
    """

    RECEIVED = "received"
    GROUNDED_GENERATED = "grounded_generated"
    VERIFIED = "verified"
    AUTHORIZED = "authorized"
    EXECUTED = "executed"
    COMPLETED = "completed"

    # Terminal failure states
    UNRESOLVED = "unresolved"
    GENERATION_FAILED = "generation_failed"
    SAFETY_REJECTED = "safety_rejected"
    ACCESS_DENIED = "access_denied"
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"


class RuntimeStatus(StrEnum):
    """Terminal outcome status for a runtime query execution."""

    COMPLETED = "completed"
    UNRESOLVED = "unresolved"
    GENERATION_FAILED = "generation_failed"
    SAFETY_REJECTED = "safety_rejected"
    ACCESS_DENIED = "access_denied"
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"


class StateTransitionRecord(BaseModel):
    """Record of a state transition during runtime execution."""

    from_state: RuntimeState
    to_state: RuntimeState
    elapsed_ms: float = Field(ge=0.0)


class RuntimeTrace(BaseModel):
    """Complete observability trace for an end-to-end runtime execution."""

    run_id: str
    state_history: list[StateTransitionRecord] = Field(default_factory=list)
    final_state: RuntimeState
    orchestration_trace: OrchestrationTrace | None = None
    ast_referenced_tables: list[str] = Field(default_factory=list)
    safety_check_passed: bool = False
    access_check_passed: bool = False
    execution_passed: bool = False


class RuntimeExecutionResult(BaseModel):
    """Result of an end-to-end safe Text-to-SQL runtime execution."""

    run_id: str
    status: RuntimeStatus
    sql: str | None = None
    dialect: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    has_more_rows: bool = False
    execution_time_ms: int | None = None
    total_latency_ms: float = Field(default=0.0, ge=0.0)
    orchestration_outcome: OrchestrationOutcome | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    trace: RuntimeTrace

    def to_query_response(self, request_id: str, trace_id: str) -> QueryResponse:
        """Convert runtime result into API presentation contract (QueryResponse)."""
        status: Literal["answer", "ambiguous", "abstain", "error"]
        if self.status == RuntimeStatus.COMPLETED:
            status = "answer"
            explanation = "SQL successfully generated, validated, and executed."
            answer = AnswerPayload(columns=self.columns, rows=self.rows)
            policy = "safe-runtime-v1"
            reason = "execution_succeeded"
        elif self.status in {RuntimeStatus.UNRESOLVED, RuntimeStatus.GENERATION_FAILED}:
            status = "abstain"
            explanation = self.error_message or "Query could not be resolved safely."
            answer = None
            policy = "safe-runtime-v1"
            reason = self.status.value
        elif self.status in {RuntimeStatus.SAFETY_REJECTED, RuntimeStatus.ACCESS_DENIED}:
            status = "abstain"
            explanation = self.error_message or "Query rejected by security policies."
            answer = None
            policy = "security-gate-v1"
            reason = self.status.value
        else:
            status = "error"
            explanation = self.error_message or "Query execution failed."
            answer = None
            policy = "execution-gate-v1"
            reason = self.status.value

        evidence_summary: list[str] = []
        if self.trace.ast_referenced_tables:
            evidence_summary.append(
                f"ast_tables={','.join(self.trace.ast_referenced_tables)}"
            )
        if self.orchestration_outcome:
            evidence_summary.append(f"orchestration_outcome={self.orchestration_outcome.value}")

        return QueryResponse(
            request_id=request_id,
            run_id=self.run_id,
            trace_id=trace_id,
            status=status,
            answer=answer,
            sql=self.sql,
            explanation=explanation,
            decision=QueryDecision(
                policy=policy,
                reason=reason,
            ),
            evidence_summary=evidence_summary,
            warnings=self.warnings,
        )
