from typing import Any

from pydantic import BaseModel, Field


class QueryExecutionResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    has_more_rows: bool = False
    elapsed_ms: int | None = None
    warnings: list[str] = Field(default_factory=list)
