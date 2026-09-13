from pydantic import BaseModel


class QueryExplainResult(BaseModel):
    plan_text: str
    elapsed_ms: int | None = None
