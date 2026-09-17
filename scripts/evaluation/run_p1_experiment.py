"""Run the P1 Context & Serialization Causal Experiment.

Controls context volume (P1A: C0, C1, C2) and serialization formatting (P1B: S0, S1, S2, S3)
while strictly freezing model, prompt, provider, scorer, and runtime policies.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import shutil
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
from t2s.benchmark.scoring import (
    compute_result_fingerprint,
    execute_gold_sql,
    score_execution_accuracy,
)
from t2s.bootstrap.runtime_factory import build_semantic_runtime_profile
from t2s.configuration import Settings
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.runtime import RuntimeStatus, TextToSqlRuntime
from t2s.runtime.context_experiment_profile import resolve_grounding_budget_for_arm
from t2s.runtime.runtime_profile import SemanticRuntimeProfile
from t2s.security import UserIdentity
from t2s.solver.context_serializer import get_schema_serializer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results" / "context_serialization_experiment"
B0_RESULTS_ROOT = PROJECT_ROOT / "results" / "post_p0_baseline"
RUNTIME_MANIFEST_PATH = (
    PROJECT_ROOT / "results" / "runtime_parity" / "effective_runtime_manifest.json"
)
DATASET_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_eval_v1.jsonl"
PILOT_DATASET_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_pilot_v1.jsonl"
DATABASE_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run P1 Context & Serialization Causal Experiment."
    )
    parser.add_argument(
        "--phase",
        choices=["P1A", "P1B", "all"],
        default="P1A",
        help="Experiment phase to run.",
    )
    parser.add_argument(
        "--arms",
        nargs="*",
        default=None,
        help="Specific arms to run (e.g. C0 C1 C2 or S0 S1 S2 S3).",
    )
    parser.add_argument("--replicate-count", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--use-b0-for-control", action="store_true", default=True)
    args = parser.parse_args()

    runtime_manifest = _load_runtime_manifest()
    settings = Settings()
    profile = build_semantic_runtime_profile(settings)
    _validate_effective_profile(runtime_manifest, profile)
    cases = load_benchmark_cases(DATASET_PATH, BenchmarkCaseFilter())
    _validate_dataset(cases)

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    experiment_manifest = _build_experiment_manifest(runtime_manifest, profile, cases)
    _write_json(RESULTS_ROOT / "experiment_manifest.json", experiment_manifest)

    if args.phase in ("P1A", "all"):
        arms = args.arms or ["C0", "C1", "C2"]
        _run_p1a_context_selection(
            arms=arms,
            replicate_count=args.replicate_count,
            concurrency=args.concurrency,
            settings=settings,
            profile=profile,
            cases=cases,
            use_b0_for_control=args.use_b0_for_control,
        )

    if args.phase in ("P1B", "all"):
        arms = args.arms or ["S0", "S1", "S2", "S3"]
        _run_p1b_serialization(
            arms=arms,
            replicate_count=args.replicate_count,
            concurrency=args.concurrency,
            settings=settings,
            profile=profile,
            cases=cases,
            use_b0_for_control=args.use_b0_for_control,
        )

    _generate_aggregate_analyses()


def _run_p1a_context_selection(
    arms: list[str],
    replicate_count: int,
    concurrency: int,
    settings: Settings,
    profile: SemanticRuntimeProfile,
    cases: list[Any],
    use_b0_for_control: bool,
) -> None:
    p1a_root = RESULTS_ROOT / "context_selection"
    p1a_root.mkdir(parents=True, exist_ok=True)

    for arm in arms:
        arm_dir = p1a_root / arm
        if arm == "C0" and use_b0_for_control and B0_RESULTS_ROOT.exists():
            _populate_control_from_b0(arm_dir, "context_selection", "C0", replicate_count)
            continue

        arm_budget = resolve_grounding_budget_for_arm(arm)  # type: ignore[arg-type]
        arm_profile = profile.model_copy(update={"grounding_budget": arm_budget})

        for rep_idx in range(1, replicate_count + 1):
            rep_id = f"replicate_{rep_idx:02d}"
            rep_dir = arm_dir / rep_id
            if rep_dir.exists() and (rep_dir / "metrics.json").exists():
                print(f"[P1A] {arm}/{rep_id} already completed, skipping.", flush=True)
                continue
            if rep_dir.exists():
                shutil.rmtree(rep_dir)
            asyncio.run(
                _run_replicate(
                    replicate_dir=rep_dir,
                    experiment_family="context_selection",
                    arm=arm,
                    replicate_id=rep_id,
                    settings=settings,
                    profile=arm_profile,
                    cases=cases,
                    schema_serializer=None,
                    concurrency=concurrency,
                )
            )


def _run_p1b_serialization(
    arms: list[str],
    replicate_count: int,
    concurrency: int,
    settings: Settings,
    profile: SemanticRuntimeProfile,
    cases: list[Any],
    use_b0_for_control: bool,
) -> None:
    p1b_root = RESULTS_ROOT / "serialization"
    p1b_root.mkdir(parents=True, exist_ok=True)

    for arm in arms:
        arm_dir = p1b_root / arm
        if arm == "S0" and use_b0_for_control and B0_RESULTS_ROOT.exists():
            _populate_control_from_b0(arm_dir, "serialization", "S0", replicate_count)
            continue

        serializer = get_schema_serializer(arm)  # type: ignore[arg-type]
        for rep_idx in range(1, replicate_count + 1):
            rep_id = f"replicate_{rep_idx:02d}"
            rep_dir = arm_dir / rep_id
            if rep_dir.exists() and (rep_dir / "metrics.json").exists():
                print(f"[P1B] {arm}/{rep_id} already completed, skipping.", flush=True)
                continue
            if rep_dir.exists():
                shutil.rmtree(rep_dir)
            asyncio.run(
                _run_replicate(
                    replicate_dir=rep_dir,
                    experiment_family="serialization",
                    arm=arm,
                    replicate_id=rep_id,
                    settings=settings,
                    profile=profile,
                    cases=cases,
                    schema_serializer=serializer,
                    concurrency=concurrency,
                )
            )


def _populate_control_from_b0(
    target_arm_dir: Path,
    family: str,
    arm: str,
    replicate_count: int,
) -> None:
    print(f"[{family}] Initializing {arm} from frozen B0 baseline records...", flush=True)
    target_arm_dir.mkdir(parents=True, exist_ok=True)
    for rep_idx in range(1, replicate_count + 1):
        rep_id = f"replicate_{rep_idx:02d}"
        src_rep = B0_RESULTS_ROOT / rep_id
        dst_rep = target_arm_dir / rep_id
        if dst_rep.exists():
            continue
        dst_rep.mkdir(parents=True, exist_ok=True)
        # Adapt cases.jsonl into standardized P1 format
        cases_in = src_rep / "cases.jsonl"
        cases_out = dst_rep / "cases.jsonl"
        for line in cases_in.read_text().splitlines():
            raw = json.loads(line)
            record = _standardize_case_record(raw, family, arm, rep_idx)
            _append_jsonl(cases_out, record)
        if (src_rep / "metrics.json").exists():
            shutil.copy(src_rep / "metrics.json", dst_rep / "metrics.json")
        if (src_rep / "manifest.json").exists():
            shutil.copy(src_rep / "manifest.json", dst_rep / "manifest.json")


def _standardize_case_record(
    raw: dict[str, Any],
    family: str,
    arm: str,
    replicate_idx: int,
) -> dict[str, Any]:
    grounding = raw.get("grounding", {})
    return {
        "case_id": raw["case_id"],
        "experiment_family": family,
        "arm": arm,
        "replicate": replicate_idx,
        "runtime_status": raw.get("runtime_status"),
        # V2-P00R §5: persist the raw candidate SQL so semantic (A-F) audits
        # can reconstruct inference. The boolean flag is retained for backward
        # compatibility with existing aggregate readers.
        "generated_sql": raw.get("generated_sql"),
        "generated_sql_present": raw.get("generated_sql_present", False),
        "rejected_candidate_sql": raw.get("rejected_candidate_sql"),
        "candidate_assumptions": list(raw.get("candidate_assumptions", [])),
        "candidate_result_fingerprint": raw.get("candidate_result_fingerprint"),
        "gold_result_fingerprint": raw.get("gold_result_fingerprint"),
        "execution_success": raw.get("execution_success", False),
        "execution_correct": raw.get("execution_correct"),
        "context": {
            "candidate_tables": grounding.get("candidate_table_count", 0),
            "selected_tables": grounding.get("hydrated_table_count", 0),
            "selected_columns": grounding.get("selected_column_count", 0),
            "relationships": grounding.get("relationship_count", 0),
            "serialized_chars": grounding.get("serialized_context_chars", 0),
            "prompt_tokens": None,
        },
        "solver": {
            "call_count": raw.get("solver", {}).get("call_count", 0),
        },
        "verifier": {
            "invoked": raw.get("verifier", {}).get("invoked", False),
            "flagged": raw.get("verifier", {}).get("flagged", False),
        },
        "latency_ms": raw.get("latency_ms", {}).get("total", 0.0),
        "error_category": raw.get("error", {}).get("category"),
    }


async def _run_replicate(
    replicate_dir: Path,
    experiment_family: str,
    arm: str,
    replicate_id: str,
    settings: Settings,
    profile: SemanticRuntimeProfile,
    cases: list[Any],
    schema_serializer: Any,
    concurrency: int = 3,
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
            tables_json_path=_require(
                settings.runtime_catalog_tables_path, "runtime_catalog_tables_path"
            ),
            chat_client=client,
            model_name=profile.model_name,
            prompt_directory=settings.runtime_prompt_directory,
            runtime_profile=profile,
            schema_serializer=schema_serializer,
        )
        _observe_grounding(runtime, observations)
        runtimes[db_id] = runtime

    cases_path = replicate_dir / "cases.jsonl"
    replicate_num = int(replicate_id.split("_")[-1])
    sem = asyncio.Semaphore(concurrency)
    progress_counter = 0

    async def _execute_case_bound(index: int, case: Any) -> tuple[int, dict[str, Any]]:
        nonlocal progress_counter
        async with sem:
            raw_record = await _run_case(
                case, runtimes[case.inference_case.db_id], observations, f"{arm}_{replicate_id}"
            )
            record = _standardize_case_record(raw_record, experiment_family, arm, replicate_num)
            progress_counter += 1
            cid = case.inference_case.case_id
            print(f"[{arm}] {replicate_id}: {progress_counter}/{len(cases)} {cid}", flush=True)
            return index, record

    tasks = [_execute_case_bound(index, case) for index, case in enumerate(cases, start=1)]
    completed = await asyncio.gather(*tasks)
    completed.sort(key=lambda item: item[0])
    records = [record for _, record in completed]

    for record in records:
        _append_jsonl(cases_path, record)

    _write_json(replicate_dir / "metrics.json", _replicate_metrics(records))
    _write_json(
        replicate_dir / "manifest.json",
        {
            "experiment_family": experiment_family,
            "arm": arm,
            "replicate_id": replicate_id,
            "started_at": datetime.now(UTC).isoformat(),
        },
    )


def _observe_grounding(
    runtime: TextToSqlRuntime, observations: dict[str, dict[str, Any]]
) -> None:
    orchestrator = runtime.adaptive_orchestrator
    original_run = orchestrator.run

    async def observed_run(**kwargs: Any) -> Any:
        result = await original_run(**kwargs)
        context = result.grounding_context
        prompt_builder = orchestrator.solver.prompt_builder
        schema_text = (
            prompt_builder.schema_serializer(context)
            if prompt_builder.schema_serializer is not None
            else prompt_builder._format_authorized_schema(context)
        )
        observations[str(kwargs["run_id"])] = {
            "candidate_table_count": len(context.tables),
            "hydrated_table_count": len(context.tables),
            "selected_column_count": sum(len(table.columns) for table in context.tables),
            "selected_columns_per_table": {
                table.fqn: len(table.columns) for table in context.tables
            },
            "relationship_count": sum(len(table.relationships) for table in context.tables),
            "fallback_mode": None,
            "serialized_context_chars": len(schema_text),
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

    # Inference-before-gold ordering (V2-P00R §7): finalize every inference
    # artifact off the runtime result first, then load gold and compute its
    # fingerprint. Gold never re-enters inference.
    generated_sql = result.sql
    rejected_candidate = result.trace.rejected_candidate if result.trace is not None else None
    rejected_sql = rejected_candidate.sql if rejected_candidate is not None else None
    candidate_assumptions = (
        result.trace.candidate_assumptions if result.trace is not None else []
    )
    candidate_result_fingerprint: str | None = (
        compute_result_fingerprint(result.rows)
        if result.status == RuntimeStatus.COMPLETED
        else None
    )

    gold_ok = False
    correct: bool | None = None
    gold_result_fingerprint: str | None = None
    if result.status == RuntimeStatus.COMPLETED and case.scoring_gold.official_sql is not None:
        gold = execute_gold_sql(
            case.scoring_gold.official_sql,
            resolve_official_database_path(DATABASE_ROOT, inference.db_id),
        )
        gold_ok = gold.ok
        if gold.ok:
            gold_result_fingerprint = compute_result_fingerprint(gold.rows)
            correct = score_execution_accuracy(
                result.rows, gold.rows, case.scoring_gold.official_sql
            )
    trace = result.trace.orchestration_trace
    verifier = result.result_verification_outcome
    observation = observations.get(run_id, _empty_context())
    return {
        "case_id": inference.case_id,
        "replicate_id": replicate_id,
        "runtime_status": result.status.value.upper(),
        "generated_sql_present": generated_sql is not None,
        "generated_sql": generated_sql,
        "rejected_candidate_sql": rejected_sql,
        "candidate_assumptions": list(candidate_assumptions),
        "candidate_result_fingerprint": candidate_result_fingerprint,
        "gold_result_fingerprint": gold_result_fingerprint,
        "execution_attempted": result.status == RuntimeStatus.COMPLETED,
        "execution_success": result.trace.execution_passed,
        "execution_correct": correct,
        "gold_execution_success": gold_ok,
        "latency_ms": {
            "total": result.total_latency_ms,
            "execution": result.execution_time_ms,
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
        },
        "error": {
            "category": _error_category(result.status.value, result.error_message),
            "provider_status": None,
        },
    }


def _failure_record(
    case: Any, replicate_id: str, started: datetime, exc: Exception
) -> dict[str, Any]:
    return {
        "case_id": case.inference_case.case_id,
        "replicate_id": replicate_id,
        "runtime_status": "GENERATION_FAILED",
        "generated_sql_present": False,
        "generated_sql": None,
        "rejected_candidate_sql": None,
        "candidate_assumptions": [],
        "candidate_result_fingerprint": None,
        "gold_result_fingerprint": None,
        "execution_attempted": False,
        "execution_success": False,
        "execution_correct": None,
        "gold_execution_success": False,
        "latency_ms": {"total": (datetime.now(UTC) - started).total_seconds() * 1000},
        "solver": {"call_count": 0, "generation_failed": True},
        "grounding": _empty_context(),
        "verifier": {"invoked": False, "decision": None, "flagged": False},
        "error": {
            "category": _error_category(type(exc).__name__, str(exc)),
            "provider_status": None,
        },
    }


def _empty_context() -> dict[str, Any]:
    return {
        "candidate_table_count": 0,
        "hydrated_table_count": 0,
        "selected_column_count": 0,
        "selected_columns_per_table": {},
        "relationship_count": 0,
        "fallback_mode": None,
        "serialized_context_chars": 0,
    }


def _replicate_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    latencies = [float(record["latency_ms"]) for record in records]
    verifier_records = [record for record in records if record["verifier"]["invoked"]]
    return {
        "case_count": total,
        "execution_accuracy": _ratio(
            sum(r["execution_correct"] is True for r in records), total
        ),
        "sql_produced_rate": _ratio(sum(r["generated_sql_present"] for r in records), total),
        "execution_success_rate": _ratio(sum(r["execution_success"] for r in records), total),
        "generation_failure_rate": _ratio(
            sum(r["runtime_status"] == "GENERATION_FAILED" for r in records), total
        ),
        "median_latency_ms": median(latencies) if latencies else 0.0,
        "mean_llm_calls": mean(r["solver"]["call_count"] for r in records) if records else 0.0,
        "result_verifier": {
            "invocation_count": len(verifier_records),
            "flag_count": sum(r["verifier"]["flagged"] for r in records),
        },
        "context": {
            "candidate_table_count": mean(r["context"]["candidate_tables"] for r in records),
            "selected_column_count": mean(r["context"]["selected_columns"] for r in records),
            "relationship_count": mean(r["context"]["relationships"] for r in records),
            "serialized_context_chars": mean(r["context"]["serialized_chars"] for r in records),
        },
    }


def _generate_aggregate_analyses() -> None:
    _compute_family_metrics("context_selection", RESULTS_ROOT / "context_metrics.json")
    _compute_family_metrics("serialization", RESULTS_ROOT / "serialization_metrics.json")
    _compute_pairwise_mcnemar()
    _compute_stability_analysis()


def _compute_family_metrics(family: str, out_path: Path) -> None:
    family_dir = RESULTS_ROOT / family
    if not family_dir.exists():
        return
    results: dict[str, Any] = {}
    for arm_dir in sorted(family_dir.iterdir()):
        if not arm_dir.is_dir():
            continue
        arm_name = arm_dir.name
        replicate_metrics = []
        for rep_dir in sorted(arm_dir.iterdir()):
            m_path = rep_dir / "metrics.json"
            if m_path.exists():
                replicate_metrics.append(json.loads(m_path.read_text()))
        if replicate_metrics:
            accuracies = [m["execution_accuracy"] for m in replicate_metrics]
            chars = [m["context"]["serialized_context_chars"] for m in replicate_metrics]
            results[arm_name] = {
                "replicate_count": len(replicate_metrics),
                "replicate_accuracies": accuracies,
                "mean_execution_accuracy": mean(accuracies),
                "accuracy_range": [min(accuracies), max(accuracies)],
                "mean_serialized_chars": mean(chars),
                "mean_latency_ms": mean(m["median_latency_ms"] for m in replicate_metrics),
            }
    _write_json(out_path, results)


def _compute_pairwise_mcnemar() -> None:
    pairwise: dict[str, Any] = {}
    # Compare C0 vs C1, C0 vs C2
    c_root = RESULTS_ROOT / "context_selection"
    if (c_root / "C0").exists():
        for treatment in ("C1", "C2"):
            if (c_root / treatment).exists():
                pairwise[f"C0_vs_{treatment}"] = _mcnemar_pair(c_root / "C0", c_root / treatment)

    # Compare S0 vs S1, S0 vs S2, S0 vs S3
    s_root = RESULTS_ROOT / "serialization"
    if (s_root / "S0").exists():
        for treatment in ("S1", "S2", "S3"):
            if (s_root / treatment).exists():
                pairwise[f"S0_vs_{treatment}"] = _mcnemar_pair(s_root / "S0", s_root / treatment)

    _write_json(RESULTS_ROOT / "pairwise_analysis.json", pairwise)


def _mcnemar_pair(control_dir: Path, treatment_dir: Path) -> dict[str, Any]:
    # Aggregated over all available matching replicates
    control_cases = _load_arm_replicates(control_dir)
    treatment_cases = _load_arm_replicates(treatment_dir)

    both_correct = 0
    both_incorrect = 0
    control_only = 0
    treatment_only = 0

    for key, c_correct in control_cases.items():
        if key in treatment_cases:
            t_correct = treatment_cases[key]
            if c_correct and t_correct:
                both_correct += 1
            elif not c_correct and not t_correct:
                both_incorrect += 1
            elif c_correct and not t_correct:
                control_only += 1
            elif not c_correct and t_correct:
                treatment_only += 1

    b = control_only
    c = treatment_only
    n_pairs = both_correct + both_incorrect + b + c
    p_value = _exact_mcnemar_p_value(b, c)
    abs_delta = (c - b) / n_pairs if n_pairs else 0.0

    return {
        "total_pairs": n_pairs,
        "contingency_table": {
            "both_correct": both_correct,
            "both_incorrect": both_incorrect,
            "control_only_correct": b,
            "treatment_only_correct": c,
        },
        "discordant_b": b,
        "discordant_c": c,
        "p_value": p_value,
        "absolute_delta": abs_delta,
    }


def _load_arm_replicates(arm_dir: Path) -> dict[tuple[str, int], bool]:
    outcomes: dict[tuple[str, int], bool] = {}
    for rep_dir in sorted(arm_dir.iterdir()):
        if not rep_dir.is_dir():
            continue
        c_path = rep_dir / "cases.jsonl"
        if c_path.exists():
            for line in c_path.read_text().splitlines():
                rec = json.loads(line)
                outcomes[(rec["case_id"], rec["replicate"])] = bool(rec["execution_correct"])
    return outcomes


def _exact_mcnemar_p_value(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    prob_tail = sum(math.comb(n, i) * (0.5**n) for i in range(k + 1))
    return min(1.0, 2.0 * prob_tail)


def _compute_stability_analysis() -> None:
    # Aggregates stability counts across all present arms
    stability: dict[str, Any] = {}
    for family in ("context_selection", "serialization"):
        f_dir = RESULTS_ROOT / family
        if not f_dir.exists():
            continue
        for arm_dir in sorted(f_dir.iterdir()):
            if not arm_dir.is_dir():
                continue
            records_by_case: dict[str, list[dict[str, Any]]] = {}
            for rep_dir in sorted(arm_dir.iterdir()):
                c_path = rep_dir / "cases.jsonl"
                if c_path.exists():
                    for line in c_path.read_text().splitlines():
                        rec = json.loads(line)
                        records_by_case.setdefault(rec["case_id"], []).append(rec)
            case_classifications = []
            for case_id, recs in sorted(records_by_case.items()):
                outcomes = [r["execution_correct"] for r in recs]
                label = (
                    "STABLE_CORRECT"
                    if all(outcomes)
                    else "STABLE_INCORRECT"
                    if not any(outcomes)
                    else "UNSTABLE"
                )
                case_classifications.append(
                    {
                        "case_id": case_id,
                        "pass_count": sum(value is True for value in outcomes),
                        "total_replicates": len(recs),
                        "classification": label,
                    }
                )
            stability[f"{family}_{arm_dir.name}"] = {
                "case_count": len(case_classifications),
                "counts": dict(Counter(c["classification"] for c in case_classifications)),
            }
    _write_json(RESULTS_ROOT / "stability_analysis.json", stability)


def _load_runtime_manifest() -> dict[str, Any]:
    manifest = json.loads(RUNTIME_MANIFEST_PATH.read_text())
    if (
        manifest.get("parity", {}).get("status") != "PASS"
        or manifest.get("parity", {}).get("semantic_differences")
    ):
        raise RuntimeError("BLOCKED_RUNTIME_PARITY")
    return manifest


def _validate_effective_profile(manifest: dict[str, Any], profile: Any) -> None:
    solver = manifest["profiles"]["api"]["solver"]
    if (
        solver["model"] != profile.model_name
        or solver["temperature"] != profile.temperature
    ):
        raise RuntimeError(
            "BLOCKED_RUNTIME_PARITY: Settings disagree with effective manifest"
        )


def _validate_dataset(cases: list[Any]) -> None:
    verify_eval_v1_invariants(DATASET_PATH, PILOT_DATASET_PATH, DATABASE_ROOT)
    if len(cases) != 100 or any(case.scoring_gold.official_sql is None for case in cases):
        raise RuntimeError(
            "Dataset is not the governed 100-case executable evaluation population."
        )


def _build_experiment_manifest(
    manifest: dict[str, Any], profile: Any, cases: list[Any]
) -> dict[str, Any]:
    api = manifest["profiles"]["api"]
    return {
        "experiment_id": "context_serialization_causal_experiment",
        "git_commit": _git(["rev-parse", "HEAD"]),
        "git_dirty": bool(_git(["status", "--porcelain"])),
        "runtime_manifest_sha256": manifest["manifest_sha256"],
        "dataset_path": str(DATASET_PATH),
        "dataset_sha256": _sha256(DATASET_PATH),
        "total_cases": len(cases),
        "provider": api["solver"]["provider"],
        "model": api["solver"]["model"],
        "temperature": api["solver"]["temperature"],
        "seed_policy": api["solver"]["seed_policy"],
        "retry_policy": api["solver"]["retry_policy"],
        "timeout_policy": api["solver"]["request_timeout_seconds"],
        "prompt_version": api["solver"]["prompt_version"],
        "prompt_hashes": {
            "system": api["solver"]["system_prompt_hash"],
            "user_template": api["solver"]["user_template_hash"],
        },
        "evidence_mode": api["solver"]["evidence_mode"],
        "planner_mode": api["policies"]["planner_mode"],
        "result_verifier_mode": api["policies"]["result_verifier_mode"],
        "value_linking_mode": api["grounding"]["value_linking_mode"],
        "validator_mode": api["policies"]["validator_mode"],
        "replicate_count": 3,
    }


def _error_category(status: str, message: str | None) -> str | None:
    text = f"{status} {message or ''}".upper()
    for category in (
        "TIMEOUT",
        "RATE_LIMIT",
        "MALFORMED_OUTPUT",
        "DEPENDENCY_ERROR",
        "NETWORK_ERROR",
    ):
        if category in text:
            return category
    if status == RuntimeStatus.COMPLETED.value:
        return "SQL_INCORRECT"
    return "UNKNOWN_PROVIDER_ERROR" if message else None


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


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
