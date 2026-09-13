from typing import Any

from pydantic import BaseModel, field_validator

from t2s.contracts.sql_candidate import SupportedSqlDialect


class SolverStructuredOutput(BaseModel):
    sql: str
    dialect: SupportedSqlDialect
    referenced_tables: list[str]
    referenced_columns: list[str]
    expected_columns: list[str]
    assumptions: list[str]
    unresolved: list[str]

    @field_validator("sql")
    @classmethod
    def validate_sql_is_not_empty(cls, sql: str) -> str:
        stripped_sql = sql.strip()
        if not stripped_sql:
            raise ValueError("Structured solver output SQL must not be empty.")
        return stripped_sql


class StructuredChatResponse(BaseModel):
    content: dict[str, Any]
    model_name: str
    elapsed_ms: int
    prompt_tokens: int | None = None
    output_tokens: int | None = None
