import argparse
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from t2s.benchmark.artifacts import (
    append_jsonl,
    build_reproducibility_manifest,
    write_json,
    write_summary_markdown,
)
from t2s.benchmark.case_loader import (
    BenchmarkCaseBundle,
    BenchmarkCaseFilter,
    load_benchmark_cases,
)
from t2s.benchmark.invariants import (
    resolve_official_database_path,
    verify_benchmark_database_integrity,
    verify_eval_v1_invariants,
)
from t2s.benchmark.metrics import aggregate_benchmark_metrics
from t2s.benchmark.paths import official_database_root
from t2s.benchmark.runtime_factory import (
    BenchmarkEvidenceMode,
    build_bird_runtime_for_database,
    build_query_request_from_benchmark_case,
)
from t2s.benchmark.scoring import (
    compute_result_fingerprint,
    execute_gold_sql,
    score_execution_accuracy,
)
from t2s.grounding.value_grounding import ValueGroundingBudget
from t2s.integrations.openai_compatible import (
    OpenAICompatibleChatClient,
    describe_provider_request_policy,
)
from t2s.orchestration.escalation_contracts import ValueGroundingTrace
from t2s.runtime import RuntimeExecutionResult, RuntimeStatus, TextToSqlRuntime
from t2s.runtime.runtime_profile import SemanticRuntimeProfile
from t2s.security import UserIdentity

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_eval_v1.jsonl"
DEFAULT_PILOT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_pilot_v1.jsonl"
DEFAULT_DATABASE_ROOT = official_database_root()
DEFAULT_TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
DEFAULT_PROMPT_DIRECTORY = PROJECT_ROOT / "prompts" / "direct_sql"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "results"


async def run_benchmark(args: argparse.Namespace) -> Path:
    provider = args.provider or os.getenv("T2S_LLM_PROVIDER", "openai_compatible")
    if provider != "openai_compatible":
        raise ValueError(f"Unsupported benchmark provider: {provider}")

    model = args.model or os.getenv("T2S_LLM_MODEL")
    base_url = args.base_url or os.getenv("T2S_LLM_BASE_URL")
    api_key = args.api_key or os.getenv("T2S_LLM_API_KEY")
    if not model:
        raise ValueError("Missing model. Set --model or T2S_LLM_MODEL.")
    if not base_url:
        raise ValueError("Missing base URL. Set --base-url or T2S_LLM_BASE_URL.")
    if not api_key:
        raise ValueError("Missing API key. Set --api-key or T2S_LLM_API_KEY.")

    dataset_path = Path(args.dataset)
    database_root = Path(args.database_root)
    if args.verify_invariants:
        verify_eval_v1_invariants(
            eval_dataset_path=dataset_path,
            pilot_dataset_path=Path(args.pilot_dataset),
            database_root=database_root,
        )

    case_filter = BenchmarkCaseFilter(
        limit=args.limit,
        case_ids=frozenset(args.case_id or []),
        db_ids=frozenset(args.db_id or []),
        executable_only=args.executable_only,
    )
    case_bundles = load_benchmark_cases(dataset_path, case_filter)
    if not case_bundles:
        raise ValueError("Benchmark filters selected zero cases.")
    verify_benchmark_database_integrity(
        database_root=database_root,
        db_ids={case.inference_case.db_id for case in case_bundles},
    )

    run_id = args.run_id or _build_run_id()
    output_dir = Path(args.output) / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    chat_client = OpenAICompatibleChatClient(
        base_url=base_url,
        api_key=api_key,
        request_timeout_seconds=args.timeout_seconds,
        temperature=args.temperature,
    )
    value_grounding_budget = (
        ValueGroundingBudget(
            max_value_columns=args.max_value_columns,
            max_value_candidates_per_column=args.max_value_candidates_per_column,
            value_lookup_timeout_ms=args.value_lookup_timeout_ms,
        )
        if args.value_grounding
        else None
    )
    evidence_mode: BenchmarkEvidenceMode = args.evidence_mode
    runtime_profile = SemanticRuntimeProfile(
        provider_identifier=provider,
        model_name=model,
        temperature=args.temperature,
        request_timeout_seconds=args.timeout_seconds,
        prompt_version=args.prompt_version,
        evidence_mode=evidence_mode,
        value_linking_enabled=bool(args.value_grounding),
        release_candidates_with_caveats=not args.strict_abstention,
        planner_mode=args.planner_mode,
        result_verifier_enabled=bool(args.result_verifier),
    )
    runtime_cache: dict[str, TextToSqlRuntime] = {}
    case_results: list[dict[str, Any]] = []
    cases_path = output_dir / "cases.jsonl"
    failures_path = output_dir / "failures.jsonl"

    manifest = build_reproducibility_manifest(
        run_id=run_id,
        dataset_path=dataset_path,
        database_root=database_root,
        provider=provider,
        model=model,
        base_url=base_url,
        prompt_version=args.prompt_version,
        case_ids=[case.inference_case.case_id for case in case_bundles],
        temperature=args.temperature,
        max_tokens=args.max_output_tokens,
        provider_request_policy=describe_provider_request_policy(
            model_name=model,
            requested_temperature=args.temperature,
        ),
    )
    manifest["value_grounding_enabled"] = runtime_profile.value_linking_enabled
    manifest["value_grounding_budget"] = (
        value_grounding_budget.model_dump() if value_grounding_budget is not None else None
    )
    manifest["evidence_mode"] = runtime_profile.evidence_mode
    manifest["release_candidates_with_caveats"] = runtime_profile.release_candidates_with_caveats
    manifest["planner_mode"] = runtime_profile.planner_mode
    manifest["result_verifier_enabled"] = runtime_profile.result_verifier_enabled
    manifest["validator_mode"] = runtime_profile.validator_mode.value
    write_json(output_dir / "manifest.json", manifest)

    for case_bundle in case_bundles:
        db_id = case_bundle.inference_case.db_id
        if db_id not in runtime_cache:
            runtime_cache[db_id] = build_bird_runtime_for_database(
                db_id=db_id,
                db_path=resolve_official_database_path(database_root, db_id),
                tables_json_path=Path(args.tables_json),
                chat_client=chat_client,
                model_name=model,
                prompt_directory=Path(args.prompt_directory),
                prompt_version=args.prompt_version,
                value_grounding_budget=value_grounding_budget,
                release_candidates_with_caveats=not args.strict_abstention,
                runtime_profile=runtime_profile,
            )

    concurrency_limit = max(1, getattr(args, "concurrency", 1))
    semaphore = asyncio.Semaphore(concurrency_limit)
    file_lock = asyncio.Lock()

    async def _process_case(bundle: BenchmarkCaseBundle) -> dict[str, Any]:
        async with semaphore:
            result = await _run_case(
                case_bundle=bundle,
                runtime=runtime_cache[bundle.inference_case.db_id],
                database_root=database_root,
                run_id=run_id,
                evidence_mode=evidence_mode,
            )
            async with file_lock:
                append_jsonl(cases_path, result)
                if result["execution_correct"] is not True:
                    append_jsonl(failures_path, result)
            return result

    case_results = list(await asyncio.gather(*(_process_case(c) for c in case_bundles)))

    metrics = aggregate_benchmark_metrics(case_results)
    write_json(output_dir / "metrics.json", metrics)
    write_summary_markdown(output_dir / "summary.md", metrics, run_id)
    return output_dir


async def _run_case(
    case_bundle: BenchmarkCaseBundle,
    runtime: TextToSqlRuntime,
    database_root: Path,
    run_id: str,
    evidence_mode: BenchmarkEvidenceMode = "none",
) -> dict[str, Any]:
    inference_case = case_bundle.inference_case
    case_run_id = f"{run_id}_{inference_case.case_id}"
    started_at = datetime.now(UTC)
    try:
        runtime_result = await runtime.execute_query_pipeline(
            query_request=build_query_request_from_benchmark_case(
                question=inference_case.question,
                evidence=inference_case.evidence,
                evidence_mode=evidence_mode,
            ),
            user_identity=UserIdentity(user_id="benchmark-runner", tenant_id="t2s"),
            run_id=case_run_id,
        )
    except Exception as exc:
        return _build_infrastructure_failure_result(case_bundle, exc, started_at)

    # Inference-before-gold ordering (V2-P00R §7): compute the candidate result
    # fingerprint from the runtime result before any gold data is loaded.
    candidate_result_fingerprint: str | None = (
        compute_result_fingerprint(runtime_result.rows)
        if runtime_result.status == RuntimeStatus.COMPLETED
        else None
    )

    official_sql = case_bundle.scoring_gold.official_sql
    gold_execution_ok = False
    execution_correct: bool | None = None
    gold_result_fingerprint: str | None = None
    if runtime_result.status == RuntimeStatus.COMPLETED and official_sql is not None:
        gold_result = execute_gold_sql(
            official_sql,
            resolve_official_database_path(database_root, inference_case.db_id),
        )
        gold_execution_ok = gold_result.ok
        if gold_result.ok:
            gold_result_fingerprint = compute_result_fingerprint(gold_result.rows)
            execution_correct = score_execution_accuracy(
                generated_rows=runtime_result.rows,
                gold_rows=gold_result.rows,
                gold_sql=official_sql,
            )

    return _serialize_case_result(
        case_bundle=case_bundle,
        runtime_result=runtime_result,
        execution_correct=execution_correct,
        gold_execution_ok=gold_execution_ok,
        candidate_result_fingerprint=candidate_result_fingerprint,
        gold_result_fingerprint=gold_result_fingerprint,
    )


def _serialize_case_result(
    case_bundle: BenchmarkCaseBundle,
    runtime_result: RuntimeExecutionResult,
    execution_correct: bool | None,
    gold_execution_ok: bool,
    candidate_result_fingerprint: str | None = None,
    gold_result_fingerprint: str | None = None,
) -> dict[str, Any]:
    inference_case = case_bundle.inference_case
    orchestration_trace = runtime_result.trace.orchestration_trace
    escalation_records = (
        orchestration_trace.escalation_records if orchestration_trace is not None else []
    )
    value_grounding_trace = (
        orchestration_trace.value_grounding
        if orchestration_trace is not None
        else ValueGroundingTrace()
    )
    return {
        "case_id": inference_case.case_id,
        "question_id": inference_case.question_id,
        "db_id": inference_case.db_id,
        "runtime_status": _artifact_status(runtime_result.status),
        "generated_sql": runtime_result.sql,
        "orchestration_outcome": (
            runtime_result.orchestration_outcome.value
            if runtime_result.orchestration_outcome is not None
            else None
        ),
        "escalated": bool(escalation_records),
        "same_context_stop": any(
            record.outcome == "context_unchanged" for record in escalation_records
        ),
        "safety_passed": runtime_result.trace.safety_check_passed,
        "access_passed": runtime_result.trace.access_check_passed,
        "execution_success": runtime_result.trace.execution_passed,
        "candidate_result_fingerprint": candidate_result_fingerprint,
        "gold_result_fingerprint": gold_result_fingerprint,
        "gold_execution_success": gold_execution_ok,
        "gold_execution_status": (
            "NOT_APPLICABLE"
            if case_bundle.scoring_gold.official_sql is None
            else (
                "NOT_ATTEMPTED"
                if runtime_result.status != RuntimeStatus.COMPLETED
                else ("SUCCESS" if gold_execution_ok else "FAILED")
            )
        ),
        "verifier_outcome": (
            {
                "decision": runtime_result.result_verification_outcome.decision.value,
                "is_suspicious": runtime_result.result_verification_outcome.is_suspicious,
                "failure_code": runtime_result.result_verification_outcome.failure_code,
                "recommended_probe": runtime_result.result_verification_outcome.recommended_probe,
                "details": runtime_result.result_verification_outcome.details,
            }
            if runtime_result.result_verification_outcome is not None
            else None
        ),
        "diagnostic_probe_outcome": (
            {
                "probe_executed": runtime_result.diagnostic_probe_outcome.probe_executed,
                "probe_type": runtime_result.diagnostic_probe_outcome.probe_type,
                "probe_sql": runtime_result.diagnostic_probe_outcome.probe_sql,
                "findings": runtime_result.diagnostic_probe_outcome.findings,
                "failure_code": runtime_result.diagnostic_probe_outcome.failure_code,
                "details": runtime_result.diagnostic_probe_outcome.details,
            }
            if runtime_result.diagnostic_probe_outcome is not None
            else None
        ),
        "semantic_plan_summary": (
            {
                "plan_id": runtime_result.semantic_plan.plan_id,
                "status": runtime_result.semantic_plan.status.value,
                "metric_name": runtime_result.semantic_plan.metric_name,
                "aggregation": runtime_result.semantic_plan.aggregation.value,
                "uncertainty_level": runtime_result.semantic_plan.semantic_uncertainty_level,
                "relevant_tables": runtime_result.semantic_plan.relevant_tables,
            }
            if runtime_result.semantic_plan is not None
            else None
        ),
        "execution_correct": execution_correct,
        "latency_ms": runtime_result.total_latency_ms,
        "grounding_calls": (
            orchestration_trace.total_grounding_calls if orchestration_trace is not None else None
        ),
        "solver_calls": (
            orchestration_trace.total_solver_calls if orchestration_trace is not None else None
        ),
        "tokens_input": _sum_prompt_tokens(runtime_result),
        "tokens_output": _sum_output_tokens(runtime_result),
        "error_code": runtime_result.status.value
        if runtime_result.status != RuntimeStatus.COMPLETED
        else None,
        "error_message": runtime_result.error_message,
        "bird_difficulty": inference_case.bird_difficulty,
        "t2s_stratum": inference_case.t2s_stratum,
        "value_binding_count": value_grounding_trace.binding_count,
        "value_probe_count": value_grounding_trace.probe_count,
        "value_grounding_latency_ms": value_grounding_trace.latency_ms,
        "value_bound_column_fqns": value_grounding_trace.bound_column_fqns,
        "candidate_uses_value_evidence": value_grounding_trace.candidate_uses_value_evidence,
        "failure_taxonomy": _classify_failure(runtime_result, execution_correct),
        "escalation_reason": (escalation_records[0].reason.value if escalation_records else None),
        "escalation_action": (escalation_records[0].action.value if escalation_records else None),
        "escalation_evidence": (escalation_records[0].evidence if escalation_records else []),
        "baseline_tables": (
            orchestration_trace.baseline_table_fqns if orchestration_trace is not None else []
        ),
        "final_tables": (
            orchestration_trace.final_table_fqns if orchestration_trace is not None else []
        ),
        "solver_unresolved": (
            orchestration_trace.baseline_solver_unresolved
            if orchestration_trace is not None
            else []
        ),
        "grounding_unresolved": (
            orchestration_trace.baseline_unresolved_codes if orchestration_trace is not None else []
        ),
        "rejected_candidate_sql": (
            runtime_result.trace.rejected_candidate.sql
            if runtime_result.trace.rejected_candidate is not None
            else None
        ),
        "rejected_candidate_assumptions": (
            runtime_result.trace.rejected_candidate.assumptions
            if runtime_result.trace.rejected_candidate is not None
            else []
        ),
        "rejected_candidate_unresolved": (
            runtime_result.trace.rejected_candidate.unresolved
            if runtime_result.trace.rejected_candidate is not None
            else []
        ),
        "candidate_assumptions": (
            runtime_result.trace.candidate_assumptions if runtime_result.trace is not None else []
        ),
    }


def _build_infrastructure_failure_result(
    case_bundle: BenchmarkCaseBundle,
    exc: Exception,
    started_at: datetime,
) -> dict[str, Any]:
    inference_case = case_bundle.inference_case
    latency_ms = (datetime.now(UTC) - started_at).total_seconds() * 1000
    return {
        "case_id": inference_case.case_id,
        "question_id": inference_case.question_id,
        "db_id": inference_case.db_id,
        "runtime_status": "GENERATION_FAILED",
        "generated_sql": None,
        "orchestration_outcome": None,
        "escalated": False,
        "same_context_stop": False,
        "safety_passed": False,
        "access_passed": False,
        "execution_success": False,
        "gold_execution_success": False,
        "execution_correct": None,
        "latency_ms": round(latency_ms, 3),
        "grounding_calls": None,
        "solver_calls": None,
        "tokens_input": None,
        "tokens_output": None,
        "error_code": type(exc).__name__,
        "error_message": str(exc),
        "bird_difficulty": inference_case.bird_difficulty,
        "t2s_stratum": inference_case.t2s_stratum,
        "failure_taxonomy": "UNKNOWN",
    }


def _artifact_status(status: RuntimeStatus) -> str:
    if status == RuntimeStatus.COMPLETED:
        return "SUCCESS"
    return status.value.upper()


def _sum_prompt_tokens(runtime_result: RuntimeExecutionResult) -> int | None:
    return _sum_generation_trace_field(runtime_result, "prompt_tokens")


def _sum_output_tokens(runtime_result: RuntimeExecutionResult) -> int | None:
    return _sum_generation_trace_field(runtime_result, "output_tokens")


def _sum_generation_trace_field(
    runtime_result: RuntimeExecutionResult,
    field_name: str,
) -> int | None:
    # Current P5 trace stores call counts but not each SqlCandidate trace. Keep null instead of
    # fabricating token accounting.
    return None


def _classify_failure(
    runtime_result: RuntimeExecutionResult,
    execution_correct: bool | None,
) -> str | None:
    if runtime_result.status == RuntimeStatus.COMPLETED and execution_correct is True:
        return None
    if runtime_result.status == RuntimeStatus.COMPLETED and execution_correct is False:
        return "SQL_INCORRECT"
    if runtime_result.status == RuntimeStatus.UNRESOLVED:
        return "UNRESOLVED"
    if runtime_result.status == RuntimeStatus.SAFETY_REJECTED:
        return "SAFETY_REJECTED"
    if runtime_result.status == RuntimeStatus.ACCESS_DENIED:
        return "ACCESS_REJECTED"
    if runtime_result.status == RuntimeStatus.EXECUTION_FAILED:
        return "EXECUTION_ERROR"
    if runtime_result.status == RuntimeStatus.TIMEOUT:
        return "TIMEOUT"
    if runtime_result.status == RuntimeStatus.GENERATION_FAILED:
        return "SQL_GENERATION_ERROR"
    return "UNKNOWN"


def _build_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"t2s_benchmark_{timestamp}_{str(uuid4())[:8]}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a reproducible T2S BIRD benchmark.")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--pilot-dataset", default=str(DEFAULT_PILOT_DATASET))
    parser.add_argument("--database-root", default=str(DEFAULT_DATABASE_ROOT))
    parser.add_argument(
        "--value-grounding",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Probe the execution database for literals and supply them to the solver.",
    )
    parser.add_argument(
        "--strict-abstention",
        action="store_true",
        help=(
            "Abstain whenever the solver reports any uncertainty, even on a "
            "structurally sound candidate. Reproduces pre-correction behaviour."
        ),
    )
    parser.add_argument("--max-value-columns", type=int, default=6)
    parser.add_argument("--max-value-candidates-per-column", type=int, default=5)
    parser.add_argument("--value-lookup-timeout-ms", type=int, default=1500)
    parser.add_argument(
        "--evidence-mode",
        choices=["none", "inline", "structured"],
        default="structured",
        help=(
            "How dataset evidence reaches the solver: appended to the question "
            "(inline, the historical behaviour) or as a separate field (structured)."
        ),
    )
    parser.add_argument("--tables-json", default=str(DEFAULT_TABLES_JSON))
    parser.add_argument("--prompt-directory", default=str(DEFAULT_PROMPT_DIRECTORY))
    parser.add_argument("--prompt-version", default="v003")
    parser.add_argument("--executable-only", action="store_true", default=False)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--output", default=str(DEFAULT_RESULTS_ROOT))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--db-id", action="append", default=[])
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--verify-invariants", action="store_true")
    parser.add_argument(
        "--planner-mode",
        choices=["off", "llm", "deterministic"],
        default="off",
        help="Semantic planner mode: off (default), llm, or deterministic.",
    )
    parser.add_argument(
        "--result-verifier",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable post-execution result verification and diagnostic probing.",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    output_dir = asyncio.run(run_benchmark(args))
    print(output_dir)


if __name__ == "__main__":
    main()
