"""Read-only case replay and hash-integrity verification (E04 §17, §18).

Replay loads stored evidence and returns the reconstructed record. It is
deliberately inert: it never calls an LLM, never executes SQL, and never mutates
anything. Re-running a case is a separate concern that must create a new run /
replicate identity — it is intentionally not implemented here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from t2s.benchmark.case_evidence.contract import CaseRunRecord
from t2s.benchmark.case_evidence.hashing import sha256_json, sha256_text


def load_case_record(
    evidence_root: Path,
    experiment_id: str,
    case_id: str,
    replicate_id: str,
) -> CaseRunRecord:
    """Load one stored record from its ``evidence_manifest.json`` (no LLM)."""

    manifest_path = (
        evidence_root
        / experiment_id
        / "cases"
        / case_id
        / replicate_id
        / "evidence_manifest.json"
    )
    if not manifest_path.exists():
        raise FileNotFoundError(f"No evidence manifest at {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return CaseRunRecord.model_validate(payload["record"])


def load_experiment_records(evidence_root: Path, experiment_id: str) -> list[CaseRunRecord]:
    """Load every record for an experiment from ``case_records.jsonl`` (no LLM)."""

    path = evidence_root / experiment_id / "case_records.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No case_records.jsonl at {path}")
    records: list[CaseRunRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(CaseRunRecord.model_validate_json(line))
    return records


@dataclass(frozen=True)
class HashCheck:
    field: str
    stored: str | None
    recomputed: str | None

    @property
    def ok(self) -> bool:
        # A hash that was never stored (content absent) is not a corruption.
        if self.stored is None:
            return True
        return self.stored == self.recomputed


def verify_record_hashes(record: CaseRunRecord) -> list[HashCheck]:
    """Recompute every stored content hash and compare (E04 §18).

    A returned check with ``ok is False`` means stored content no longer hashes
    to its stored digest: evidence corruption.
    """

    checks: list[HashCheck] = []

    prompt_recompute = (
        sha256_json([m.model_dump() for m in record.exact_solver_prompt])
        if record.exact_solver_prompt
        else None
    )
    checks.append(HashCheck("solver_prompt_hash", record.solver_prompt_hash, prompt_recompute))

    context_recompute = (
        sha256_text(record.exact_grounded_context)
        if record.exact_grounded_context is not None
        else None
    )
    checks.append(
        HashCheck("grounded_context_hash", record.grounded_context_hash, context_recompute)
    )

    sql_recompute = sha256_text(record.candidate_sql) if record.candidate_sql else None
    checks.append(HashCheck("candidate_sql_hash", record.candidate_sql_hash, sql_recompute))

    raw_recompute = (
        sha256_json(record.raw_model_output) if record.raw_model_output is not None else None
    )
    checks.append(
        HashCheck("raw_model_output_hash", record.raw_model_output_hash, raw_recompute)
    )

    # Per-chat-call prompt + raw-output hashes.
    for call in record.chat_calls:
        call_prompt_recompute = (
            sha256_json([m.model_dump() for m in call.messages]) if call.messages else None
        )
        checks.append(
            HashCheck(
                f"chat_call[{call.ordinal}].prompt_hash",
                call.prompt_hash,
                call_prompt_recompute,
            )
        )
        call_raw_recompute = (
            sha256_json(call.raw_model_output) if call.raw_model_output is not None else None
        )
        checks.append(
            HashCheck(
                f"chat_call[{call.ordinal}].raw_model_output_hash",
                call.raw_model_output_hash,
                call_raw_recompute,
            )
        )

    return checks


def all_hashes_valid(record: CaseRunRecord) -> bool:
    return all(check.ok for check in verify_record_hashes(record))
