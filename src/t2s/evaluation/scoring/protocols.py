"""Minimal stable evidence protocol consumed from E04 (E05 §1, §15).

E04 owns ``CaseRunRecord`` / evidence capture. E05 must *consume* that record
without independently inventing a conflicting case schema. Because the E04
contract may not be final, E05 defines a **minimal stable protocol**
(:class:`CaseRunEvidence`) describing only the fields the scorer needs, plus an
adapter (:func:`case_evidence_from_runner_record`) that builds it from the
current benchmark runner's serialized case dict.

This is deliberately a *consumption interface*, not a duplicated data model: it
is a ``Protocol`` (structural) so any E04 record exposing these attributes is
accepted, and a concrete ``@dataclass`` fallback so E05's own tooling (tests,
synthetic cases, adapters) has something to instantiate.

Missing-evidence policy (E05 §15) is encoded here, not silently: absence of the
candidate SQL, or absence of both result rows and result fingerprints, is
surfaced by :meth:`CaseRunEvidence.determination_blockers`, which the semantic
auditor turns into grade ``F`` rather than a silent exclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from t2s.evaluation.scoring.versions import CONSUMED_CASE_RECORD_PROTOCOL_VERSION


@dataclass(frozen=True)
class ResultTable:
    """A materialized query result: column names plus rows in executor order.

    ``columns`` may be empty when the source only preserved a fingerprint; row
    order and duplicate rows are preserved exactly as returned by the executor,
    matching the fingerprint canonicalization contract in
    :mod:`t2s.benchmark.scoring`.
    """

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]

    @property
    def column_count(self) -> int:
        # Prefer declared column names; fall back to row arity when only rows were
        # captured (a minimal E04 / fingerprint-shaped record carries rows without
        # column names). Empty on both => 0 columns.
        if self.columns:
            return len(self.columns)
        return len(self.rows[0]) if self.rows else 0

    @property
    def row_count(self) -> int:
        return len(self.rows)


@runtime_checkable
class CaseRunEvidence(Protocol):
    """Structural contract for one replicate's stored evidence.

    Any object exposing these attributes (an E04 ``CaseRunRecord``, the dataclass
    fallback below, or an adapter) is a valid scorer input. Optional attributes
    are typed ``| None``; the scorer never fabricates absent evidence.
    """

    # Identity / clustering.
    case_id: str
    replicate_id: str
    db_id: str | None

    # Governed semantic-audit inputs (E05 §11).
    question: str | None
    evidence_context: str | None  # context/evidence delivered to the model
    candidate_sql: str | None
    gold_sql: str | None

    # Execution states.
    runtime_status: str | None
    candidate_execution_ok: bool | None
    gold_execution_ok: bool | None

    # Results (rows when captured, fingerprints always cheap to store).
    candidate_result: ResultTable | None
    gold_result: ResultTable | None
    candidate_fingerprint: str | None
    gold_fingerprint: str | None

    # Optional evaluation-only handle for downstream mutation / alternate-fixture
    # checks. NEVER used to alter runtime behaviour (E05 §3).
    db_path: str | None


@dataclass(frozen=True)
class CaseEvidence:
    """Concrete, instantiable :class:`CaseRunEvidence` (dataclass fallback).

    Used by E05's synthetic tests, adapters and any caller that does not have a
    live E04 record. Field names mirror the protocol exactly.
    """

    case_id: str
    replicate_id: str
    db_id: str | None = None
    question: str | None = None
    evidence_context: str | None = None
    candidate_sql: str | None = None
    gold_sql: str | None = None
    runtime_status: str | None = None
    candidate_execution_ok: bool | None = None
    gold_execution_ok: bool | None = None
    candidate_result: ResultTable | None = None
    gold_result: ResultTable | None = None
    candidate_fingerprint: str | None = None
    gold_fingerprint: str | None = None
    db_path: str | None = None
    #: Free-form provenance carried through for audit views; not scored.
    provenance: dict[str, Any] = field(default_factory=dict)


def determination_blockers(evidence: CaseRunEvidence) -> list[str]:
    """Return reasons a semantic determination is impossible (drives grade F).

    An empty list means enough evidence is present to *attempt* a determination.
    A non-empty list means the case is ``F`` (insufficient evidence), NOT that it
    should be silently dropped (E05 §2, §15).
    """

    blockers: list[str] = []
    if not (evidence.candidate_sql or "").strip():
        blockers.append("candidate_sql_missing")
    have_candidate_result = (
        evidence.candidate_result is not None or evidence.candidate_fingerprint is not None
    )
    have_gold_result = (
        evidence.gold_result is not None or evidence.gold_fingerprint is not None
    )
    if not have_candidate_result:
        blockers.append("candidate_result_missing")
    if not have_gold_result:
        blockers.append("gold_reference_missing")
    return blockers


def case_evidence_from_runner_record(
    record: dict[str, Any],
    *,
    question: str | None = None,
    evidence_context: str | None = None,
    gold_sql: str | None = None,
    replicate_id: str = "r1",
    db_path: str | None = None,
    candidate_result: ResultTable | None = None,
    gold_result: ResultTable | None = None,
) -> CaseEvidence:
    """Adapt the current benchmark runner's case dict into :class:`CaseEvidence`.

    This is the concrete E04-integration path against the *current* stable record
    shape (``t2s.benchmark.runner._serialize_case_result``). When E04 finalizes a
    richer record, only this adapter changes — the scorer consumes the protocol.

    ``question`` / ``gold_sql`` are accepted as explicit arguments because the
    runner record intentionally stores only fingerprints, not gold text or the
    natural-language question (both live in the dataset / case bundle). The
    caller (e.g. :func:`case_evidence_from_bundle_and_record`) supplies them.
    """

    runtime_status = record.get("runtime_status")
    return CaseEvidence(
        case_id=str(record.get("case_id")),
        replicate_id=replicate_id,
        db_id=(str(record["db_id"]) if record.get("db_id") is not None else None),
        question=question,
        evidence_context=evidence_context,
        candidate_sql=record.get("generated_sql"),
        gold_sql=gold_sql,
        runtime_status=runtime_status if isinstance(runtime_status, str) else None,
        candidate_execution_ok=record.get("execution_success"),
        gold_execution_ok=record.get("gold_execution_success"),
        candidate_result=candidate_result,
        gold_result=gold_result,
        candidate_fingerprint=record.get("candidate_result_fingerprint"),
        gold_fingerprint=record.get("gold_result_fingerprint"),
        db_path=db_path,
        provenance={
            "runtime_status": runtime_status,
            "orchestration_outcome": record.get("orchestration_outcome"),
            "execution_correct_runner": record.get("execution_correct"),
            "failure_taxonomy_runner": record.get("failure_taxonomy"),
            "candidate_assumptions": record.get("candidate_assumptions"),
            "consumed_protocol_version": CONSUMED_CASE_RECORD_PROTOCOL_VERSION,
        },
    )
