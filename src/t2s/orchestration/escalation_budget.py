"""Escalation budget configuration for bounded adaptive orchestration."""

from pydantic import BaseModel, Field


class EscalationBudget(BaseModel):
    """Controls the bounded expansion for escalated grounding attempts.

    All values are additive deltas applied on top of the baseline
    GroundingBudget when performing escalated regrounding.
    """

    max_escalations: int = Field(default=1, ge=0, le=3)
    grounding_table_delta: int = Field(default=4, ge=1)
    grounding_column_delta: int = Field(default=12, ge=1)
    grounding_relationship_delta: int = Field(default=8, ge=0)
