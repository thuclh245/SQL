from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    # Business context supplied by the caller, kept separate from the question so
    # the solver can tell reference material from the user's instruction. In
    # production this is filled from governed sources (metadata, glossary,
    # approved business context), never from a benchmark answer key.
    evidence: list[str] = Field(default_factory=list, max_length=32)
    locale: Literal["vi", "en", "auto"] = "auto"
    target_hint: str | None = None
    client_request_id: str | None = Field(default=None, max_length=128)
    database_dialect: (
        Literal["postgres", "clickhouse", "starrocks", "sqlite", "trino"] | None
    ) = None

    @field_validator("question")
    @classmethod
    def validate_question_has_semantic_text(cls, question: str) -> str:
        stripped_question = question.strip()
        if not stripped_question:
            raise ValueError("Question must contain non-whitespace text.")
        return stripped_question
