"""Typed contracts for database value grounding (value linking).

Value grounding answers one question: which literal values stored in the
authorized database correspond to terms the user wrote? The solver then filters
on observed literals instead of inventing them.

These contracts are dialect-neutral. Adapters translate them into concrete,
parameterized, read-only probes.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ValueMatchType(StrEnum):
    """How a database literal was matched against a term from the question."""

    EXACT = "exact"
    CASE_INSENSITIVE = "case_insensitive"
    LEXICAL = "lexical"


class ValueProbeColumn(BaseModel):
    """An authorized column that value grounding is allowed to probe.

    ``sql_identifier`` and ``column_name`` always originate from the catalog,
    never from user input, so adapters may safely quote them as identifiers.
    """

    model_config = ConfigDict(frozen=True)

    table_fqn: str
    sql_identifier: str
    column_name: str
    data_type: str


class ValueProbeRequest(BaseModel):
    """A single bounded lookup against one column.

    ``match_terms`` holds every spelling worth testing for equality, including
    case variants precomputed in Python so that folding is Unicode-correct and
    independent of the database's collation. They are always bound as query
    parameters, never interpolated.
    """

    model_config = ConfigDict(frozen=True)

    column: ValueProbeColumn
    match_terms: tuple[str, ...] = ()
    max_values: int = Field(default=5, gt=0)
    timeout_ms: int = Field(default=1500, gt=0)


class ValueProbeOutcome(BaseModel):
    """Literals observed for one column, plus whether the domain was truncated.

    ``domain_truncated`` marks a column whose distinct values exceeded the
    enumeration budget; such a column is treated as high-cardinality and its
    partial domain is never rendered into a prompt.
    """

    column: ValueProbeColumn
    observed_values: list[str] = Field(default_factory=list)
    domain_truncated: bool = False
    probe_count: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0.0, ge=0.0)
    error_message: str | None = None


class ValueBindingCandidate(BaseModel):
    """One question term linked to one literal observed in the database."""

    model_config = ConfigDict(frozen=True)

    table_fqn: str
    column_name: str
    phrase: str
    candidate_value: str
    match_type: ValueMatchType
    evidence_score: float = Field(ge=0.0, le=1.0)


class ValueGroundingDiagnostics(BaseModel):
    """Observability for one value-grounding pass.

    Recorded whether or not any binding was produced, so an empty result is
    always distinguishable from a skipped or failed pass.
    """

    enabled: bool = True
    candidate_column_count: int = Field(default=0, ge=0)
    probed_column_count: int = Field(default=0, ge=0)
    probe_count: int = Field(default=0, ge=0)
    binding_count: int = Field(default=0, ge=0)
    term_count: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0.0, ge=0.0)
    skipped_reason: str | None = None
    error_messages: list[str] = Field(default_factory=list)


class ValueGroundingResult(BaseModel):
    """Bindings plus diagnostics from a value-grounding pass."""

    bindings: list[ValueBindingCandidate] = Field(default_factory=list)
    diagnostics: ValueGroundingDiagnostics = Field(default_factory=ValueGroundingDiagnostics)
