from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    locale: Literal["vi", "en", "auto"] = "auto"
    target_hint: str | None = None
    client_request_id: str | None = Field(default=None, max_length=128)
    database_dialect: Literal["postgres", "clickhouse", "starrocks", "sqlite"] | None = None
