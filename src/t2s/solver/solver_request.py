from pydantic import BaseModel, ConfigDict, Field

from t2s.contracts import GroundingContext, QueryRequest
from t2s.contracts.sql_candidate import SupportedSqlDialect
from t2s.semantics.semantic_plan import SemanticPlan


class SolverGenerationSettings(BaseModel):
    reasoning_effort: str | None = None
    max_output_tokens: int = Field(default=2048, gt=0)


class SolverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    query_request: QueryRequest
    target_dialect: SupportedSqlDialect
    grounding_context: GroundingContext
    semantic_plan: SemanticPlan | None = None
    generation_settings: SolverGenerationSettings = Field(default_factory=SolverGenerationSettings)
