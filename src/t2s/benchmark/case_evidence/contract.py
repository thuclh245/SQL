"""Canonical, versioned case-run evidence contract (E04 §6, §12, §13).

``CaseRunRecord`` is the single source of truth for one *replicate* of one case.
It is intentionally structured so that:

* Every model call is reconstructable: the exact ordered prompt messages, the
  exact serialized grounding context, and the raw structured model output are all
  present (E04 §7, §8, §9).
* It structurally satisfies the E05 consumption protocol
  :class:`t2s.evaluation.scoring.protocols.CaseRunEvidence` (version
  ``e05.case_evidence.v1``): the field names ``case_id``, ``replicate_id``,
  ``db_id``, ``question``, ``evidence_context``, ``candidate_sql``, ``gold_sql``,
  ``runtime_status``, ``candidate_execution_ok``, ``gold_execution_ok``,
  ``candidate_result``, ``gold_result``, ``candidate_fingerprint``,
  ``gold_fingerprint`` and ``db_path`` are present with matching semantics. E04
  never fabricates gold text; ``gold_sql``/``gold_result`` stay ``None`` in the
  evidence tree and E05 supplies gold text from the dataset when scoring.

Unknown values are ``None``; they are never fabricated (E04 §6).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: Version of the E04 record schema itself.
SCHEMA_VERSION = "e04.case_run_record.v1"

#: The E05 consumption-protocol version this record is designed to satisfy.
#: Kept in sync with ``t2s.evaluation.scoring.versions.CONSUMED_CASE_RECORD_PROTOCOL_VERSION``.
E05_CONSUMED_PROTOCOL_VERSION = "e05.case_evidence.v1"


class EvidenceCompleteness(StrEnum):
    """Machine-checkable reconstructability of a case (E04 §12)."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class GenerationOutcome(StrEnum):
    """Distinct generation/execution states (E04 §13).

    These separate *how* a case ended so that a provider failure is never
    conflated with an empty generation, a rejected candidate, or a semantically
    wrong-but-executed answer.
    """

    PROVIDER_ERROR = "PROVIDER_ERROR"
    GENERATION_EMPTY = "GENERATION_EMPTY"
    SQL_EXTRACTION_ERROR = "SQL_EXTRACTION_ERROR"
    VALIDATION_REJECTED = "VALIDATION_REJECTED"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    EXECUTION_SUCCESS = "EXECUTION_SUCCESS"
    ABSTAIN = "ABSTAIN"
    UNKNOWN = "UNKNOWN"


class ChatMessageRecord(BaseModel):
    """One ordered message in the exact prompt sent to the provider."""

    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class ChatCallRecord(BaseModel):
    """Exact evidence for a single provider call (E04 §7, §9).

    ``messages`` is the exact ordered prompt content handed to the chat client
    (the substantive prompt). Model configuration that lives on the client rather
    than in the messages (temperature, token-limit parameter) is recorded once in
    the experiment manifest and echoed in :class:`CaseRunRecord`. Secrets (API
    keys, auth headers) are never captured (E04 §7).
    """

    model_config = ConfigDict(extra="forbid")

    ordinal: int
    purpose: str | None = None
    schema_name: str | None = None
    model_name_requested: str | None = None
    model_name_returned: str | None = None
    reasoning_effort: str | None = None
    max_output_tokens: int | None = None
    messages: list[ChatMessageRecord] = Field(default_factory=list)
    prompt_hash: str | None = None
    raw_model_output: dict[str, Any] | None = None
    raw_model_output_hash: str | None = None
    extracted_sql: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    elapsed_ms: int | None = None
    error_class: str | None = None
    error_message: str | None = None


class GroundingCaptureRecord(BaseModel):
    """Exact grounding/context that entered the solver (E04 §8).

    ``serialized_authorized_schema`` is the byte-for-byte string embedded in the
    solver prompt. The structured fields are provenance for audit; they describe
    what was *selected*, distinct from what was merely retrieved.
    """

    model_config = ConfigDict(extra="forbid")

    ordinal: int
    selected_tables: list[str] = Field(default_factory=list)
    selected_columns: list[str] = Field(default_factory=list)
    selected_relationships: list[dict[str, Any]] = Field(default_factory=list)
    glossary_terms: list[str] = Field(default_factory=list)
    value_binding_columns: list[str] = Field(default_factory=list)
    example_count: int = 0
    unresolved_codes: list[str] = Field(default_factory=list)
    serialized_authorized_schema: str = ""
    serialized_context_hash: str | None = None


class CaseRunRecord(BaseModel):
    """Canonical evidence for one replicate of one evaluation case (E04 §6)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION

    # --- identity / clustering (E04 §14) ---
    experiment_id: str
    run_id: str
    replicate_id: str
    case_id: str
    db_id: str | None = None

    question: str | None = None

    # --- dataset provenance ---
    dataset_name: str | None = None
    dataset_split: str | None = None
    dataset_version_or_hash: str | None = None

    # --- source provenance ---
    source_commit: str | None = None
    source_dirty: bool | None = None

    # --- grounding (E04 §8) ---
    grounding_strategy: str | None = None
    grounding_config_hash: str | None = None
    selected_tables: list[str] = Field(default_factory=list)
    selected_columns: list[str] = Field(default_factory=list)
    selected_relationships: list[dict[str, Any]] = Field(default_factory=list)
    exact_grounded_context: str | None = None
    grounded_context_hash: str | None = None
    #: Alias consumed by E05 (context/evidence delivered to the model).
    evidence_context: str | None = None
    grounding_captures: list[GroundingCaptureRecord] = Field(default_factory=list)

    # --- prompt (E04 §7) ---
    prompt_version: str | None = None
    exact_solver_prompt: list[ChatMessageRecord] = Field(default_factory=list)
    solver_prompt_hash: str | None = None
    chat_calls: list[ChatCallRecord] = Field(default_factory=list)

    # --- model configuration ---
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    seed_or_null: int | None = None
    retry_policy: dict[str, Any] | None = None
    correction_budget: int | None = None

    # --- generation (E04 §9 hard gate: raw output preserved separately) ---
    candidate_sql: str | None = None
    candidate_sql_hash: str | None = None
    raw_model_output: dict[str, Any] | None = None
    raw_model_output_hash: str | None = None
    solver_assumptions: list[str] = Field(default_factory=list)
    solver_unresolved_items: list[str] = Field(default_factory=list)
    generation_outcome: GenerationOutcome = GenerationOutcome.UNKNOWN

    # --- validation / verification ---
    validator_mode: str | None = None
    verifier_mode: str | None = None
    ast_summary: dict[str, Any] | None = None
    validation_outputs: dict[str, Any] | None = None

    # --- execution (E04 §10) ---
    execution_attempted: bool = False
    execution_status: str | None = None
    execution_error_class: str | None = None
    runtime_status: str | None = None
    candidate_execution_ok: bool | None = None
    candidate_result_schema: list[str] | None = None
    candidate_result_row_count: int | None = None
    candidate_result_fingerprint: str | None = None
    #: E05 protocol name for the candidate result fingerprint.
    candidate_fingerprint: str | None = None
    #: Optional materialized result table; kept ``None`` by default (fingerprints
    #: preferred in general manifests, E04 §10). Typed loosely to avoid an
    #: E04 -> E05 import; E05 reads it structurally.
    candidate_result: Any | None = None

    # --- gold (governed; text never persisted here, E04 §10/§19) ---
    gold_sql: str | None = None
    gold_result: Any | None = None
    gold_result_fingerprint: str | None = None
    gold_fingerprint: str | None = None
    gold_execution_ok: bool | None = None

    # --- correlation / timing ---
    latency_breakdown: dict[str, Any] | None = None
    request_id: str | None = None
    trace_id: str | None = None
    created_at: str | None = None

    # --- evaluation-only handle (never used to alter runtime, E05 §3) ---
    db_path: str | None = None

    # --- completeness (E04 §12) ---
    evidence_completeness: EvidenceCompleteness = EvidenceCompleteness.INSUFFICIENT


def classify_evidence_completeness(
    *,
    has_exact_prompt: bool,
    has_exact_context: bool,
    has_candidate_or_explicit_failure: bool,
    has_model_config: bool,
    has_execution_record: bool,
    has_provenance: bool,
) -> EvidenceCompleteness:
    """Machine-checkable completeness classification (E04 §12).

    COMPLETE requires every reconstruction input: exact prompt, exact context,
    candidate SQL *or* an explicit generation-failure state, model config, an
    execution record, and provenance. If the semantic-audit inputs (prompt +
    context + candidate/explicit-failure) are missing, the case is INSUFFICIENT
    because a semantic audit cannot be reproduced. Otherwise it is PARTIAL.
    """

    semantic_audit_reconstructable = (
        has_exact_prompt and has_exact_context and has_candidate_or_explicit_failure
    )
    if not semantic_audit_reconstructable:
        return EvidenceCompleteness.INSUFFICIENT
    if has_model_config and has_execution_record and has_provenance:
        return EvidenceCompleteness.COMPLETE
    return EvidenceCompleteness.PARTIAL
