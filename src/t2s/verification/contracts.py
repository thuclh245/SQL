from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
    short_reason: str = Field(default="", description="Concise rationale for the check status.")
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

    model_config = ConfigDict(extra="forbid")

    question: str
    evidence: str
    dialect: str = "sqlite"
    authorized_schema: str
    candidate_sql: str
    authorized_tables: list[str] = Field(default_factory=list)
    authorized_columns: dict[str, list[str]] = Field(default_factory=dict)
    glossary: list[str] = Field(default_factory=list)
    value_bindings: list[str] = Field(default_factory=list)
