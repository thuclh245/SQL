from pydantic import BaseModel, Field


class QueryExecutionPolicy(BaseModel):
    read_only_required: bool = True
    statement_timeout_seconds: int = Field(default=30, gt=0)
    maximum_result_rows: int = Field(default=1000, gt=0)
