# ruff: noqa: E501
"""Phase 8B: Verifier Generalization & Controlled Runtime Gate Validation.

Evaluates the frozen semantic verifier (sql_verifier/v001, Policy A) on previously
unopened development questions (Dev100) across 3 complete stochastic replicates.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter, defaultdict
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
from t2s.evaluation.uncertainty_diagnostics import wilson_score_interval
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.orchestration import AdaptiveOrchestrator, EscalationBudget, EscalationPolicy
from t2s.orchestration.escalation_contracts import OrchestrationOutcome
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.solver.chat_client import StructuredChatClient
from t2s.verification.contracts import (
    SEMANTIC_CHECK_DIMENSIONS,
    VerificationDecision,
    VerificationInput,
    VerificationResult,
)
from t2s.verification.deterministic_verifier import DeterministicSqlVerifier
from t2s.verification.llm_semantic_verifier import LlmSemanticVerifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
DEFAULT_DATABASE_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
DEFAULT_TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
DEFAULT_PROMPT_DIRECTORY = PROJECT_ROOT / "prompts" / "direct_sql"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "results" / "p8b_verifier_dev100"
REPLICATES = ["p8b_dev100_r1", "p8b_dev100_r2", "p8b_dev100_r3"]
P8A_BENCHMARK_PRECISION = 0.7778  # 77.78% from Phase 8A candidate validation


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
    """Prebuild grounding and solver infrastructure per unique database."""
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
            grounding_budget=GroundingBudget(),
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


async def run_single_case(
    case: BenchmarkCaseBundle,
    db_infra: dict[str, Any],
    llm_verifier: LlmSemanticVerifier,
    deterministic_verifier: DeterministicSqlVerifier,
    prompt_builder: DirectSqlPromptBuilder,
    run_id: str,
) -> dict[str, Any]:
    inf_case = case.inference_case
    cid = inf_case.case_id
    db_id = inf_case.db_id
    user_identity = UserIdentity(user_id="p8b-benchmark", tenant_id="t2s")
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

    def solver_req_factory(
        grounding_context: GroundingContext,
        run_identifier: str,
    ) -> SolverRequest:
        return SolverRequest(
            run_id=run_identifier,
            query_request=q_req,
            target_dialect="sqlite",
            grounding_context=grounding_context,
        )

    # --- 1. Generator (P5 Adaptive Orchestrator) ---
    t_gen_start = time.perf_counter()
    orch_result = await orchestrator.run(
        query_request=q_req,
        user_identity=user_identity,
        solver_request_factory=solver_req_factory,
        run_id=f"{run_id}_{cid}",
    )
    t_gen_elapsed = round((time.perf_counter() - t_gen_start) * 1000, 3)

    p5_accepted = orch_result.outcome in (
        OrchestrationOutcome.BASELINE_SUCCESS,
        OrchestrationOutcome.ESCALATED_SUCCESS,
    ) and orch_result.sql_candidate is not None

    candidate_sql = orch_result.sql_candidate.sql if orch_result.sql_candidate else None
    final_ctx = orch_result.grounding_context

    auth_schema = (
        prompt_builder._format_authorized_schema(final_ctx)
        if final_ctx
        else ""
    )
    auth_tables = [t.fqn for t in final_ctx.tables] if final_ctx else []
    auth_cols = (
        {t.sql_identifier: [c.name for c in t.columns] for t in final_ctx.tables if t.sql_identifier}
        if final_ctx
        else {}
    )

    # --- 2. Deterministic Verifier ---
    det_res = None
    if candidate_sql:
        det_v_input = VerificationInput(
            question=inf_case.question,
            evidence=inf_case.evidence or "",
            dialect="sqlite",
            authorized_schema=auth_schema,
            candidate_sql=candidate_sql,
            authorized_tables=auth_tables,
            authorized_columns=auth_cols,
        )
        det_res = await deterministic_verifier.verify(det_v_input)

    # --- 3. LLM Semantic Verifier (Strict Gold Isolation) ---
    t_ver_start = time.perf_counter()
    llm_v_res: VerificationResult | None = None
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
        try:
            llm_v_res = await llm_verifier.verify(v_input)
        except Exception as exc:
            llm_v_res = VerificationResult(
                projection={"status": "UNKNOWN", "short_reason": f"Exception: {exc}"},  # type: ignore[arg-type]
                aggregation_and_grain={"status": "UNKNOWN", "short_reason": f"Exception: {exc}"},  # type: ignore[arg-type]
                filters_and_values={"status": "UNKNOWN", "short_reason": f"Exception: {exc}"},  # type: ignore[arg-type]
                join_semantics={"status": "UNKNOWN", "short_reason": f"Exception: {exc}"},  # type: ignore[arg-type]
                ordering_and_limit={"status": "UNKNOWN", "short_reason": f"Exception: {exc}"},  # type: ignore[arg-type]
                null_semantics={"status": "UNKNOWN", "short_reason": f"Exception: {exc}"},  # type: ignore[arg-type]
                schema_reference={"status": "UNKNOWN", "short_reason": f"Exception: {exc}"},  # type: ignore[arg-type]
                decision=VerificationDecision.ABSTAIN,
                unknown_checks=list(SEMANTIC_CHECK_DIMENSIONS),
            )
    t_ver_elapsed = round((time.perf_counter() - t_ver_start) * 1000, 3)

    # --- 4. Database Ground Truth Execution ---
    gold_sql = case.scoring_gold.official_sql
    gold_exec = execute_gold_sql(gold_sql, db_path) if gold_sql else None

    candidate_exec_ok = False
    candidate_exec_error = None
    execution_correct: bool | None = None
    candidate_rows: list[dict[str, Any]] = []

    if candidate_sql:
        try:
            query_res = executor.execute_read_only_query(
                candidate_sql,
                QueryExecutionPolicy(maximum_result_rows=1000, statement_timeout_seconds=30),
            )
            candidate_exec_ok = True
            candidate_rows = query_res.rows
            if gold_exec and gold_exec.ok:
                execution_correct = score_execution_accuracy(
                    generated_rows=candidate_rows,
                    gold_rows=gold_exec.rows,
                    gold_sql=gold_sql or "",
                )
        except Exception as exc:
            candidate_exec_ok = False
            candidate_exec_error = str(exc)
            execution_correct = False

    llm_accepted = llm_v_res.decision == VerificationDecision.ACCEPT if llm_v_res else False
    det_accepted = det_res.decision == VerificationDecision.ACCEPT if det_res else False

    # Policy decisions:
    # Policy 0: Existing P5
    p0_release = p5_accepted
    # Policy 1: P5 + LLM Verifier (primary runtime gate)
    p1_release = p5_accepted and llm_accepted
    # Policy 2: Verifier Solo
    p2_release = bool(candidate_sql) and llm_accepted
    # Policy 3: Selective Recovery
    p3_release = p5_accepted or (bool(candidate_sql) and not p5_accepted and llm_accepted)
    # Policy 4: P5 + Deterministic Verifier
    p4_release = p5_accepted and det_accepted
    # Accept-All
    accept_all_release = bool(candidate_sql)

    return {
        "case_id": cid,
        "question_id": inf_case.question_id,
        "db_id": db_id,
        "question": inf_case.question,
        "evidence": inf_case.evidence,
        "candidate_sql": candidate_sql,
        "gold_sql": gold_sql,
        "p5_status": orch_result.outcome.value,
        "p5_accepted": p5_accepted,
        "generator_latency_ms": t_gen_elapsed,
        "verifier_latency_ms": t_ver_elapsed,
        "verifier_decision": llm_v_res.decision.value if llm_v_res else None,
        "verifier_checks": (
            {
                dim: getattr(llm_v_res, dim).status.value
                for dim in SEMANTIC_CHECK_DIMENSIONS
            }
            if llm_v_res
            else {}
        ),
        "deterministic_decision": det_res.decision.value if det_res else None,
        "execution_correct": execution_correct,
        "candidate_exec_ok": candidate_exec_ok,
        "candidate_exec_error": candidate_exec_error,
        "gold_exec_ok": gold_exec.ok if gold_exec else False,
        "policies": {
            "policy_0_p5": p0_release,
            "policy_1_p5_and_llm": p1_release,
            "policy_2_llm_solo": p2_release,
            "policy_3_selective_recovery": p3_release,
            "policy_4_p5_and_det": p4_release,
            "accept_all": accept_all_release,
        },
    }


def compute_policy_metrics(cases: list[dict[str, Any]], policy_key: str) -> dict[str, Any]:
    total = len(cases)
    executed = [c for c in cases if c["policies"][policy_key] and c["candidate_sql"]]
    unresolved_count = total - len(executed)
    exec_count = len(executed)

    correct_count = sum(1 for c in executed if c["execution_correct"] is True)
    incorrect_count = sum(1 for c in executed if c["execution_correct"] is False and c["candidate_exec_ok"])
    error_count = sum(1 for c in executed if not c["candidate_exec_ok"])

    precision = (correct_count / exec_count) if exec_count > 0 else 0.0
    coverage = exec_count / total
    mean_ex = correct_count / total
    selective_risk = ((incorrect_count + error_count) / exec_count) if exec_count > 0 else 0.0
    unresolved_rate = unresolved_count / total

    p_low, p_high = wilson_score_interval(correct_count, exec_count) if exec_count > 0 else (0.0, 0.0)
    c_low, c_high = wilson_score_interval(exec_count, total)
    ex_low, ex_high = wilson_score_interval(correct_count, total)

    return {
        "total_queries": total,
        "executed": exec_count,
        "unresolved": unresolved_count,
        "correct": correct_count,
        "incorrect": incorrect_count,
        "execution_error": error_count,
        "precision": round(precision, 4),
        "precision_ci_95": [round(p_low, 4), round(p_high, 4)],
        "coverage": round(coverage, 4),
        "coverage_ci_95": [round(c_low, 4), round(c_high, 4)],
        "mean_ex": round(mean_ex, 4),
        "mean_ex_ci_95": [round(ex_low, 4), round(ex_high, 4)],
        "selective_risk": round(selective_risk, 4),
        "unresolved_rate": round(unresolved_rate, 4),
    }


def aggregate_replicates_metrics(
    replicate_metrics: list[dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    policy_names = list(replicate_metrics[0].keys())
    agg: dict[str, Any] = {}

    for pol in policy_names:
        precisions = [r[pol]["precision"] for r in replicate_metrics]
        coverages = [r[pol]["coverage"] for r in replicate_metrics]
        exs = [r[pol]["mean_ex"] for r in replicate_metrics]
        risks = [r[pol]["selective_risk"] for r in replicate_metrics]
        unres = [r[pol]["unresolved_rate"] for r in replicate_metrics]

        def _stats(vals: list[float]) -> dict[str, float]:
            m = statistics.mean(vals)
            s = statistics.stdev(vals) if len(vals) > 1 else 0.0
            return {
                "mean": round(m, 4),
                "std": round(s, 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
            }

        agg[pol] = {
            "precision": _stats(precisions),
            "coverage": _stats(coverages),
            "mean_ex": _stats(exs),
            "selective_risk": _stats(risks),
            "unresolved_rate": _stats(unres),
            "replicates": [
                {
                    "rep": f"r{i+1}",
                    "executed": replicate_metrics[i][pol]["executed"],
                    "correct": replicate_metrics[i][pol]["correct"],
                    "precision": replicate_metrics[i][pol]["precision"],
                    "coverage": replicate_metrics[i][pol]["coverage"],
                    "mean_ex": replicate_metrics[i][pol]["mean_ex"],
                    "selective_risk": replicate_metrics[i][pol]["selective_risk"],
                }
                for i in range(len(replicate_metrics))
            ],
        }

    return agg


def analyze_verifier_stability(all_reps_cases: list[list[dict[str, Any]]]) -> dict[str, Any]:
    # Group by question_id across replicates
    q_decisions: dict[int, list[str]] = defaultdict(list)
    for rep_cases in all_reps_cases:
        for c in rep_cases:
            qid = c["question_id"]
            dec = c["verifier_decision"] or "NO_CANDIDATE"
            q_decisions[qid].append(dec)

    always_accept = 0
    always_reject = 0
    always_abstain = 0
    mixed_flips = 0

    for _qid, decs in q_decisions.items():
        unique_decs = set(decs)
        if len(unique_decs) == 1:
            dec = next(iter(unique_decs))
            if dec == "ACCEPT":
                always_accept += 1
            elif dec == "REJECT":
                always_reject += 1
            elif dec == "ABSTAIN":
                always_abstain += 1
            else:
                mixed_flips += 1
        else:
            mixed_flips += 1

    total = len(q_decisions)
    return {
        "total_questions": total,
        "always_accept_3_of_3": always_accept,
        "always_reject_3_of_3": always_reject,
        "always_abstain_3_of_3": always_abstain,
        "mixed_decision_flips": mixed_flips,
        "stability_rate": round((always_accept + always_reject + always_abstain) / total, 4) if total > 0 else 0.0,
    }


def analyze_confusion_and_checks(all_cases: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    # Candidates where verifier ran and we have ground truth
    cands = [c for c in all_cases if c["candidate_sql"] and c["verifier_decision"] is not None]

    ca = 0  # correct accepted
    cr = 0  # correct rejected
    cab = 0  # correct abstained
    ia = 0  # incorrect accepted
    ir = 0  # incorrect rejected
    iab = 0  # incorrect abstained

    dimension_rejections: Counter[str] = Counter()

    for c in cands:
        corr = c["execution_correct"] is True
        dec = c["verifier_decision"]

        if corr:
            if dec == "ACCEPT":
                ca += 1
            elif dec == "REJECT":
                cr += 1
            else:
                cab += 1
        else:
            if dec == "ACCEPT":
                ia += 1
            elif dec == "REJECT":
                ir += 1
            else:
                iab += 1

        if dec in ("REJECT", "ABSTAIN"):
            for dim, status in c["verifier_checks"].items():
                if status == "FAIL":
                    dimension_rejections[dim] += 1

    tot_acc = ca + ia
    prec = ca / tot_acc if tot_acc > 0 else 0.0
    tot_cands = len(cands)
    cov = tot_acc / tot_cands if tot_cands > 0 else 0.0
    risk = ia / tot_acc if tot_acc > 0 else 0.0

    cm = {
        "total_candidates": tot_cands,
        "correct_accepted": ca,
        "correct_rejected": cr,
        "correct_abstained": cab,
        "incorrect_accepted": ia,
        "incorrect_rejected": ir,
        "incorrect_abstained": iab,
        "accepted_precision": round(prec, 4),
        "coverage": round(cov, 4),
        "selective_risk": round(risk, 4),
    }

    checks = {
        "rejections_by_dimension": dict(dimension_rejections.most_common()),
        "total_rejections_abstained": cr + cab + ir + iab,
    }

    return cm, checks


def build_latency_cost_analysis(all_cases: list[dict[str, Any]]) -> dict[str, Any]:
    gen_lats = [c["generator_latency_ms"] for c in all_cases if c.get("generator_latency_ms")]
    ver_lats = [c["verifier_latency_ms"] for c in all_cases if c.get("verifier_latency_ms")]

    def _lat_stats(lats: list[float]) -> dict[str, float]:
        if not lats:
            return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
        s = sorted(lats)
        n = len(s)
        p50 = s[int(n * 0.50)]
        p95 = s[int(n * 0.95)]
        return {
            "mean_ms": round(statistics.mean(lats), 1),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
        }

    # Token and cost estimation based on gpt-5-mini pricing
    # Approx: generator: 1800 input tokens, 200 output tokens per case
    # Approx: verifier: 2200 input tokens, 350 output tokens per candidate
    total_queries = len(all_cases)
    total_verifier_calls = sum(1 for c in all_cases if c["candidate_sql"])

    # gpt-5-mini estimated rates: $0.15 / 1M input, $0.60 / 1M output
    est_gen_cost = total_queries * (1800 * 0.15e-6 + 200 * 0.60e-6)
    est_ver_cost = total_verifier_calls * (2200 * 0.15e-6 + 350 * 0.60e-6)

    return {
        "generator_latency": _lat_stats(gen_lats),
        "verifier_latency": _lat_stats(ver_lats),
        "total_queries_profiled": total_queries,
        "total_verifier_calls": total_verifier_calls,
        "estimated_tokens": {
            "generator_input_tokens": total_queries * 1800,
            "generator_output_tokens": total_queries * 200,
            "verifier_input_tokens": total_verifier_calls * 2200,
            "verifier_output_tokens": total_verifier_calls * 350,
        },
        "estimated_cost_usd": {
            "generator_cost_usd": round(est_gen_cost, 4),
            "verifier_cost_usd": round(est_ver_cost, 4),
            "total_cost_usd": round(est_gen_cost + est_ver_cost, 4),
        },
    }


def write_summary_markdown(
    summary_path: Path,
    policy_agg: dict[str, Any],
    stability: dict[str, Any],
    delta: float,
    cm: dict[str, Any],
) -> None:
    p1 = policy_agg["policy_1_p5_and_llm"]
    p0 = policy_agg["policy_0_p5"]
    p2 = policy_agg["policy_2_llm_solo"]
    p3 = policy_agg["policy_3_selective_recovery"]
    p4 = policy_agg["policy_4_p5_and_det"]
    p_all = policy_agg["accept_all"]

    md = f"""# Phase 8B: Verifier Generalization & Runtime Gate Validation Summary

## Key Findings

- **P8-A Benchmark Precision**: {P8A_BENCHMARK_PRECISION * 100:.2f}%
- **P8-B Dev100 Primary Gate (P5 + LLM Verifier)**:
  - Precision: {p1['precision']['mean'] * 100:.2f}% ± {p1['precision']['std'] * 100:.2f}% (range: {p1['precision']['min'] * 100:.2f}% – {p1['precision']['max'] * 100:.2f}%)
  - Coverage: {p1['coverage']['mean'] * 100:.2f}% ± {p1['coverage']['std'] * 100:.2f}%
  - Mean EX: {p1['mean_ex']['mean'] * 100:.2f}% ± {p1['mean_ex']['std'] * 100:.2f}%
  - Selective Risk: {p1['selective_risk']['mean'] * 100:.2f}%
  - Generalization Delta vs P8-A: {delta * 100:+.2f}%

## Policy Comparison (Mean Across 3 Replicates)

| Policy | Executed Precision | Coverage | Mean EX | Selective Risk | Unresolved Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Accept-All Control** | {p_all['precision']['mean'] * 100:.2f}% | {p_all['coverage']['mean'] * 100:.2f}% | {p_all['mean_ex']['mean'] * 100:.2f}% | {p_all['selective_risk']['mean'] * 100:.2f}% | {p_all['unresolved_rate']['mean'] * 100:.2f}% |
| **Policy 0: Existing P5** | {p0['precision']['mean'] * 100:.2f}% | {p0['coverage']['mean'] * 100:.2f}% | {p0['mean_ex']['mean'] * 100:.2f}% | {p0['selective_risk']['mean'] * 100:.2f}% | {p0['unresolved_rate']['mean'] * 100:.2f}% |
| **Policy 1: P5 + LLM Verifier (Primary)** | **{p1['precision']['mean'] * 100:.2f}%** | {p1['coverage']['mean'] * 100:.2f}% | {p1['mean_ex']['mean'] * 100:.2f}% | **{p1['selective_risk']['mean'] * 100:.2f}%** | {p1['unresolved_rate']['mean'] * 100:.2f}% |
| **Policy 2: Verifier Solo** | {p2['precision']['mean'] * 100:.2f}% | {p2['coverage']['mean'] * 100:.2f}% | {p2['mean_ex']['mean'] * 100:.2f}% | {p2['selective_risk']['mean'] * 100:.2f}% | {p2['unresolved_rate']['mean'] * 100:.2f}% |
| **Policy 3: Selective Recovery** | {p3['precision']['mean'] * 100:.2f}% | {p3['coverage']['mean'] * 100:.2f}% | {p3['mean_ex']['mean'] * 100:.2f}% | {p3['selective_risk']['mean'] * 100:.2f}% | {p3['unresolved_rate']['mean'] * 100:.2f}% |
| **Policy 4: P5 + Deterministic Verifier** | {p4['precision']['mean'] * 100:.2f}% | {p4['coverage']['mean'] * 100:.2f}% | {p4['mean_ex']['mean'] * 100:.2f}% | {p4['selective_risk']['mean'] * 100:.2f}% | {p4['unresolved_rate']['mean'] * 100:.2f}% |

## Verifier Decision Stability (3 Replicates on 100 Questions)

- **Total Questions**: {stability['total_questions']}
- **Always ACCEPT (3/3)**: {stability['always_accept_3_of_3']}
- **Always REJECT (3/3)**: {stability['always_reject_3_of_3']}
- **Always ABSTAIN (3/3)**: {stability['always_abstain_3_of_3']}
- **Decision Flips (Mixed)**: {stability['mixed_decision_flips']}
- **Stability Rate**: {stability['stability_rate'] * 100:.2f}%

## Confusion Matrix Summary (Aggregated across Replicates)

- Correct Accepted (TP): {cm['correct_accepted']}
- Correct Rejected/Abstained (FN): {cm['correct_rejected'] + cm['correct_abstained']}
- Incorrect Rejected/Abstained (TN): {cm['incorrect_rejected'] + cm['incorrect_abstained']}
- Incorrect Accepted (FP): {cm['incorrect_accepted']}
- Candidate-level Precision: {cm['accepted_precision'] * 100:.2f}%
- Selective Risk: {cm['selective_risk'] * 100:.2f}%
"""
    summary_path.write_text(md, encoding="utf-8")


async def execute_single_replicate(
    rep_name: str,
    out_dir: Path,
    cases: list[BenchmarkCaseBundle],
    db_infra: dict[str, Any],
    llm_verifier: LlmSemanticVerifier,
    deterministic_verifier: DeterministicSqlVerifier,
    prompt_builder: DirectSqlPromptBuilder,
    semaphore: asyncio.Semaphore,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rep_dir = out_dir / rep_name
    rep_dir.mkdir(parents=True, exist_ok=True)
    pred_file = rep_dir / "predictions.jsonl"
    metrics_file = rep_dir / "metrics.json"

    # Check if already completed or partially completed
    completed_map: dict[str, dict[str, Any]] = {}
    if pred_file.exists():
        with pred_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    completed_map[item["case_id"]] = item

        if len(completed_map) == 100:
            print(f"[{rep_name}] Found existing complete run with 100 cases.")
            loaded_cases = [completed_map[c.inference_case.case_id] for c in cases]
            if metrics_file.exists():
                rep_m = json.loads(metrics_file.read_text(encoding="utf-8"))
            else:
                rep_m = {
                    k: compute_policy_metrics(loaded_cases, k)
                    for k in loaded_cases[0]["policies"].keys()
                }
                metrics_file.write_text(json.dumps(rep_m, indent=2), encoding="utf-8")
            return loaded_cases, rep_m
        elif len(completed_map) > 0:
            print(f"[{rep_name}] Resuming run: {len(completed_map)}/100 cases already completed.")

    print(f"[{rep_name}] Starting replicate execution (100 cases)...")

    cases_to_run = [c for c in cases if c.inference_case.case_id not in completed_map]
    file_lock = asyncio.Lock()
    completed_count = len(completed_map)

    async def _run_case_task(bundle: BenchmarkCaseBundle) -> dict[str, Any]:
        nonlocal completed_count
        cid = bundle.inference_case.case_id
        if cid in completed_map:
            return completed_map[cid]

        async with semaphore:
            res = await run_single_case(
                case=bundle,
                db_infra=db_infra[bundle.inference_case.db_id],
                llm_verifier=llm_verifier,
                deterministic_verifier=deterministic_verifier,
                prompt_builder=prompt_builder,
                run_id=rep_name,
            )
            async with file_lock:
                completed_count += 1
                with pred_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(res) + "\n")
                    f.flush()
                print(
                    f"[{rep_name}] [{completed_count}/100] {cid} "
                    f"(P5={res['p5_status']}, Verifier={res['verifier_decision']}, "
                    f"Correct={res['execution_correct']})"
                )
            return res

    run_results = list(await asyncio.gather(*(_run_case_task(c) for c in cases_to_run)))
    for r in run_results:
        completed_map[r["case_id"]] = r

    rep_results = [completed_map[c.inference_case.case_id] for c in cases]

    rep_m = {
        k: compute_policy_metrics(rep_results, k)
        for k in rep_results[0]["policies"].keys()
    }
    metrics_file.write_text(json.dumps(rep_m, indent=2), encoding="utf-8")
    print(f"[{rep_name}] Replicate complete. Precision P1: {rep_m['policy_1_p5_and_llm']['precision']:.4f}")
    return rep_results, rep_m


async def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 8B Verifier Experiment")
    parser.add_argument("--dataset", type=str, default=str(DEFAULT_DATASET))
    parser.add_argument("--database-root", type=str, default=str(DEFAULT_DATABASE_ROOT))
    parser.add_argument("--tables-json", type=str, default=str(DEFAULT_TABLES_JSON))
    parser.add_argument("--prompt-directory", type=str, default=str(DEFAULT_PROMPT_DIRECTORY))
    parser.add_argument("--prompt-version", type=str, default="v001")
    parser.add_argument("--output", type=str, default=str(DEFAULT_RESULTS_ROOT))
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="Run with mock responses for testing pipeline")
    args = parser.parse_args()

    env_vars = load_env()
    api_key = env_vars.get("OPENAI_API_KEY")
    base_url = env_vars.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    active_model = args.model or env_vars.get("T2S_LLM_MODEL", "openai/gpt-oss-120b")

    if not api_key and not args.dry_run:
        raise ValueError("Missing OPENAI_API_KEY in environment or .env file.")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = Path(args.dataset)
    cases = load_benchmark_cases(dataset_path)
    if len(cases) != 100:
        raise ValueError(f"Expected exactly 100 Dev cases, got {len(cases)}")

    print(f"Loaded {len(cases)} Dev100 cases successfully.")

    from t2s.solver.chat_client import StructuredChatClient
    from t2s.solver.solver_response import StructuredChatResponse

    class MockDryRunChatClient(StructuredChatClient):
        async def generate_structured_response(
            self,
            messages: list[dict[str, str]],
            response_schema: dict[str, Any],
            model_name: str,
            reasoning_effort: str | None = None,
            max_output_tokens: int = 1500,
        ) -> StructuredChatResponse:
            if "sql" in response_schema.get("properties", {}):
                return StructuredChatResponse(
                    content={
                        "sql": "SELECT 1",
                        "referenced_tables": [],
                        "referenced_columns": [],
                        "expected_columns": ["1"],
                        "assumptions": [],
                        "unresolved": [],
                    },
                    model_name=model_name,
                    elapsed_ms=50,
                )
            else:
                pass_chk = {
                    "status": "PASS",
                    "short_reason": "Dry run pass",
                    "question_evidence": "",
                    "sql_evidence": "",
                }
                return StructuredChatResponse(
                    content={
                        "projection": pass_chk,
                        "aggregation_and_grain": pass_chk,
                        "filters_and_values": pass_chk,
                        "join_semantics": pass_chk,
                        "ordering_and_limit": pass_chk,
                        "null_semantics": pass_chk,
                        "schema_reference": pass_chk,
                        "decision": "ACCEPT",
                    },
                    model_name=model_name,
                    elapsed_ms=30,
                )

    chat_client: StructuredChatClient = (
        MockDryRunChatClient()
        if args.dry_run
        else OpenAICompatibleChatClient(
            base_url=base_url,
            api_key=api_key or "mock-key",
        )
    )
    llm_verifier = LlmSemanticVerifier(chat_client=chat_client, model_name=active_model)
    deterministic_verifier = DeterministicSqlVerifier()
    prompt_builder = DirectSqlPromptBuilder(
        prompt_directory=Path(args.prompt_directory),
        prompt_version=args.prompt_version,
    )

    db_infra = prebuild_database_infrastructure(
        case_bundles=cases,
        database_root=Path(args.database_root),
        tables_json_path=Path(args.tables_json),
        chat_client=chat_client,
        model_name=active_model,
        prompt_directory=Path(args.prompt_directory),
        prompt_version=args.prompt_version,
    )

    semaphore = asyncio.Semaphore(args.concurrency)

    all_reps_cases: list[list[dict[str, Any]]] = []
    replicate_metrics: list[dict[str, Any]] = []

    for rep_name in REPLICATES:
        rep_results, rep_m = await execute_single_replicate(
            rep_name=rep_name,
            out_dir=out_dir,
            cases=cases,
            db_infra=db_infra,
            llm_verifier=llm_verifier,
            deterministic_verifier=deterministic_verifier,
            prompt_builder=prompt_builder,
            semaphore=semaphore,
        )
        all_reps_cases.append(rep_results)
        replicate_metrics.append(rep_m)

    # Cross-replicate aggregations
    print("Computing cross-replicate policy aggregations...")
    policy_agg = aggregate_replicates_metrics(replicate_metrics)
    (out_dir / "policy_comparison.json").write_text(json.dumps(policy_agg, indent=2), encoding="utf-8")

    stability = analyze_verifier_stability(all_reps_cases)
    (out_dir / "verifier_stability.json").write_text(json.dumps(stability, indent=2), encoding="utf-8")

    all_cases_flat = [c for rep in all_reps_cases for c in rep]
    cm, checks = analyze_confusion_and_checks(all_cases_flat)
    (out_dir / "confusion_matrices.json").write_text(json.dumps(cm, indent=2), encoding="utf-8")
    (out_dir / "failure_slice_analysis.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")

    lat_cost = build_latency_cost_analysis(all_cases_flat)
    (out_dir / "latency_cost.json").write_text(json.dumps(lat_cost, indent=2), encoding="utf-8")

    p1_mean_prec = policy_agg["policy_1_p5_and_llm"]["precision"]["mean"]
    gen_delta = p1_mean_prec - P8A_BENCHMARK_PRECISION

    write_summary_markdown(
        summary_path=out_dir / "summary.md",
        policy_agg=policy_agg,
        stability=stability,
        delta=gen_delta,
        cm=cm,
    )

    manifest = {
        "phase": "P8-B",
        "description": "Verifier Generalization & Controlled Runtime Gate Validation",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "dataset": str(dataset_path),
        "total_cases": len(cases),
        "replicates": REPLICATES,
        "provider": "openai_compatible",
        "model": active_model,
        "prompt_version": args.prompt_version,
        "verifier_prompt_version": "v001",
        "verifier_prompt_sha256": "6d28add0fd23876db02f703a086aceff35eed01efd5d73736baf893010b2becf",
        "eval_v1_used": False,
        "final_holdout_used": False,
        "gold_exposed_to_verifier": False,
        "p8a_benchmark_precision": P8A_BENCHMARK_PRECISION,
        "p8b_primary_gate_mean_precision": p1_mean_prec,
        "generalization_delta": round(gen_delta, 4),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Phase 8B experiment execution and artifact generation completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
