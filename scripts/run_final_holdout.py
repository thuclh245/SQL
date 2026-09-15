# ruff: noqa: E501
"""Final Freeze & One-Shot Holdout Evaluation (Phase 8 Final Holdout).

Executes the frozen deployed pipeline exactly once over the 215-case untouched holdout.
Strict gold isolation, exact terminal category accounting, paired statistical analysis,
and fail-closed provider error handling.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.benchmark.case_loader import BenchmarkCaseBundle, load_benchmark_cases
from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.benchmark.invariants import resolve_official_database_path
from t2s.benchmark.scoring import execute_gold_sql, score_execution_accuracy
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.database import QueryExecutionPolicy
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.errors import MalformedSolverOutputError, SolverDependencyError
from t2s.evaluation.uncertainty_diagnostics import (
    classify_sql_failure_slice,
    wilson_score_interval,
)
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.orchestration import AdaptiveOrchestrator, EscalationBudget, EscalationPolicy
from t2s.orchestration.escalation_contracts import OrchestrationOutcome
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.security.sanitization import sanitize_data
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.solver.chat_client import StructuredChatClient
from t2s.verification.contracts import (
    SEMANTIC_CHECK_DIMENSIONS,
    VerificationDecision,
    VerificationInput,
    VerificationResult,
)
from t2s.verification.llm_semantic_verifier import LlmSemanticVerifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_final_holdout_v1.jsonl"
DEFAULT_DATABASE_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
DEFAULT_TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "final_holdout" / "t2s_final_holdout_v1.json"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "results" / "final_holdout_v1"

GENERATOR_MODEL = "openai/gpt-oss-120b"
VERIFIER_MODEL = "openai/gpt-5-mini"
EXPECTED_TOTAL_CASES = 215

# OpenRouter pricing assumptions (USD per 1M tokens)
PRICING = {
    "generator": {"prompt": 0.15, "completion": 0.60},
    "verifier": {"prompt": 0.25, "completion": 2.00},
}


def load_env() -> dict[str, str]:
    env_file = PROJECT_ROOT / ".env"
    env_vars: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


class AllTablesAccessPolicy:
    def __init__(self, authorized_resources: list[AuthorizedSqlResource]) -> None:
        self.authorized_resources = authorized_resources

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return list(self.authorized_resources)


def prebuild_database_infrastructure(
    case_bundles: list[BenchmarkCaseBundle],
    database_root: Path,
    tables_json_path: Path,
    chat_client: StructuredChatClient,
    model_name: str,
    prompt_directory: Path,
    prompt_version: str,
) -> dict[str, Any]:
    db_cache: dict[str, Any] = {}
    unique_dbs = {c.inference_case.db_id for c in case_bundles}

    for db_id in unique_dbs:
        db_path = resolve_official_database_path(database_root, db_id)
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        catalog_tables = load_bird_catalog_tables(db_id=db_id, tables_json_path=tables_json_path)
        catalog = InMemoryCatalog()
        catalog.upsert_tables(catalog_tables)

        doc_builder = CatalogSearchDocumentBuilder()
        search_docs = [doc for t in catalog_tables for doc in doc_builder.build_search_documents(t)]
        retriever = SchemaRetriever(InMemorySchemaSearch(search_docs))

        auth_resources = [
            AuthorizedSqlResource(catalog_fqn=t.table_fqn, sql_identifier=t.sql_identifier)
            for t in catalog_tables
            if t.sql_identifier is not None
        ]
        auth_service = AuthorizationService(AllTablesAccessPolicy(auth_resources))
        grounding_builder = GroundingContextBuilder(
            catalog=catalog,
            schema_retriever=retriever,
            authorization_service=auth_service,
            grounding_budget=GroundingBudget(
                max_tables=5,
                max_columns_per_table=10,
                max_sample_values_per_column=3,
                max_total_tokens=2000,
            ),
        )

        solver = DirectSqlSolver(
            chat_client=chat_client,
            prompt_builder=DirectSqlPromptBuilder(
                prompt_directory=prompt_directory,
                prompt_version=prompt_version,
            ),
            model_name=model_name,
        )

        orchestrator = AdaptiveOrchestrator(
            grounding_context_builder=grounding_builder,
            solver=solver,
            escalation_policy=EscalationPolicy(),
            escalation_budget=EscalationBudget(max_escalations=1),
        )

        query_executor = SqliteReadOnlyQueryExecutor(db_path)

        db_cache[db_id] = {
            "orchestrator": orchestrator,
            "query_executor": query_executor,
            "grounding_builder": grounding_builder,
            "db_path": db_path,
        }

    return db_cache


async def execute_with_transport_retry(
    func: Any,
    max_retries: int = 2,
    backoff_factors: tuple[float, ...] = (2.0, 4.0),
) -> tuple[Any, str | None]:
    """Preregistered transport retry policy: up to 3 attempts (1 + 2 retries) on SolverDependencyError.

    No selection among multiple alternatives: stops on first successful or non-retryable response.
    """
    for attempt in range(max_retries + 1):
        try:
            res = await func()
            return res, None
        except MalformedSolverOutputError:
            # Deterministic format violation: do not retry
            return None, "STRUCTURED_OUTPUT_FAILURE"
        except SolverDependencyError:
            if attempt < max_retries:
                delay = backoff_factors[min(attempt, len(backoff_factors) - 1)]
                await asyncio.sleep(delay)
                continue
            return None, "PROVIDER_FAILURE"
        except Exception as exc:
            return None, f"EXCEPTION_{type(exc).__name__}"
    return None, "UNKNOWN_TRANSPORT_ERROR"


async def run_single_case(
    case: BenchmarkCaseBundle,
    db_infra: dict[str, Any],
    llm_verifier: LlmSemanticVerifier,
    prompt_builder: DirectSqlPromptBuilder,
    run_id: str,
) -> dict[str, Any]:
    inf_case = case.inference_case
    cid = inf_case.case_id
    db_id = inf_case.db_id
    user_identity = UserIdentity(user_id="final-holdout-evaluator", tenant_id="t2s")
    q_req = QueryRequest(
        question=inf_case.question,
        target_hint=inf_case.evidence or "",
        database_dialect="sqlite",
    )

    orchestrator: AdaptiveOrchestrator = db_infra["orchestrator"]
    executor: SqliteReadOnlyQueryExecutor = db_infra["query_executor"]
    db_path: Path = db_infra["db_path"]

    from t2s.contracts.grounding_context import GroundingContext
    from t2s.solver import SolverRequest

    def solver_req_factory(grounding_context: GroundingContext, run_identifier: str) -> SolverRequest:
        return SolverRequest(
            run_id=run_identifier,
            query_request=q_req,
            target_dialect="sqlite",
            grounding_context=grounding_context,
        )

    # 1. Grounding & Generator Execution (with retry)
    t0 = time.perf_counter()
    async def _invoke_orch():
        return await orchestrator.run(
            query_request=q_req,
            user_identity=user_identity,
            solver_request_factory=solver_req_factory,
            run_id=f"{run_id}_{cid}",
        )

    orch_result, gen_transport_err = await execute_with_transport_retry(_invoke_orch)
    t_gen_elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    gen_failure_type = None
    candidate_produced = False
    candidate_sql: str | None = None
    p5_accepted = False
    final_ctx = None

    if gen_transport_err:
        if gen_transport_err == "PROVIDER_FAILURE":
            gen_failure_type = "GENERATOR_PROVIDER_FAILURE"
        elif gen_transport_err == "STRUCTURED_OUTPUT_FAILURE":
            gen_failure_type = "STRUCTURED_OUTPUT_FAILURE"
        else:
            gen_failure_type = f"GENERATOR_{gen_transport_err}"
    elif orch_result is not None:
        final_ctx = orch_result.grounding_context
        if orch_result.sql_candidate is not None:
            candidate_produced = True
            candidate_sql = orch_result.sql_candidate.sql
            p5_accepted = orch_result.outcome in (
                OrchestrationOutcome.BASELINE_SUCCESS,
                OrchestrationOutcome.ESCALATED_SUCCESS,
            )
        elif orch_result.outcome == OrchestrationOutcome.FAILED:
            gen_failure_type = "GENERATOR_PROVIDER_FAILURE"
        else:
            # Unresolved without candidate
            pass

    # Extract schema details for verifier
    auth_schema = prompt_builder._format_authorized_schema(final_ctx) if final_ctx else ""
    auth_tables = [t.fqn for t in final_ctx.tables] if final_ctx else []
    auth_cols = (
        {t.sql_identifier: [c.name for c in t.columns] for t in final_ctx.tables if t.sql_identifier}
        if final_ctx
        else {}
    )

    # 2. Semantic Verifier (Strict Gold Isolation)
    t_ver_start = time.perf_counter()
    llm_v_res: VerificationResult | None = None
    ver_transport_err: str | None = None
    ver_failure_type: str | None = None

    if candidate_sql:
        v_input = VerificationInput(
            question=inf_case.question,
            evidence=inf_case.evidence or "",
            dialect="sqlite",
            authorized_schema=auth_schema,
            candidate_sql=candidate_sql,
            authorized_tables=auth_tables,
            authorized_columns=auth_cols,
        )

        async def _invoke_ver():
            return await llm_verifier.verify(v_input)

        llm_v_res, ver_transport_err = await execute_with_transport_retry(_invoke_ver)
        if ver_transport_err:
            if ver_transport_err == "PROVIDER_FAILURE":
                ver_failure_type = "VERIFIER_PROVIDER_FAILURE"
            elif ver_transport_err == "STRUCTURED_OUTPUT_FAILURE":
                ver_failure_type = "STRUCTURED_OUTPUT_FAILURE"
            else:
                ver_failure_type = f"VERIFIER_{ver_transport_err}"

            # Fail closed on verifier failure
            llm_v_res = VerificationResult(
                projection={"status": "UNKNOWN", "short_reason": ver_failure_type},  # type: ignore[arg-type]
                aggregation_and_grain={"status": "UNKNOWN", "short_reason": ver_failure_type},  # type: ignore[arg-type]
                filters_and_values={"status": "UNKNOWN", "short_reason": ver_failure_type},  # type: ignore[arg-type]
                join_semantics={"status": "UNKNOWN", "short_reason": ver_failure_type},  # type: ignore[arg-type]
                ordering_and_limit={"status": "UNKNOWN", "short_reason": ver_failure_type},  # type: ignore[arg-type]
                null_semantics={"status": "UNKNOWN", "short_reason": ver_failure_type},  # type: ignore[arg-type]
                schema_reference={"status": "UNKNOWN", "short_reason": ver_failure_type},  # type: ignore[arg-type]
                decision=VerificationDecision.ABSTAIN,
                unknown_checks=list(SEMANTIC_CHECK_DIMENSIONS),
            )

    t_ver_elapsed_ms = round((time.perf_counter() - t_ver_start) * 1000, 2)

    # 3. Evaluator Scorer Execution (Strictly Post-Hoc Scorer Only)
    gold_sql = case.scoring_gold.official_sql
    gold_exec = execute_gold_sql(gold_sql, db_path) if gold_sql else None

    candidate_exec_ok = False
    candidate_exec_error = None
    execution_correct: bool | None = None
    t_exec_start = time.perf_counter()

    if candidate_sql:
        try:
            cand_exec_res = executor.execute_query(
                candidate_sql,
                user_identity=user_identity,
                policy=QueryExecutionPolicy(maximum_result_rows=1000, statement_timeout_seconds=30),
            )
            candidate_exec_ok = True
            if gold_exec and gold_exec.ok:
                score_res = score_execution_accuracy(
                    predicted_rows=cand_exec_res.rows,
                    gold_rows=gold_exec.rows,
                )
                execution_correct = score_res.is_correct
            else:
                execution_correct = False
        except Exception as exc:
            candidate_exec_ok = False
            candidate_exec_error = str(exc)
            execution_correct = False

    t_exec_elapsed_ms = round((time.perf_counter() - t_exec_start) * 1000, 2)
    t_total_elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Verifier decision resolution
    ver_decision_str = llm_v_res.decision.value if llm_v_res else "NONE"
    checks_summary = {
        dim: getattr(llm_v_res, dim).status.value
        for dim in SEMANTIC_CHECK_DIMENSIONS
    } if llm_v_res else {}

    # Evaluator-side counterfactual policy outcomes
    # Policy 1: Accept All candidate
    p_accept_all = {
        "executed": candidate_produced,
        "correct": bool(execution_correct) if candidate_produced else False,
        "incorrect": not bool(execution_correct) if candidate_produced else False,
        "withheld": not candidate_produced,
    }

    # Policy 2: P5 alone
    p_p5 = {
        "executed": p5_accepted and candidate_produced,
        "correct": bool(execution_correct) if (p5_accepted and candidate_produced) else False,
        "incorrect": not bool(execution_correct) if (p5_accepted and candidate_produced) else False,
        "withheld": not (p5_accepted and candidate_produced),
    }

    # Policy 3: P5 + frozen verifier v001 (Policy A)
    p5_and_ver_accepted = (
        p5_accepted
        and candidate_produced
        and ver_decision_str == "ACCEPT"
        and ver_failure_type is None
    )
    p_p5_ver = {
        "executed": p5_and_ver_accepted,
        "correct": bool(execution_correct) if p5_and_ver_accepted else False,
        "incorrect": not bool(execution_correct) if p5_and_ver_accepted else False,
        "withheld": not p5_and_ver_accepted,
    }

    # Failure slice diagnosis for incorrect candidates
    failure_slice = None
    if candidate_sql and gold_sql and not execution_correct:
        failure_slice = classify_sql_failure_slice(candidate_sql, gold_sql).value

    # Extract usage tokens if available
    gen_p_tok = None
    gen_o_tok = None
    if orch_result and orch_result.sql_candidate:
        gen_p_tok = orch_result.sql_candidate.prompt_tokens
        gen_o_tok = orch_result.sql_candidate.completion_tokens

    record = {
        "case_id": cid,
        "question_id": inf_case.question_id,
        "db_id": db_id,
        "difficulty": inf_case.bird_difficulty,
        "stratum": inf_case.t2s_stratum,
        "candidate_produced": candidate_produced,
        "candidate_sql": candidate_sql,
        "p5_accepted": p5_accepted,
        "p5_outcome": orch_result.outcome.value if orch_result else "GENERATOR_ERROR",
        "gen_failure_type": gen_failure_type,
        "verifier_invoked": candidate_produced,
        "verifier_decision": ver_decision_str,
        "verifier_checks": checks_summary,
        "verifier_failure_type": ver_failure_type,
        "candidate_exec_ok": candidate_exec_ok,
        "candidate_exec_error": candidate_exec_error,
        "execution_correct": execution_correct,
        "failure_slice": failure_slice,
        "counterfactual_policies": {
            "accept_all": p_accept_all,
            "p5_alone": p_p5,
            "p5_and_verifier_v001": p_p5_ver,
        },
        "latencies_ms": {
            "generator": t_gen_elapsed_ms,
            "verifier": t_ver_elapsed_ms,
            "execution": t_exec_elapsed_ms,
            "total": t_total_elapsed_ms,
        },
        "tokens": {
            "generator_prompt": gen_p_tok,
            "generator_output": gen_o_tok,
        },
    }
    return record


def compute_policy_metrics(cases: list[dict[str, Any]], policy_key: str, total_cases: int = EXPECTED_TOTAL_CASES) -> dict[str, Any]:
    n = total_cases
    accepted = [c for c in cases if c["counterfactual_policies"][policy_key]["executed"]]
    correct = [c for c in accepted if c["counterfactual_policies"][policy_key]["correct"]]
    incorrect = [c for c in accepted if c["counterfactual_policies"][policy_key]["incorrect"]]
    withheld = [c for c in cases if c["counterfactual_policies"][policy_key]["withheld"]]

    a_count = len(accepted)
    c_count = len(correct)
    i_count = len(incorrect)
    w_count = len(withheld)

    assert a_count + w_count == n
    assert c_count + i_count == a_count

    precision = c_count / a_count if a_count > 0 else 0.0
    coverage = a_count / n
    risk = i_count / a_count if a_count > 0 else 0.0
    incorrect_rate = i_count / n
    ex = c_count / n
    abstention_rate = w_count / n

    ci_low, ci_high = wilson_score_interval(c_count, a_count, confidence=0.95) if a_count > 0 else (0.0, 0.0)

    return {
        "total_cases": n,
        "accepted_count": a_count,
        "correct_accepted_count": c_count,
        "incorrect_accepted_count": i_count,
        "withheld_count": w_count,
        "accepted_precision": round(precision, 4),
        "precision_95_ci": [round(ci_low, 4), round(ci_high, 4)],
        "coverage": round(coverage, 4),
        "selective_risk": round(risk, 4),
        "incorrect_execution_rate": round(incorrect_rate, 4),
        "execution_accuracy": round(ex, 4),
        "abstention_rate": round(abstention_rate, 4),
    }


def compute_candidate_accounting(cases: list[dict[str, Any]], total_cases: int = EXPECTED_TOTAL_CASES) -> dict[str, Any]:
    cand_produced = 0
    no_cand = 0
    gen_failure = 0

    p5_acc = 0
    p5_unres = 0

    ver_acc = 0
    ver_rej = 0
    ver_abs = 0
    ver_fail = 0

    exec_corr = 0
    exec_inc = 0

    for c in cases:
        if c["gen_failure_type"]:
            gen_failure += 1
        elif c["candidate_produced"]:
            cand_produced += 1
        else:
            no_cand += 1

        if c["p5_accepted"]:
            p5_acc += 1
        else:
            p5_unres += 1

        if c["verifier_failure_type"]:
            ver_fail += 1
        elif c["candidate_produced"]:
            dec = c["verifier_decision"]
            if dec == "ACCEPT":
                ver_acc += 1
            elif dec == "REJECT":
                ver_rej += 1
            elif dec == "ABSTAIN":
                ver_abs += 1

        if c["candidate_produced"]:
            if c["execution_correct"]:
                exec_corr += 1
            else:
                exec_inc += 1

    terminal_gen = cand_produced + no_cand + gen_failure
    unaccounted = total_cases - terminal_gen

    return {
        "total_cases": total_cases,
        "candidate_produced": cand_produced,
        "no_candidate": no_cand,
        "generator_failure": gen_failure,
        "p5_accepted": p5_acc,
        "p5_unresolved": p5_unres,
        "verifier_accept": ver_acc,
        "verifier_reject": ver_rej,
        "verifier_abstain": ver_abs,
        "verifier_provider_failure": ver_fail,
        "executed_correct": exec_corr,
        "executed_incorrect": exec_inc,
        "unaccounted": unaccounted,
    }


def compute_verifier_confusion(cases: list[dict[str, Any]]) -> dict[str, int]:
    ca = 0
    ia = 0
    cr = 0
    ir = 0
    cab = 0
    iab = 0

    for c in cases:
        if not c["candidate_produced"] or c["verifier_failure_type"]:
            continue
        dec = c["verifier_decision"]
        corr = c["execution_correct"]
        if dec == "ACCEPT":
            if corr:
                ca += 1
            else:
                ia += 1
        elif dec == "REJECT":
            if corr:
                cr += 1
            else:
                ir += 1
        elif dec == "ABSTAIN":
            if corr:
                cab += 1
            else:
                iab += 1

    return {
        "correct_accepted": ca,
        "incorrect_accepted": ia,
        "correct_rejected": cr,
        "incorrect_rejected": ir,
        "correct_abstained": cab,
        "incorrect_abstained": iab,
    }


def compute_latency_and_cost(cases: list[dict[str, Any]]) -> dict[str, Any]:
    gen_lats = [c["latencies_ms"]["generator"] for c in cases if c["latencies_ms"]["generator"] is not None]
    ver_lats = [c["latencies_ms"]["verifier"] for c in cases if c["candidate_produced"] and c["latencies_ms"]["verifier"] is not None]
    exec_lats = [c["latencies_ms"]["execution"] for c in cases if c["candidate_produced"] and c["latencies_ms"]["execution"] is not None]
    tot_lats = [c["latencies_ms"]["total"] for c in cases if c["latencies_ms"]["total"] is not None]

    def _stats(arr: list[float]) -> dict[str, float]:
        if not arr:
            return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
        s = sorted(arr)
        p50 = statistics.median(s)
        p95 = s[int(len(s) * 0.95)] if len(s) >= 20 else s[-1]
        return {
            "mean": round(statistics.mean(s), 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
        }

    # Token counting & estimation
    # Est tokens per call based on observed lengths
    est_gen_prompt_tok = 2200 * len(cases)
    est_gen_out_tok = 250 * len(cases)
    cands_count = sum(1 for c in cases if c["candidate_produced"])
    est_ver_prompt_tok = 2300 * cands_count
    est_ver_out_tok = 350 * cands_count

    gen_cost = (est_gen_prompt_tok / 1e6 * PRICING["generator"]["prompt"]) + (est_gen_out_tok / 1e6 * PRICING["generator"]["completion"])
    ver_cost = (est_ver_prompt_tok / 1e6 * PRICING["verifier"]["prompt"]) + (est_ver_out_tok / 1e6 * PRICING["verifier"]["completion"])
    total_cost = gen_cost + ver_cost

    return {
        "generator_latency_ms": _stats(gen_lats),
        "verifier_latency_ms": _stats(ver_lats),
        "execution_latency_ms": _stats(exec_lats),
        "end_to_end_latency_ms": _stats(tot_lats),
        "tokens": {
            "estimated_generator_prompt_tokens": est_gen_prompt_tok,
            "estimated_generator_output_tokens": est_gen_out_tok,
            "estimated_verifier_prompt_tokens": est_ver_prompt_tok,
            "estimated_verifier_output_tokens": est_ver_out_tok,
        },
        "cost_usd": {
            "generator_cost": round(gen_cost, 4),
            "verifier_cost": round(ver_cost, 4),
            "total_estimated_cost": round(total_cost, 4),
            "pricing_assumptions": PRICING,
        },
    }


def compute_failure_slices(cases: list[dict[str, Any]]) -> dict[str, Any]:
    # For incorrect accepted queries under P5 + verifier
    ia_slices: Counter[str] = Counter()
    all_incorrect_slices: Counter[str] = Counter()

    for c in cases:
        sl = c.get("failure_slice")
        if not sl:
            continue
        all_incorrect_slices[sl] += 1
        if c["counterfactual_policies"]["p5_and_verifier_v001"]["incorrect"]:
            ia_slices[sl] += 1

    return {
        "p5_and_verifier_false_accept_slices": dict(ia_slices.most_common()),
        "all_incorrect_candidate_slices": dict(all_incorrect_slices.most_common()),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="T2S One-Shot Final Holdout Evaluation")
    parser.add_argument("--dataset", type=str, default=str(DEFAULT_DATASET))
    parser.add_argument("--output", type=str, default=str(DEFAULT_RESULTS_ROOT))
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env_vars = load_env()
    api_key = env_vars.get("OPENAI_API_KEY")
    base_url = env_vars.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    if not api_key and not args.dry_run:
        raise ValueError("Missing OPENAI_API_KEY in environment or .env file.")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = Path(args.dataset)
    cases = load_benchmark_cases(dataset_path)
    if len(cases) != EXPECTED_TOTAL_CASES:
        raise ValueError(f"Expected exactly {EXPECTED_TOTAL_CASES} cases, got {len(cases)}")

    print(f"=== T2S Final Holdout Execution: Loaded {len(cases)} cases ===")

    # Initialize chat clients
    chat_client = OpenAICompatibleChatClient(
        base_url=base_url,
        api_key=api_key or "mock-key",
        request_timeout_seconds=120.0,
    )

    prompt_builder = DirectSqlPromptBuilder(
        prompt_directory=PROJECT_ROOT / "prompts" / "direct_sql",
        prompt_version="v001",
    )

    db_infra = prebuild_database_infrastructure(
        case_bundles=cases,
        database_root=DEFAULT_DATABASE_ROOT,
        tables_json_path=DEFAULT_TABLES_JSON,
        chat_client=chat_client,
        model_name=GENERATOR_MODEL,
        prompt_directory=PROJECT_ROOT / "prompts" / "direct_sql",
        prompt_version="v001",
    )

    llm_verifier = LlmSemanticVerifier(
        chat_client=chat_client,
        model_name=VERIFIER_MODEL,
        prompt_directory=PROJECT_ROOT / "prompts" / "sql_verifier",
        prompt_version="v001",
        reasoning_effort="low",
        max_output_tokens=4096,
    )

    sem = asyncio.Semaphore(args.concurrency)
    predictions_file = out_dir / "predictions.jsonl"
    results_lock = asyncio.Lock()
    all_results: list[dict[str, Any]] = []

    async def _process_case(idx: int, case_bundle: BenchmarkCaseBundle) -> dict[str, Any]:
        async with sem:
            rec = await run_single_case(
                case=case_bundle,
                db_infra=db_infra[case_bundle.inference_case.db_id],
                llm_verifier=llm_verifier,
                prompt_builder=prompt_builder,
                run_id="final_holdout_v1",
            )
            async with results_lock:
                all_results.append(rec)
                with predictions_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(sanitize_data(rec)) + "\n")
                if len(all_results) % 25 == 0 or len(all_results) == len(cases):
                    print(f"Progress: {len(all_results)}/{len(cases)} cases processed.")
            return rec

    t_start = time.perf_counter()
    # Clear prior output if starting fresh
    if predictions_file.exists():
        predictions_file.unlink()

    tasks = [_process_case(i, c) for i, c in enumerate(cases)]
    await asyncio.gather(*tasks)
    t_elapsed = round(time.perf_counter() - t_start, 2)
    print(f"Completed {len(all_results)} cases in {t_elapsed} seconds.")

    # 4. Compute Official Metrics
    p_accept_all = compute_policy_metrics(all_results, "accept_all")
    p_p5 = compute_policy_metrics(all_results, "p5_alone")
    p_p5_ver = compute_policy_metrics(all_results, "p5_and_verifier_v001")

    policy_comp = {
        "accept_all": p_accept_all,
        "p5_alone": p_p5,
        "p5_and_verifier_v001": p_p5_ver,
    }
    (out_dir / "policy_comparison.json").write_text(
        json.dumps(sanitize_data(policy_comp), indent=2) + "\n", encoding="utf-8"
    )

    cand_acc = compute_candidate_accounting(all_results)
    (out_dir / "candidate_accounting.json").write_text(
        json.dumps(sanitize_data(cand_acc), indent=2) + "\n", encoding="utf-8"
    )

    ver_conf = compute_verifier_confusion(all_results)
    (out_dir / "verifier_confusion.json").write_text(
        json.dumps(sanitize_data(ver_conf), indent=2) + "\n", encoding="utf-8"
    )

    failure_slices = compute_failure_slices(all_results)
    (out_dir / "failure_slices.json").write_text(
        json.dumps(sanitize_data(failure_slices), indent=2) + "\n", encoding="utf-8"
    )

    lat_cost = compute_latency_and_cost(all_results)
    (out_dir / "latency_cost.json").write_text(
        json.dumps(sanitize_data(lat_cost), indent=2) + "\n", encoding="utf-8"
    )

    manifest = {
        "benchmark": "t2s_final_holdout_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "total_cases": EXPECTED_TOTAL_CASES,
        "generator_model": GENERATOR_MODEL,
        "verifier_model": VERIFIER_MODEL,
        "elapsed_seconds": t_elapsed,
        "dataset_path": str(dataset_path),
        "accounting_unaccounted": cand_acc["unaccounted"],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(sanitize_data(manifest), indent=2) + "\n", encoding="utf-8"
    )

    # Write summary.md
    delta_prec = round(p_p5_ver["accepted_precision"] - p_p5["accepted_precision"], 4)
    delta_risk = round(p_p5_ver["selective_risk"] - p_p5["selective_risk"], 4)
    delta_cov = round(p_p5_ver["coverage"] - p_p5["coverage"], 4)
    delta_ex = round(p_p5_ver["execution_accuracy"] - p_p5["execution_accuracy"], 4)

    summary_md = f"""# Final Holdout Summary: Phase 8-V1

**Execution Completed**: {datetime.now(UTC).isoformat()}  
**Total Cases**: {EXPECTED_TOTAL_CASES}  
**Generator**: `{GENERATOR_MODEL}`  
**Verifier**: `{VERIFIER_MODEL}` (v001, Policy A)  

## Policy Comparison Table

| Policy | Precision | 95% CI | Coverage | Risk | EX | Incorrect Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Accept All | {p_accept_all['accepted_precision']*100:.2f}% | [{p_accept_all['precision_95_ci'][0]*100:.2f}%, {p_accept_all['precision_95_ci'][1]*100:.2f}%] | {p_accept_all['coverage']*100:.2f}% | {p_accept_all['selective_risk']*100:.2f}% | {p_accept_all['execution_accuracy']*100:.2f}% | {p_accept_all['incorrect_execution_rate']*100:.2f}% |
| P5 | {p_p5['accepted_precision']*100:.2f}% | [{p_p5['precision_95_ci'][0]*100:.2f}%, {p_p5['precision_95_ci'][1]*100:.2f}%] | {p_p5['coverage']*100:.2f}% | {p_p5['selective_risk']*100:.2f}% | {p_p5['execution_accuracy']*100:.2f}% | {p_p5['incorrect_execution_rate']*100:.2f}% |
| P5 + frozen verifier v001 | {p_p5_ver['accepted_precision']*100:.2f}% | [{p_p5_ver['precision_95_ci'][0]*100:.2f}%, {p_p5_ver['precision_95_ci'][1]*100:.2f}%] | {p_p5_ver['coverage']*100:.2f}% | {p_p5_ver['selective_risk']*100:.2f}% | {p_p5_ver['execution_accuracy']*100:.2f}% | {p_p5_ver['incorrect_execution_rate']*100:.2f}% |

## P5 vs Verifier Deltas
- Δ Accepted Precision: {delta_prec*100:+.2f}%
- Δ Selective Risk: {delta_risk*100:+.2f}%
- Δ Coverage: {delta_cov*100:+.2f}%
- Δ Execution Accuracy (EX): {delta_ex*100:+.2f}%

## Verifier Confusion
- Correct Accepted: {ver_conf['correct_accepted']}
- Incorrect Accepted: {ver_conf['incorrect_accepted']}
- Correct Rejected: {ver_conf['correct_rejected']}
- Incorrect Rejected: {ver_conf['incorrect_rejected']}
- Correct Abstained: {ver_conf['correct_abstained']}
- Incorrect Abstained: {ver_conf['incorrect_abstained']}

## Candidate Accounting
- Total: {cand_acc['total_cases']}
- Candidate Produced: {cand_acc['candidate_produced']}
- No Candidate: {cand_acc['no_candidate']}
- Generator Failure: {cand_acc['generator_failure']}
- Unaccounted: {cand_acc['unaccounted']}
"""
    (out_dir / "summary.md").write_text(summary_md, encoding="utf-8")
    print("Summary written to", out_dir / "summary.md")


if __name__ == "__main__":
    asyncio.run(main())
