"""Typed immutable contracts for grounded semantic planning.

Represents the semantic interpretation of the question derived from
grounding evidence, decoupled from SQL syntax generation.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlannerStatus(StrEnum):
    """Lifecycle status of the semantic planning phase."""

    READY = "READY"
    UNCERTAIN = "UNCERTAIN"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class MetricAggregation(StrEnum):
    """Semantic aggregation intent."""

    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    RATIO_PERCENTAGE = "RATIO_PERCENTAGE"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class ResultShape(StrEnum):
    """Expected structural shape of the query result."""

    SCALAR = "SCALAR"
    LIST = "LIST"
    GROUPED_TABLE = "GROUPED_TABLE"
    RECORD = "RECORD"
    UNKNOWN = "UNKNOWN"


class ExpectedValueType(StrEnum):
    """Expected semantic value type."""

    NUMERIC = "NUMERIC"
    TEXT = "TEXT"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    UNKNOWN = "UNKNOWN"


class SemanticEvidence(BaseModel):
    """Structured evidence item supporting a semantic interpretation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    entity: str
    field: str
    value: str
    confidence: float = 1.0


class SemanticGrain(BaseModel):
    """Explicit representation of metric and dimensional grains."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_grain: str = "unknown"
    source_grain: str = "unknown"
    requires_normalization: bool = False
    normalization_notes: str | None = None


class SemanticFilter(BaseModel):
    """Structured filter requirement grounded in evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    column_name: str
    operator: str
    target_value: str | None = None
    is_temporal: bool = False
    evidence_source: str | None = None


class ResultExpectation(BaseModel):
    """Typed runtime expectations for post-execution result validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_shape: ResultShape = ResultShape.UNKNOWN
    expected_value_type: ExpectedValueType = ExpectedValueType.UNKNOWN
    can_be_empty: bool = False
    can_be_null: bool = False
    min_expected_rows: int = 0
    max_expected_rows: int | None = None


class SemanticPlan(BaseModel):
    """Typed immutable contract representing semantic query interpretation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str
    status: PlannerStatus = PlannerStatus.INSUFFICIENT_EVIDENCE
    metric_name: str | None = None
    aggregation: MetricAggregation = MetricAggregation.NONE
    dimensions: list[str] = Field(default_factory=list)
    population_scope: str | None = None
    filters: list[SemanticFilter] = Field(default_factory=list)
    time_scope: str | None = None
    grain: SemanticGrain = Field(default_factory=SemanticGrain)
    relevant_tables: list[str] = Field(default_factory=list)
    relevant_columns: list[str] = Field(default_factory=list)
    required_relationships: list[str] = Field(default_factory=list)
    expectation: ResultExpectation = Field(default_factory=ResultExpectation)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence: list[SemanticEvidence] = Field(default_factory=list)
    semantic_uncertainty_level: str = "HIGH"
    metadata_notes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_anchors_and_status(self) -> "SemanticPlan":
        has_anchors = bool(
            self.relevant_tables
            or self.metric_name
            or self.filters
            or self.dimensions
        )
        if self.status == PlannerStatus.READY and not has_anchors:
            object.__setattr__(self, "status", PlannerStatus.INSUFFICIENT_EVIDENCE)
            object.__setattr__(self, "semantic_uncertainty_level", "HIGH")
        return self
