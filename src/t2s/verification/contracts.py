from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class VerificationDecision(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"


class SemanticCheckResult(BaseModel):
    status: CheckStatus
    short_reason: str = Field(
        default="", description="Concise rationale for the check status."
    )
    question_evidence: str = Field(
        default="", description="Relevant snippet from question/evidence."
    )
    sql_evidence: str = Field(default="", description="Relevant snippet from candidate SQL.")


SEMANTIC_CHECK_DIMENSIONS = (
    "projection",
    "aggregation_and_grain",
    "filters_and_values",
    "join_semantics",
    "ordering_and_limit",
    "null_semantics",
    "schema_reference",
)


class VerificationResult(BaseModel):
    projection: SemanticCheckResult
    aggregation_and_grain: SemanticCheckResult
    filters_and_values: SemanticCheckResult
    join_semantics: SemanticCheckResult
    ordering_and_limit: SemanticCheckResult
    null_semantics: SemanticCheckResult
    schema_reference: SemanticCheckResult
    decision: VerificationDecision
    failed_checks: list[str] = Field(default_factory=list)
    unknown_checks: list[str] = Field(default_factory=list)
    confidence: float | None = Field(
        default=None, description="Diagnostic model confidence if available."
    )


class VerificationInput(BaseModel):
    """Inference-time input for SQL verification.

    Strictly isolated: does NOT contain gold SQL, gold results, or generator uncertainty.
    """

    question: str
    evidence: str
    dialect: str = "sqlite"
    authorized_schema: str
    candidate_sql: str
    authorized_tables: list[str] = Field(default_factory=list)
    authorized_columns: dict[str, list[str]] = Field(default_factory=dict)
    glossary: list[str] = Field(default_factory=list)
    value_bindings: list[str] = Field(default_factory=list)


class VerifierCandidateRecord(BaseModel):
    """Evaluator-side candidate record with strictly isolated ground truth metadata."""

    candidate_id: str
    source_run_id: str
    case_id: str
    question_id: int | None = None
    db_id: str
    t2s_stratum: str | None = None
    bird_difficulty: str | None = None

    question: str
    evidence: str
    dialect: str = "sqlite"

    grounding_context: dict[str, Any] = Field(default_factory=dict)
    candidate_sql: str

    runtime_origin: str  # "EXECUTED" or "REJECTED_BY_P5"
    evaluator_correctness_label: bool
    gold_sql: str | None = None

    def to_verification_input(self, authorized_schema_text: str | None = None) -> VerificationInput:
        """Constructs a VerificationInput strictly free of gold or evaluation labels."""
        schema_text = authorized_schema_text or self.grounding_context.get("formatted_schema", "")
        auth_tables = self.grounding_context.get("authorized_tables", [])
        auth_cols = self.grounding_context.get("authorized_columns", {})
        glossary = self.grounding_context.get("glossary", [])
        values = self.grounding_context.get("value_bindings", [])
        return VerificationInput(
            question=self.question,
            evidence=self.evidence,
            dialect=self.dialect,
            authorized_schema=schema_text,
            candidate_sql=self.candidate_sql,
            authorized_tables=auth_tables,
            authorized_columns=auth_cols,
            glossary=glossary,
            value_bindings=values,
        )
