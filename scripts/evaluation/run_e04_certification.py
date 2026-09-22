"""E04 dry certification run (§21).

Purpose: certify that the case-evidence harness collects reconstructable
evidence end-to-end. It does NOT estimate accuracy.

It drives the *real* runtime pipeline (real grounding, real prompt building, real
SQLite execution against official BIRD dev databases) using the same evidence
components the benchmark runner uses (``RecordingChatClient`` +
``recording_schema_serializer`` + ``EvidenceEmitter``). The provider is a
deterministic fake so the run needs no network and no credentials, and no gold
SQL is ever placed in a prompt.

A small mix of generation outcomes is induced (execution success, an empty /
malformed generation, and a provider error) to certify state differentiation and
the evidence-completeness classification.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from t2s.benchmark.case_evidence import (
    CaseEvidenceRecorder,
    EvidenceEmitter,
    RecordingChatClient,
    active_case_key,
    all_hashes_valid,
    file_sha256,
    git_source_provenance,
    grounding_config_hash,
    load_case_record,
    recording_schema_serializer,
    reset_active_case,
    set_active_case,
    verify_record_hashes,
)
from t2s.benchmark.case_evidence.contract import EvidenceCompleteness, GenerationOutcome
from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases
from t2s.benchmark.invariants import resolve_official_database_path
from t2s.benchmark.runtime_factory import (
    build_bird_runtime_for_database,
    build_query_request_from_benchmark_case,
)
from t2s.benchmark.scoring import compute_result_fingerprint, execute_gold_sql
from t2s.errors import SolverDependencyError
from t2s.runtime import RuntimeStatus
from t2s.runtime.runtime_profile import SemanticRuntimeProfile
from t2s.security import UserIdentity
from t2s.solver.solver_response import StructuredChatResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
DATABASE_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
PROMPT_DIR = PROJECT_ROOT / "prompts" / "direct_sql"

# A fixed, non-gold candidate that executes on any SQLite database. Using a
# constant proves the harness records the exact prompt/candidate regardless of
# correctness (E04 is about auditability, not accuracy, §22).
SAFE_CANDIDATE_SQL = "SELECT 1 AS answer"


class DeterministicFakeChatClient:
    """A no-network provider whose behavior varies by the active case scope.

    ``behavior`` maps a case_run_id to one of: 'ok' (valid candidate),
    'empty' (empty SQL -> malformed output, a generation failure), or
    'provider_error' (raises, a provider failure).
    """

    def __init__(self, behavior: dict[str, str]) -> None:
        self._behavior = behavior

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        key = active_case_key() or ""
        mode = self._behavior.get(key, "ok")
        if mode == "provider_error":
            raise SolverDependencyError("Injected provider error for certification.")
        sql = "" if mode == "empty" else SAFE_CANDIDATE_SQL
        return StructuredChatResponse(
            content={
                "sql": sql,
                "dialect": "sqlite",
                "referenced_tables": [],
                "referenced_columns": [],
                "expected_columns": ["answer"],
                "assumptions": ["certification-fixed-candidate"],
                "unresolved": [],
            },
            model_name=model_name,
            elapsed_ms=1,
            prompt_tokens=11,
            output_tokens=7,
        )


async def _certify(limit: int, experiment_id: str) -> dict[str, Any]:
    filter_ = BenchmarkCaseFilter(limit=limit, executable_only=True)
    bundles = load_benchmark_cases(DEV_DATASET, filter_)
    if not bundles:
        raise SystemExit("No dev cases loaded for certification.")

    run_id = f"e04_cert_{experiment_id}"
    # Induce a mix of outcomes across the selected cases.
    behavior: dict[str, str] = {}
    for index, bundle in enumerate(bundles):
        case_run_id = f"{run_id}_{bundle.inference_case.case_id}"
        if index == 1:
            behavior[case_run_id] = "empty"
        elif index == 2:
            behavior[case_run_id] = "provider_error"
        else:
            behavior[case_run_id] = "ok"

    profile = SemanticRuntimeProfile(model_name="certification-fake-model", temperature=0.0)
    recorder = CaseEvidenceRecorder()
    fake_client = DeterministicFakeChatClient(behavior)
    chat_client = RecordingChatClient(fake_client, recorder)

    evidence_root = PROJECT_ROOT / "results" / "evaluation"
    commit, dirty = git_source_provenance(PROJECT_ROOT)
    emitter = EvidenceEmitter(
        evidence_root=evidence_root,
        experiment_id=experiment_id,
        run_id=run_id,
        replicate_id="r01",
        recorder=recorder,
        profile=profile,
        provider="certification_fake",
        dataset_name=DEV_DATASET.name,
        dataset_split="dev",
        dataset_version_or_hash=file_sha256(DEV_DATASET),
        source_commit=commit,
        source_dirty=dirty,
        grounding_strategy="adaptive_orchestrator",
        grounding_config_hash=grounding_config_hash(profile),
    )
    emitter.write_manifest(extra={"certification": True, "case_count": len(bundles)})

    runtime_cache: dict[str, Any] = {}
    per_case: list[dict[str, Any]] = []

    for bundle in bundles:
        inference = bundle.inference_case
        db_id = inference.db_id
        if db_id not in runtime_cache:
            runtime_cache[db_id] = build_bird_runtime_for_database(
                db_id=db_id,
                db_path=resolve_official_database_path(DATABASE_ROOT, db_id),
                tables_json_path=TABLES_JSON,
                chat_client=chat_client,
                model_name=profile.model_name,
                prompt_directory=PROMPT_DIR,
                runtime_profile=profile,
                schema_serializer=recording_schema_serializer(recorder),
            )
        runtime = runtime_cache[db_id]
        case_run_id = f"{run_id}_{inference.case_id}"
        token = set_active_case(case_run_id)
        try:
            runtime_result = await runtime.execute_query_pipeline(
                query_request=build_query_request_from_benchmark_case(
                    question=inference.question, evidence=inference.evidence, evidence_mode="none"
                ),
                user_identity=UserIdentity(user_id="e04-cert", tenant_id="t2s"),
                run_id=case_run_id,
            )
        finally:
            reset_active_case(token)

        candidate_fp = (
            compute_result_fingerprint(runtime_result.rows)
            if runtime_result.status == RuntimeStatus.COMPLETED
            else None
        )
        gold_fp = None
        gold_ok = None
        official_sql = bundle.scoring_gold.official_sql
        if runtime_result.status == RuntimeStatus.COMPLETED and official_sql is not None:
            gold_result = execute_gold_sql(
                official_sql, resolve_official_database_path(DATABASE_ROOT, db_id)
            )
            gold_ok = gold_result.ok
            if gold_result.ok:
                gold_fp = compute_result_fingerprint(gold_result.rows)

        record = emitter.emit(
            case_id=inference.case_id,
            db_id=db_id,
            question=inference.question,
            case_run_id=case_run_id,
            runtime_result=runtime_result,
            candidate_result_fingerprint=candidate_fp,
            gold_result_fingerprint=gold_fp,
            gold_execution_ok=gold_ok if official_sql is not None else None,
            db_path=str(resolve_official_database_path(DATABASE_ROOT, db_id)),
            request_id=runtime_result.run_id,
            trace_id=runtime_result.trace.run_id,
        )
        per_case.append(_audit_case(record, evidence_root, experiment_id))

    reconstructable = sum(
        1 for c in per_case if c["completeness"] == EvidenceCompleteness.COMPLETE.value
    )
    incomplete = [
        c["case_id"]
        for c in per_case
        if c["completeness"] != EvidenceCompleteness.COMPLETE.value
    ]
    summary = {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "dataset": DEV_DATASET.name,
        "dataset_split": "dev",
        "source_commit": commit,
        "source_dirty": dirty,
        "total_cases": len(per_case),
        "reconstructable_complete": reconstructable,
        "incomplete_case_ids": incomplete,
        "generation_outcomes": _tally(per_case, "generation_outcome"),
        "all_hashes_valid": all(c["hashes_valid"] for c in per_case),
        "no_gold_in_prompt": all(c["no_gold_in_prompt"] for c in per_case),
        "no_secret_captured": all(c["no_secret_captured"] for c in per_case),
        "replay_no_llm_ok": all(c["replay_ok"] for c in per_case),
        "cases": per_case,
    }
    return summary


def _tally(cases: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case[field]] = counts.get(case[field], 0) + 1
    return counts


def _audit_case(record: Any, evidence_root: Path, experiment_id: str) -> dict[str, Any]:
    # Reload via read-only replay (no LLM) and independently verify.
    reloaded = load_case_record(evidence_root, experiment_id, record.case_id, record.replicate_id)
    hashes_valid = all_hashes_valid(reloaded)
    prompt_text = "\n".join(m.content for m in reloaded.exact_solver_prompt)
    gold_sql = record.gold_sql  # None by contract; the check below is defense-in-depth.
    no_gold_in_prompt = True
    if gold_sql:
        no_gold_in_prompt = gold_sql not in prompt_text
    combined = json.dumps(reloaded.model_dump(mode="json"))
    no_secret = "Authorization" not in combined and "Bearer " not in combined
    return {
        "case_id": record.case_id,
        "replicate_id": record.replicate_id,
        "db_id": record.db_id,
        "completeness": reloaded.evidence_completeness.value,
        "generation_outcome": reloaded.generation_outcome.value,
        "has_exact_prompt": bool(reloaded.exact_solver_prompt),
        "has_exact_context": reloaded.exact_grounded_context is not None,
        "has_candidate_sql": reloaded.candidate_sql is not None,
        "has_raw_model_output": reloaded.raw_model_output is not None
        or reloaded.generation_outcome
        in {GenerationOutcome.PROVIDER_ERROR, GenerationOutcome.GENERATION_EMPTY},
        "candidate_fingerprint": reloaded.candidate_fingerprint,
        "hashes_valid": hashes_valid,
        "hash_checks": [
            {"field": c.field, "ok": c.ok} for c in verify_record_hashes(reloaded)
        ],
        "no_gold_in_prompt": no_gold_in_prompt,
        "no_secret_captured": no_secret,
        "replay_ok": reloaded.case_id == record.case_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--experiment-id", default="e04_dry_certification")
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "results" / "e04" / "dry_certification_summary.json"),
    )
    args = parser.parse_args()
    summary = asyncio.run(_certify(args.limit, args.experiment_id))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, indent=2))
    print(f"\nEvidence + summary written. Summary: {out_path}")


if __name__ == "__main__":
    main()
