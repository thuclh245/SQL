"""Context and serialization experiment profiles for causal evaluation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from t2s.grounding.grounding_budget import GroundingBudget

ContextSelectionArm = Literal["C0", "C1", "C2"]
ContextSerializationArm = Literal["S0", "S1", "S2", "S3"]


def resolve_grounding_budget_for_arm(arm: ContextSelectionArm) -> GroundingBudget:
    """Resolve the deterministic GroundingBudget for a context selection arm.

    - C0: Frozen B0 baseline control budget.
    - C1: Compact context budget reducing candidate and column volume.
    - C2: Expanded context budget testing coverage and omission effects.
    """
    if arm == "C0":
        return GroundingBudget(
            max_candidate_tables=50,
            max_hydrated_tables=8,
            max_columns_per_table=12,
            max_total_columns=60,
            max_relationships=16,
            relationship_expansion_mode="conditional",
            fill_column_budget=False,
            small_db_threshold=0,
        )
    if arm == "C1":
        return GroundingBudget(
            max_candidate_tables=25,
            max_hydrated_tables=4,
            max_columns_per_table=6,
            max_total_columns=24,
            max_relationships=6,
            relationship_expansion_mode="conditional",
            fill_column_budget=False,
            small_db_threshold=0,
        )
    if arm == "C2":
        return GroundingBudget(
            max_candidate_tables=100,
            max_hydrated_tables=16,
            max_columns_per_table=24,
            max_total_columns=120,
            max_relationships=32,
            relationship_expansion_mode="conditional",
            fill_column_budget=True,
            small_db_threshold=0,
        )
    raise ValueError(f"Unsupported context selection arm: {arm}")


class ContextExperimentProfile(BaseModel):
    """Configuration profile for context selection and serialization experiment arms.

    Consumed by evaluation-side experiment runners only; the default runtime
    (assembled in ``t2s.bootstrap.runtime_factory``) never imports this module
    and keeps the S0 baseline serializer with the operator-supplied budget.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_arm: ContextSelectionArm = Field(default="C0")
    serialization_arm: ContextSerializationArm = Field(default="S0")

    def get_grounding_budget(self) -> GroundingBudget:
        return resolve_grounding_budget_for_arm(self.selection_arm)
