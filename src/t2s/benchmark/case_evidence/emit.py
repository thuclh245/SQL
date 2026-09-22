"""Harness-facing helper that turns a completed case into stored evidence.

This binds the recorder, assembler and writer together so entrypoints (the
benchmark runner, the certification script) share one emission path and cannot
drift. It is evaluation-layer glue and never touches runtime behavior.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from t2s.benchmark.case_evidence.assembler import build_case_run_record
from t2s.benchmark.case_evidence.contract import CaseRunRecord
from t2s.benchmark.case_evidence.hashing import sha256_json
from t2s.benchmark.case_evidence.recorder import CaseEvidenceRecorder
from t2s.benchmark.case_evidence.writer import (
    append_case_record_jsonl,
    write_case_record,
    write_experiment_manifest,
)
from t2s.runtime import RuntimeExecutionResult
from t2s.runtime.runtime_profile import SemanticRuntimeProfile


def git_source_provenance(repo_root: Path) -> tuple[str | None, bool | None]:
    """Return (commit, dirty) or (None, None) when git is unavailable."""

    try:
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, stderr=subprocess.DEVNULL
        ).decode()
        return commit, bool(status.strip())
    except (subprocess.SubprocessError, OSError):
        return None, None


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grounding_config_hash(profile: SemanticRuntimeProfile) -> str:
    """Deterministic hash of the grounding-affecting configuration (E04 §15)."""

    return sha256_json(
        {
            "grounding_budget": profile.grounding_budget.model_dump(),
            "escalation_budget": profile.escalation_budget.model_dump(),
            "value_linking_enabled": profile.value_linking_enabled,
            "planner_mode": profile.planner_mode,
            "evidence_mode": profile.evidence_mode,
        }
    )


@dataclass(frozen=True)
class EvidenceEmitter:
    """Emits one :class:`CaseRunRecord` per completed case, then persists it."""

    evidence_root: Path
    experiment_id: str
    run_id: str
    replicate_id: str
    recorder: CaseEvidenceRecorder
    profile: SemanticRuntimeProfile
    provider: str
    dataset_name: str | None
    dataset_split: str | None
    dataset_version_or_hash: str | None
    source_commit: str | None
    source_dirty: bool | None
    grounding_strategy: str
    grounding_config_hash: str
    write_files: bool = True

    def emit(
        self,
        *,
        case_id: str,
        db_id: str | None,
        question: str | None,
        case_run_id: str,
        runtime_result: RuntimeExecutionResult,
        candidate_result_fingerprint: str | None,
        gold_result_fingerprint: str | None,
        gold_execution_ok: bool | None,
        db_path: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> CaseRunRecord:
        evidence = self.recorder.pop(case_run_id)
        record = build_case_run_record(
            experiment_id=self.experiment_id,
            run_id=self.run_id,
            replicate_id=self.replicate_id,
            case_id=case_id,
            db_id=db_id,
            question=question,
            evidence=evidence,
            runtime_result=runtime_result,
            candidate_result_fingerprint=candidate_result_fingerprint,
            gold_result_fingerprint=gold_result_fingerprint,
            gold_execution_ok=gold_execution_ok,
            dataset_name=self.dataset_name,
            dataset_split=self.dataset_split,
            dataset_version_or_hash=self.dataset_version_or_hash,
            source_commit=self.source_commit,
            source_dirty=self.source_dirty,
            grounding_strategy=self.grounding_strategy,
            grounding_config_hash=self.grounding_config_hash,
            prompt_version=self.profile.prompt_version,
            provider=self.provider,
            model=self.profile.model_name,
            temperature=self.profile.temperature,
            seed_or_null=None,
            retry_policy={
                "policy": self.profile.retry_policy,
                "seed_policy": self.profile.seed_policy,
            },
            correction_budget=self.profile.escalation_budget.max_escalations,
            validator_mode=self.profile.validator_mode.value,
            verifier_mode="gate_only" if self.profile.result_verifier_enabled else "off",
            request_id=request_id,
            trace_id=trace_id,
            db_path=db_path,
        )
        if self.write_files:
            write_case_record(self.evidence_root, record)
            append_case_record_jsonl(self.evidence_root, record)
        return record

    def write_manifest(self, extra: dict[str, Any] | None = None) -> Path:
        manifest: dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "replicate_id": self.replicate_id,
            "provider": self.provider,
            "model": self.profile.model_name,
            "temperature": self.profile.temperature,
            "seed_policy": self.profile.seed_policy,
            "retry_policy": self.profile.retry_policy,
            "correction_budget": self.profile.escalation_budget.max_escalations,
            "prompt_version": self.profile.prompt_version,
            "evidence_mode": self.profile.evidence_mode,
            "planner_mode": self.profile.planner_mode,
            "validator_mode": self.profile.validator_mode.value,
            "result_verifier_enabled": self.profile.result_verifier_enabled,
            "value_linking_enabled": self.profile.value_linking_enabled,
            "grounding_strategy": self.grounding_strategy,
            "grounding_config_hash": self.grounding_config_hash,
            "dataset_name": self.dataset_name,
            "dataset_split": self.dataset_split,
            "dataset_version_or_hash": self.dataset_version_or_hash,
            "source_commit": self.source_commit,
            "source_dirty": self.source_dirty,
            "scorer_version_placeholder": None,
        }
        if extra:
            manifest.update(extra)
        return write_experiment_manifest(self.evidence_root, self.experiment_id, manifest)
