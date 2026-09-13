from pydantic import BaseModel, Field

from t2s.contracts import GroundingContext, QueryRequest
from t2s.contracts.sql_candidate import SupportedSqlDialect


class SolverGenerationSettings(BaseModel):
    reasoning_effort: str | None = None
    max_output_tokens: int = Field(default=2048, gt=0)


class SolverRequest(BaseModel):
    run_id: str
    query_request: QueryRequest
    target_dialect: SupportedSqlDialect
    grounding_context: GroundingContext
    generation_settings: SolverGenerationSettings = Field(default_factory=SolverGenerationSettings)
