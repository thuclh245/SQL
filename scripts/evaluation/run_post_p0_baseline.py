"""Measure the frozen post-P0 runtime without changing its behavior."""
# ruff: noqa: E501

import argparse
import asyncio
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases
from t2s.benchmark.invariants import (
    resolve_official_database_path,
    verify_eval_v1_invariants,
)
from t2s.benchmark.runtime_factory import (
    build_bird_runtime_for_database,
    build_query_request_from_benchmark_case,
)
from t2s.benchmark.scoring import execute_gold_sql, score_execution_accuracy
from t2s.bootstrap.runtime_factory import build_semantic_runtime_profile
from t2s.configuration import Settings
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.runtime import RuntimeStatus, TextToSqlRuntime
from t2s.security import UserIdentity

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results" / "post_p0_baseline"
RUNTIME_MANIFEST_PATH = PROJECT_ROOT / "results" / "runtime_parity" / "effective_runtime_manifest.json"
DATASET_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_eval_v1.jsonl"
PILOT_DATASET_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_pilot_v1.jsonl"
DATABASE_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen post-P0 control condition.")
    parser.add_argument("--replicate-count", type=int, default=3)
    args = parser.parse_args()
    if args.replicate_count != 3:
        raise ValueError("B0 requires exactly three preregistered baseline replicates.")

    runtime_manifest = _load_runtime_manifest()
    settings = Settings()
    profile = build_semantic_runtime_profile(settings)
    _validate_effective_profile(runtime_manifest, profile)
    cases = load_benchmark_cases(DATASET_PATH, BenchmarkCaseFilter())
    _validate_dataset(cases)
    baseline_manifest = _build_baseline_manifest(runtime_manifest, profile, cases)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    _write_json(RESULTS_ROOT / "baseline_manifest.json", baseline_manifest)

    for index in range(1, args.replicate_count + 1):
        replicate_id = f"replicate_{index:02d}"
        replicate_dir = RESULTS_ROOT / replicate_id
        if replicate_dir.exists():
            raise FileExistsError(f"Refusing to overwrite baseline replicate: {replicate_dir}")
        asyncio.run(_run_replicate(replicate_dir, replicate_id, settings, profile, cases, baseline_manifest))

    _write_aggregate_artifacts(args.replicate_count)


async def _run_replicate(
    replicate_dir: Path,
    replicate_id: str,
    settings: Settings,
    profile: Any,
    cases: list[Any],
    baseline_manifest: dict[str, Any],
) -> None:
    replicate_dir.mkdir(parents=True)
    observations: dict[str, dict[str, Any]] = {}
    runtimes: dict[str, TextToSqlRuntime] = {}
    client = OpenAICompatibleChatClient(
        base_url=_require(settings.vllm_base_url, "vllm_base_url"),
        api_key=settings.llm_api_key,
        request_timeout_seconds=profile.request_timeout_seconds,
        temperature=profile.temperature,
    )
    for case in cases:
        db_id = case.inference_case.db_id
        if db_id in runtimes:
            continue
        runtime = build_bird_runtime_for_database(
            db_id=db_id,
            db_path=resolve_official_database_path(DATABASE_ROOT, db_id),
            tables_json_path=_require(settings.runtime_catalog_tables_path, "runtime_catalog_tables_path"),
            chat_client=client,
            model_name=profile.model_name,
            prompt_directory=settings.runtime_prompt_directory,
            runtime_profile=profile,
        )
        _observe_grounding(runtime, observations)
        runtimes[db_id] = runtime

    cases_path = replicate_dir / "cases.jsonl"
    records: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        record = await _run_case(case, runtimes[case.inference_case.db_id], observations, replicate_id)
        records.append(record)
        _append_jsonl(cases_path, record)
        print(f"{replicate_id}: {index}/{len(cases)} {case.inference_case.case_id}", flush=True)

    _write_json(replicate_dir / "metrics.json", _replicate_metrics(records))
    _write_json(
        replicate_dir / "manifest.json",
        {**baseline_manifest, "replicate_id": replicate_id, "started_at": datetime.now(UTC).isoformat()},
    )


def _observe_grounding(runtime: TextToSqlRuntime, observations: dict[str, dict[str, Any]]) -> None:
    orchestrator = runtime.adaptive_orchestrator
    original_run = orchestrator.run

    async def observed_run(**kwargs: Any) -> Any:
        result = await original_run(**kwargs)
        context = result.grounding_context
        prompt_builder = orchestrator.solver.prompt_builder
        observations[str(kwargs["run_id"])] = {
            "candidate_table_count": len(context.tables),
            "hydrated_table_count": len(context.tables),
            "selected_column_count": sum(len(table.columns) for table in context.tables),
            "selected_columns_per_table": {table.fqn: len(table.columns) for table in context.tables},
            "relationship_count": sum(len(table.relationships) for table in context.tables),
            "fallback_mode": None,
            "serialized_context_chars": len(prompt_builder._format_authorized_schema(context)),
        }
        return result

    orchestrator.run = observed_run


async def _run_case(
    case: Any,
    runtime: TextToSqlRuntime,
    observations: dict[str, dict[str, Any]],
    replicate_id: str,
) -> dict[str, Any]:
    inference = case.inference_case
    run_id = f"{replicate_id}_{inference.case_id}"
    started = datetime.now(UTC)
    try:
        result = await runtime.execute_query_pipeline(
            query_request=build_query_request_from_benchmark_case(
                question=inference.question,
                evidence=inference.evidence,
                evidence_mode="none",
            ),
            user_identity=UserIdentity(user_id="benchmark-runner", tenant_id="t2s"),
            run_id=run_id,
        )
    except Exception as exc:
        return _failure_record(case, replicate_id, started, exc)

    gold_ok = False
    correct: bool | None = None
    if result.status == RuntimeStatus.COMPLETED and case.scoring_gold.official_sql is not None:
        gold = execute_gold_sql(
            case.scoring_gold.official_sql,
            resolve_official_database_path(DATABASE_ROOT, inference.db_id),
        )
        gold_ok = gold.ok
        if gold.ok:
            correct = score_execution_accuracy(result.rows, gold.rows, case.scoring_gold.official_sql)
    trace = result.trace.orchestration_trace
    verifier = result.result_verification_outcome
    observation = observations.get(run_id, _empty_context())
    return {
        "case_id": inference.case_id,
        "replicate_id": replicate_id,
        "runtime_status": result.status.value.upper(),
        "generated_sql_present": result.sql is not None,
        "execution_attempted": result.status == RuntimeStatus.COMPLETED,
        "execution_success": result.trace.execution_passed,
        "execution_correct": correct,
        "gold_execution_success": gold_ok,
        "latency_ms": {
            "total": result.total_latency_ms,
            "grounding": None,
            "solver": None,
            "execution": result.execution_time_ms,
            "verification": None,
        },
        "solver": {
            "call_count": trace.total_solver_calls if trace is not None else 0,
            "generation_failed": result.status == RuntimeStatus.GENERATION_FAILED,
        },
        "grounding": observation,
        "verifier": {
            "invoked": verifier is not None,
            "decision": verifier.decision.value if verifier is not None else None,
            "flagged": verifier.is_suspicious if verifier is not None else False,
            "final_response_altered": verifier.is_suspicious if verifier is not None else False,
        },
        "error": {
            "category": _error_category(result.status.value, result.error_message),
            "provider_status": None,
        },
    }


def _failure_record(case: Any, replicate_id: str, started: datetime, exc: Exception) -> dict[str, Any]:
    return {
        "case_id": case.inference_case.case_id,
        "replicate_id": replicate_id,
        "runtime_status": "GENERATION_FAILED",
        "generated_sql_present": False,
        "execution_attempted": False,
        "execution_success": False,
        "execution_correct": None,
        "gold_execution_success": False,
        "latency_ms": {"total": (datetime.now(UTC) - started).total_seconds() * 1000},
        "solver": {"call_count": 0, "generation_failed": True},
        "grounding": _empty_context(),
        "verifier": {"invoked": False, "decision": None, "flagged": False, "final_response_altered": False},
        "error": {"category": _error_category(type(exc).__name__, str(exc)), "provider_status": None},
    }


def _empty_context() -> dict[str, Any]:
    return {
        "candidate_table_count": 0, "hydrated_table_count": 0, "selected_column_count": 0,
        "selected_columns_per_table": {}, "relationship_count": 0, "fallback_mode": None,
        "serialized_context_chars": 0,
    }


def _replicate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    latencies = [float(record["latency_ms"]["total"]) for record in records]
    verifier_records = [record for record in records if record["verifier"]["invoked"]]
    return {
        "case_count": total,
        "execution_accuracy": _ratio(sum(r["execution_correct"] is True for r in records), total),
        "sql_produced_rate": _ratio(sum(r["generated_sql_present"] for r in records), total),
        "execution_attempt_rate": _ratio(sum(r["execution_attempted"] for r in records), total),
        "execution_success_rate": _ratio(sum(r["execution_success"] for r in records), total),
        "generation_failure_rate": _ratio(sum(r["solver"]["generation_failed"] for r in records), total),
        "median_latency_ms": median(latencies),
        "p90_latency_ms": _percentile(latencies, 0.9),
        "mean_llm_calls": mean(r["solver"]["call_count"] for r in records),
        "result_verifier": {"invocation_count": len(verifier_records), "flag_count": sum(r["verifier"]["flagged"] for r in records)},
        "context": {key: mean(r["grounding"][key] for r in records) for key in ("candidate_table_count", "selected_column_count", "relationship_count", "serialized_context_chars")},
    }


def _write_aggregate_artifacts(replicate_count: int) -> None:
    records_by_case: dict[str, list[dict[str, Any]]] = {}
    metrics: list[dict[str, Any]] = []
    for index in range(1, replicate_count + 1):
        directory = RESULTS_ROOT / f"replicate_{index:02d}"
        metrics.append(json.loads((directory / "metrics.json").read_text()))
        for line in (directory / "cases.jsonl").read_text().splitlines():
            record = json.loads(line)
            records_by_case.setdefault(record["case_id"], []).append(record)
    stability = []
    for case_id, records in sorted(records_by_case.items()):
        outcomes = [record["execution_correct"] for record in records]
        infrastructure = any(record["error"]["category"] not in {None, "SQL_INCORRECT"} for record in records)
        label = "PROVIDER_OR_RUNTIME_FAILURE" if infrastructure else ("STABLE_CORRECT" if all(outcomes) else "STABLE_INCORRECT" if not any(outcomes) else "UNSTABLE")
        stability.append({"case_id": case_id, "pass_count": sum(value is True for value in outcomes), "replicate_count": len(records), "classification": label})
    _write_json(RESULTS_ROOT / "replicate_stability.json", {"cases": stability, "counts": dict(Counter(item["classification"] for item in stability))})
    _write_json(RESULTS_ROOT / "aggregate_metrics.json", {"replicates": metrics, "mean_execution_accuracy": mean(item["execution_accuracy"] for item in metrics), "execution_accuracy_range": [min(item["execution_accuracy"] for item in metrics), max(item["execution_accuracy"] for item in metrics)]})
    _write_json(RESULTS_ROOT / "baseline_summary.json", {"replicate_count": replicate_count, "case_count": len(stability), "stability_counts": dict(Counter(item["classification"] for item in stability))})


def _load_runtime_manifest() -> dict[str, Any]:
    manifest = json.loads(RUNTIME_MANIFEST_PATH.read_text())
    if manifest.get("parity", {}).get("status") != "PASS" or manifest.get("parity", {}).get("semantic_differences"):
        raise RuntimeError("BLOCKED_RUNTIME_PARITY")
    return manifest


def _validate_effective_profile(manifest: dict[str, Any], profile: Any) -> None:
    solver = manifest["profiles"]["api"]["solver"]
    if solver["model"] != profile.model_name or solver["temperature"] != profile.temperature:
        raise RuntimeError("BLOCKED_RUNTIME_PARITY: Settings disagree with effective manifest")


def _validate_dataset(cases: list[Any]) -> None:
    verify_eval_v1_invariants(DATASET_PATH, PILOT_DATASET_PATH, DATABASE_ROOT)
    if len(cases) != 100 or any(case.scoring_gold.official_sql is None for case in cases):
        raise RuntimeError("Dataset is not the governed 100-case executable evaluation population.")


def _build_baseline_manifest(manifest: dict[str, Any], profile: Any, cases: list[Any]) -> dict[str, Any]:
    api = manifest["profiles"]["api"]
    return {
        "baseline_id": "post_p0_baseline", "git_commit": _git(["rev-parse", "HEAD"]), "git_dirty": bool(_git(["status", "--porcelain"])),
        "runtime_manifest_sha256": manifest["manifest_sha256"], "dataset_path": str(DATASET_PATH), "dataset_sha256": _sha256(DATASET_PATH),
        "total_cases": len(cases), "executable_cases": len(cases), "excluded_cases": [],
        "provider": api["solver"]["provider"], "model": api["solver"]["model"], "temperature": api["solver"]["temperature"], "seed_policy": api["solver"]["seed_policy"], "retry_policy": api["solver"]["retry_policy"], "timeout_policy": api["solver"]["request_timeout_seconds"],
        "prompt_version": api["solver"]["prompt_version"], "prompt_hashes": {"system": api["solver"]["system_prompt_hash"], "user_template": api["solver"]["user_template_hash"]},
        "planner_mode": api["policies"]["planner_mode"], "result_verifier_mode": api["policies"]["result_verifier_mode"], "value_linking_mode": api["grounding"]["value_linking_mode"], "grounding_configuration": api["grounding"], "validator_mode": api["policies"]["validator_mode"], "release_policy": api["policies"]["release_candidates_with_caveats"], "escalation_policy": {"max_escalations": api["policies"]["max_escalations"]}, "evidence_mode": api["solver"]["evidence_mode"], "replicate_count": 3,
    }


def _error_category(status: str, message: str | None) -> str | None:
    text = f"{status} {message or ''}".upper()
    for category in ("TIMEOUT", "RATE_LIMIT", "MALFORMED_OUTPUT", "DEPENDENCY_ERROR", "NETWORK_ERROR"):
        if category in text:
            return category
    if status == RuntimeStatus.COMPLETED.value:
        return "SQL_INCORRECT"
    return "UNKNOWN_PROVIDER_ERROR" if message else None


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(quantile * (len(ordered) - 1)))]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _git(args: list[str]) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(value: Any, name: str) -> Any:
    if value is None:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
