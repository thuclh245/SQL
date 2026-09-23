from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ColumnContext(BaseModel):
    name: str
    data_type: str
    description: str | None = None
    # None = nullability unknown (source metadata is silent). Never coerce to a
    # factual True/False, which would fabricate a constraint for the solver (F1).
    is_nullable: bool | None = None
    is_primary_key: bool = False


class RelationshipEvidence(BaseModel):
    from_table_fqn: str
    from_columns: list[str] = Field(default_factory=list)
    to_table_fqn: str
    to_columns: list[str] = Field(default_factory=list)
    relationship_type: Literal["many_to_one", "one_to_many", "one_to_one"] = "many_to_one"
    evidence_summary: str | None = None

    @model_validator(mode="after")
    def validate_relationship_columns_are_present(self) -> "RelationshipEvidence":
        if not self.from_columns or not self.to_columns:
            raise ValueError("Relationship evidence must include from_columns and to_columns.")
        if len(self.from_columns) != len(self.to_columns):
            raise ValueError("Relationship evidence column lists must have matching lengths.")
        return self

    @property
    def from_column(self) -> str:
        return self.from_columns[0]

    @property
    def to_column(self) -> str:
        return self.to_columns[0]


class TableContext(BaseModel):
    fqn: str
    sql_identifier: str
    description: str | None = None
    columns: list[ColumnContext]
    relationships: list[RelationshipEvidence] = Field(default_factory=list)


class EvidenceRef(BaseModel):
    kind: Literal["metadata", "glossary", "profile", "query_history", "db_probe", "semantic"]
    source_id: str
    source_version: str | None = None
    observed_at: datetime | None = None
    summary: str


class GlossaryHit(BaseModel):
    term: str
    definition: str
    evidence_ref: str | None = None


class ValueBinding(BaseModel):
    """A phrase from the question linked to a literal observed in the database.

    ``value`` is the database's own spelling, so the solver can emit a literal
    that compares equal; ``phrase`` keeps the user's wording for explanation.
    """

    phrase: str
    column_fqn: str
    value: str
    match_type: Literal["exact", "case_insensitive", "lexical"] | None = None
    evidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_ref: str | None = None


class GroundingIssue(BaseModel):
    code: str
    message: str


class ValidatedQueryExample(BaseModel):
    question: str
    sql: str
    dialect: Literal["postgres", "clickhouse", "starrocks", "sqlite", "trino"]
    evidence_ref: str | None = None


class GroundingContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_id: str
    tables: list[TableContext]
    glossary_hits: list[GlossaryHit] = Field(default_factory=list)
    value_bindings: list[ValueBinding] = Field(default_factory=list)
    unresolved: list[GroundingIssue] = Field(default_factory=list)
    examples: list[ValidatedQueryExample] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    retrieval_signals: dict[str, float] = Field(default_factory=dict)
