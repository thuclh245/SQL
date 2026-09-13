from typing import Any, Literal

from pydantic import BaseModel, Field


class AnswerPayload(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class QueryDecision(BaseModel):
    score: float | None = None
    policy: str
    reason: str


class QueryResponse(BaseModel):
    request_id: str
    run_id: str
    trace_id: str
    status: Literal["answer", "ambiguous", "abstain", "error"]
    answer: AnswerPayload | None = None
    sql: str | None = None
    explanation: str
    decision: QueryDecision
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
