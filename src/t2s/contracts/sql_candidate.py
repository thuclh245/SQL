from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SupportedSqlDialect = Literal["postgres", "clickhouse", "starrocks", "sqlite", "trino"]


class GenerationTrace(BaseModel):
    run_id: str
    model_name: str
    prompt_version: str
    reasoning_effort: str | None = None
    max_output_tokens: int | None = None
    elapsed_ms: int | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None


class SqlCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str
    dialect: SupportedSqlDialect
    referenced_tables: list[str] = Field(default_factory=list)
    referenced_columns: list[str] = Field(default_factory=list)
    expected_columns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    generation_trace: GenerationTrace

    @field_validator("sql")
    @classmethod
    def validate_sql_is_not_empty(cls, sql: str) -> str:
        stripped_sql = sql.strip()
        if not stripped_sql:
            raise ValueError("SQL candidate must not be empty.")
        return stripped_sql
