from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from t2s.contracts.sql_candidate import SupportedSqlDialect


class SolverStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


def _add_strict_constraints(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively add additionalProperties: false to all object schemas.

    Required by OpenAI Structured Outputs API when strict=True.
    """
    schema = dict(schema)
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        if "properties" in schema:
            schema["properties"] = {
                k: _add_strict_constraints(v) for k, v in schema["properties"].items()
            }
    if "items" in schema:
        schema["items"] = _add_strict_constraints(schema["items"])
    if "$defs" in schema:
        schema["$defs"] = {k: _add_strict_constraints(v) for k, v in schema["$defs"].items()}
    return schema


def build_sql_candidate_json_schema() -> dict[str, Any]:
    schema = SolverStructuredOutput.model_json_schema()
    schema = _add_strict_constraints(schema)
    return {
        "name": "sql_candidate",
        "schema": schema,
        "strict": True,
    }


class StructuredChatResponse(BaseModel):
    content: dict[str, Any]
    model_name: str
    elapsed_ms: int
    prompt_tokens: int | None = None
    output_tokens: int | None = None
