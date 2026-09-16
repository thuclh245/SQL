from typing import Literal

from pydantic import BaseModel, Field


class GroundingBudget(BaseModel):
    max_candidate_tables: int = Field(default=50, gt=0)
    max_hydrated_tables: int = Field(default=8, gt=0)
    max_columns_per_table: int = Field(default=12, gt=0)
    max_total_columns: int = Field(default=60, gt=0)
    max_relationships: int = Field(default=16, ge=0)
    relationship_expansion_mode: Literal[
        "conditional", "unconditional", "relationship_priority"
    ] = Field(default="conditional")
    fill_column_budget: bool = Field(default=False)
    small_db_threshold: int = Field(default=0, ge=0)
