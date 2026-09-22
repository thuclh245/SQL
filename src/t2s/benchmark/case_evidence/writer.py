"""Artifact writer for the canonical evidence tree (E04 §11).

Layout::

    <evidence_root>/<experiment_id>/
        experiment_manifest.json
        case_records.jsonl            # one full CaseRunRecord per line (E05 feed)
        cases/<case_id>/<replicate_id>/
            input.json
            grounding.json
            prompt.json
            generation.json
            validation.json
            execution.json
            evidence_manifest.json     # full CaseRunRecord + hash index

The split files are human/audit projections; ``evidence_manifest.json`` holds the
complete record and is the single source of truth for replay.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from t2s.benchmark.case_evidence.contract import CaseRunRecord


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def case_directory(
    evidence_root: Path, experiment_id: str, case_id: str, replicate_id: str
) -> Path:
    return evidence_root / experiment_id / "cases" / case_id / replicate_id


def hash_index(record: CaseRunRecord) -> dict[str, str | None]:
    """Compact index of the content hashes stored for a record (E04 §18)."""

    return {
        "solver_prompt_hash": record.solver_prompt_hash,
        "grounded_context_hash": record.grounded_context_hash,
        "candidate_sql_hash": record.candidate_sql_hash,
        "raw_model_output_hash": record.raw_model_output_hash,
        "grounding_config_hash": record.grounding_config_hash,
    }


def write_case_record(
    evidence_root: Path,
    record: CaseRunRecord,
) -> Path:
    """Write the split projections + full manifest for one record.

    Returns the case/replicate directory.
    """

    directory = case_directory(
        evidence_root, record.experiment_id, record.case_id, record.replicate_id
    )
    directory.mkdir(parents=True, exist_ok=True)

    _write_json(
        directory / "input.json",
        {
            "experiment_id": record.experiment_id,
            "run_id": record.run_id,
            "replicate_id": record.replicate_id,
            "case_id": record.case_id,
            "db_id": record.db_id,
            "question": record.question,
            "dataset_name": record.dataset_name,
            "dataset_split": record.dataset_split,
            "dataset_version_or_hash": record.dataset_version_or_hash,
            "request_id": record.request_id,
            "trace_id": record.trace_id,
            "created_at": record.created_at,
        },
    )
    _write_json(
        directory / "grounding.json",
        {
            "grounding_strategy": record.grounding_strategy,
            "grounding_config_hash": record.grounding_config_hash,
            "selected_tables": record.selected_tables,
            "selected_columns": record.selected_columns,
            "selected_relationships": record.selected_relationships,
            "exact_grounded_context": record.exact_grounded_context,
            "grounded_context_hash": record.grounded_context_hash,
            "grounding_captures": [c.model_dump() for c in record.grounding_captures],
        },
    )
    _write_json(
        directory / "prompt.json",
        {
            "prompt_version": record.prompt_version,
            "exact_solver_prompt": [m.model_dump() for m in record.exact_solver_prompt],
            "solver_prompt_hash": record.solver_prompt_hash,
            "chat_calls": [c.model_dump() for c in record.chat_calls],
        },
    )
    _write_json(
        directory / "generation.json",
        {
            "provider": record.provider,
            "model": record.model,
            "temperature": record.temperature,
            "seed_or_null": record.seed_or_null,
            "retry_policy": record.retry_policy,
            "correction_budget": record.correction_budget,
            "raw_model_output": record.raw_model_output,
            "raw_model_output_hash": record.raw_model_output_hash,
            "candidate_sql": record.candidate_sql,
            "candidate_sql_hash": record.candidate_sql_hash,
            "solver_assumptions": record.solver_assumptions,
            "solver_unresolved_items": record.solver_unresolved_items,
            "generation_outcome": record.generation_outcome.value,
        },
    )
    _write_json(
        directory / "validation.json",
        {
            "validator_mode": record.validator_mode,
            "verifier_mode": record.verifier_mode,
            "ast_summary": record.ast_summary,
            "validation_outputs": record.validation_outputs,
        },
    )
    _write_json(
        directory / "execution.json",
        {
            "execution_attempted": record.execution_attempted,
            "execution_status": record.execution_status,
            "execution_error_class": record.execution_error_class,
            "runtime_status": record.runtime_status,
            "candidate_execution_ok": record.candidate_execution_ok,
            "candidate_result_schema": record.candidate_result_schema,
            "candidate_result_row_count": record.candidate_result_row_count,
            "candidate_result_fingerprint": record.candidate_result_fingerprint,
            "gold_result_fingerprint": record.gold_result_fingerprint,
            "gold_execution_ok": record.gold_execution_ok,
            "latency_breakdown": record.latency_breakdown,
        },
    )
    _write_json(
        directory / "evidence_manifest.json",
        {
            "schema_version": record.schema_version,
            "evidence_completeness": record.evidence_completeness.value,
            "hash_index": hash_index(record),
            "record": record.model_dump(mode="json"),
        },
    )
    return directory


def append_case_record_jsonl(evidence_root: Path, record: CaseRunRecord) -> Path:
    """Append the full record to the experiment-level ``case_records.jsonl``."""

    path = evidence_root / record.experiment_id / "case_records.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path


def write_experiment_manifest(
    evidence_root: Path,
    experiment_id: str,
    manifest: dict[str, Any],
) -> Path:
    """Freeze the experiment configuration (E04 §15)."""

    path = evidence_root / experiment_id / "experiment_manifest.json"
    _write_json(path, manifest)
    return path
