"""Observational capture of exact prompt, grounding, and raw model output.

Everything here is *observational* (E04 §4): the wrappers delegate to the real
implementations and return their results unchanged. They never alter the prompt,
the grounding, the model configuration, or the returned SQL.

Two capture points, correlated per case by a :class:`contextvars.ContextVar`:

* :class:`RecordingChatClient` wraps a :class:`StructuredChatClient` and records
  the exact ordered messages sent to the provider and the raw structured model
  output returned (E04 §7, §9). It never captures API keys or headers.
* :func:`recording_schema_serializer` produces a ``schema_serializer`` that
  records the :class:`GroundingContext` provenance and the byte-for-byte
  serialized authorized schema, while returning exactly what the default
  serializer would return (E04 §8) so the prompt is unchanged.

Correlation uses a context variable set by the harness around each case. In
asyncio, ``asyncio.gather`` runs each case coroutine in its own task with its own
copied context, so concurrent cases never cross-contaminate.
"""

from __future__ import annotations

import contextvars
import copy
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from t2s.benchmark.case_evidence.contract import (
    ChatCallRecord,
    ChatMessageRecord,
    GroundingCaptureRecord,
)
from t2s.benchmark.case_evidence.hashing import sha256_json, sha256_text
from t2s.contracts import GroundingContext
from t2s.solver.chat_client import StructuredChatClient
from t2s.solver.prompt_builder import DirectSqlPromptBuilder
from t2s.solver.solver_response import StructuredChatResponse

#: Active case correlation key. ``None`` means "no case scope" and capture is a
#: no-op (so the wrappers are safe to leave installed outside a run).
_active_case_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "t2s_case_evidence_active_case", default=None
)


@dataclass
class CaseChatEvidence:
    """All chat calls and grounding captures observed for one case scope."""

    chat_calls: list[ChatCallRecord] = field(default_factory=list)
    grounding_captures: list[GroundingCaptureRecord] = field(default_factory=list)


class CaseEvidenceRecorder:
    """Thread-safe sink keyed by the active case correlation key."""

    def __init__(self) -> None:
        self._by_key: dict[str, CaseChatEvidence] = {}
        self._lock = threading.Lock()

    def _bucket(self, key: str) -> CaseChatEvidence:
        bucket = self._by_key.get(key)
        if bucket is None:
            bucket = CaseChatEvidence()
            self._by_key[key] = bucket
        return bucket

    def record_chat_call(self, key: str, call: ChatCallRecord) -> None:
        with self._lock:
            bucket = self._bucket(key)
            call.ordinal = len(bucket.chat_calls)
            bucket.chat_calls.append(call)

    def record_grounding(self, key: str, capture: GroundingCaptureRecord) -> None:
        with self._lock:
            bucket = self._bucket(key)
            capture.ordinal = len(bucket.grounding_captures)
            bucket.grounding_captures.append(capture)

    def evidence_for(self, key: str) -> CaseChatEvidence:
        with self._lock:
            return self._by_key.get(key, CaseChatEvidence())

    def pop(self, key: str) -> CaseChatEvidence:
        with self._lock:
            return self._by_key.pop(key, CaseChatEvidence())


def set_active_case(key: str) -> contextvars.Token[str | None]:
    """Enter a case scope; returns a token to restore the previous scope."""

    return _active_case_key.set(key)


def reset_active_case(token: contextvars.Token[str | None]) -> None:
    _active_case_key.reset(token)


def active_case_key() -> str | None:
    return _active_case_key.get()


def _messages_to_records(messages: list[dict[str, str]]) -> list[ChatMessageRecord]:
    return [
        ChatMessageRecord(
            role=str(message.get("role", "")),
            content=str(message.get("content", "")),
        )
        for message in messages
    ]


class RecordingChatClient:
    """Observational wrapper over a :class:`StructuredChatClient`.

    Delegates every call to ``inner`` and returns its response unchanged. When a
    case scope is active it records the exact messages, the requested model
    configuration, and the raw structured model output (or the error class on
    failure). Only the substantive prompt is captured — never headers or keys.
    """

    def __init__(self, inner: StructuredChatClient, recorder: CaseEvidenceRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        key = _active_case_key.get()
        # Snapshot the exact prompt before delegating so a downstream mutation
        # cannot alter what we recorded.
        prompt_records = _messages_to_records(messages) if key is not None else []
        schema_name = response_schema.get("name") if isinstance(response_schema, dict) else None
        try:
            response = await self._inner.generate_structured_response(
                messages=messages,
                response_schema=response_schema,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_output_tokens,
            )
        except Exception as exc:
            if key is not None:
                self._recorder.record_chat_call(
                    key,
                    ChatCallRecord(
                        ordinal=0,
                        purpose="solver" if schema_name == "sql_candidate" else schema_name,
                        schema_name=schema_name if isinstance(schema_name, str) else None,
                        model_name_requested=model_name,
                        reasoning_effort=reasoning_effort,
                        max_output_tokens=max_output_tokens,
                        messages=prompt_records,
                        prompt_hash=sha256_json(
                            [m.model_dump() for m in prompt_records]
                        ),
                        error_class=type(exc).__name__,
                        error_message=str(exc),
                    ),
                )
            raise

        if key is not None:
            raw_output = copy.deepcopy(response.content)
            extracted_sql = raw_output.get("sql") if isinstance(raw_output, dict) else None
            self._recorder.record_chat_call(
                key,
                ChatCallRecord(
                    ordinal=0,
                    purpose="solver" if schema_name == "sql_candidate" else schema_name,
                    schema_name=schema_name if isinstance(schema_name, str) else None,
                    model_name_requested=model_name,
                    model_name_returned=response.model_name,
                    reasoning_effort=reasoning_effort,
                    max_output_tokens=max_output_tokens,
                    messages=prompt_records,
                    prompt_hash=sha256_json([m.model_dump() for m in prompt_records]),
                    raw_model_output=raw_output if isinstance(raw_output, dict) else None,
                    raw_model_output_hash=(
                        sha256_json(raw_output) if isinstance(raw_output, dict) else None
                    ),
                    extracted_sql=(
                        str(extracted_sql).strip()
                        if isinstance(extracted_sql, str) and extracted_sql.strip()
                        else None
                    ),
                    prompt_tokens=response.prompt_tokens,
                    output_tokens=response.output_tokens,
                    elapsed_ms=response.elapsed_ms,
                ),
            )
        return response


def _grounding_capture(
    grounding_context: GroundingContext, serialized_schema: str
) -> GroundingCaptureRecord:
    selected_columns: list[str] = []
    selected_relationships: list[dict[str, Any]] = []
    for table in grounding_context.tables:
        for column in table.columns:
            selected_columns.append(f"{table.fqn}.{column.name}")
        for relationship in table.relationships:
            selected_relationships.append(
                {
                    "type": relationship.relationship_type,
                    "from_fqn": relationship.from_table_fqn,
                    "from_columns": list(relationship.from_columns),
                    "to_fqn": relationship.to_table_fqn,
                    "to_columns": list(relationship.to_columns),
                }
            )
    return GroundingCaptureRecord(
        ordinal=0,
        selected_tables=[table.fqn for table in grounding_context.tables],
        selected_columns=selected_columns,
        selected_relationships=selected_relationships,
        glossary_terms=[hit.term for hit in grounding_context.glossary_hits],
        value_binding_columns=sorted(
            {binding.column_fqn for binding in grounding_context.value_bindings}
        ),
        example_count=len(grounding_context.examples),
        unresolved_codes=[issue.code for issue in grounding_context.unresolved],
        serialized_authorized_schema=serialized_schema,
        serialized_context_hash=sha256_text(serialized_schema),
    )


def recording_schema_serializer(
    recorder: CaseEvidenceRecorder,
) -> Callable[[GroundingContext], str]:
    """Return a schema serializer that records grounding, byte-identically.

    It delegates to :meth:`DirectSqlPromptBuilder._format_authorized_schema`, a
    pure function of the grounding context, so the returned string is identical
    to the default serialization and the prompt is unchanged (E04 §4).
    """

    default_builder = DirectSqlPromptBuilder()

    def _serialize(grounding_context: GroundingContext) -> str:
        serialized = default_builder._format_authorized_schema(grounding_context)
        key = _active_case_key.get()
        if key is not None:
            recorder.record_grounding(key, _grounding_capture(grounding_context, serialized))
        return serialized

    return _serialize
