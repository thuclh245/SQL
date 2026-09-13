from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ColumnContext(BaseModel):
    name: str
    data_type: str
    description: str | None = None
    is_nullable: bool = True


class RelationshipEvidence(BaseModel):
    from_table_fqn: str
    from_column: str
    to_table_fqn: str
    to_column: str
    relationship_type: Literal["many_to_one", "one_to_many", "one_to_one"] = "many_to_one"
    evidence_summary: str | None = None


class TableContext(BaseModel):
    fqn: str
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
    phrase: str
    column_fqn: str
    value: str
    evidence_ref: str | None = None


class GroundingIssue(BaseModel):
    code: str
    message: str


class ValidatedQueryExample(BaseModel):
    question: str
    sql: str
    dialect: Literal["postgres", "clickhouse", "starrocks", "sqlite"]
    evidence_ref: str | None = None


class GroundingContext(BaseModel):
    scope_id: str
    tables: list[TableContext]
    glossary_hits: list[GlossaryHit] = Field(default_factory=list)
    value_bindings: list[ValueBinding] = Field(default_factory=list)
    unresolved: list[GroundingIssue] = Field(default_factory=list)
    examples: list[ValidatedQueryExample] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    retrieval_signals: dict[str, float] = Field(default_factory=dict)
