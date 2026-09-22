from typing import Literal

from pydantic import BaseModel, Field


class GroundingBudget(BaseModel):
    max_candidate_tables: int = Field(default=50, gt=0)
    max_hydrated_tables: int = Field(default=10, gt=0)
    max_columns_per_table: int = Field(default=120, gt=0)
    max_total_columns: int = Field(default=250, gt=0)
    max_relationships: int = Field(default=24, ge=0)

    relationship_expansion_mode: Literal[
        "conditional", "unconditional", "relationship_priority"
    ] = Field(default="relationship_priority")
    fill_column_budget: bool = Field(default=True)
    small_db_threshold: int = Field(default=5, ge=0)
