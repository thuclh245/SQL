# ruff: noqa: E501
import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases
from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.evaluation.verifier_evaluation import (
    build_confusion_matrix,
    evaluate_check_effectiveness,
    evaluate_counterfactual_policies,
    evaluate_failure_slice_detection,
    evaluate_origin_analysis,
    evaluate_policy_decisions,
)
from t2s.grounding import GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder
from t2s.verification.contracts import (
    VerificationDecision,
    VerificationResult,
    VerifierCandidateRecord,
)
from t2s.verification.deterministic_verifier import DeterministicSqlVerifier
from t2s.verification.llm_semantic_verifier import LlmSemanticVerifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results"
P7B_ROOT = RESULTS_ROOT / "p7b_prompt_calibration"
P8A_ROOT = RESULTS_ROOT / "p8a_semantic_verifier"
PILOT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_pilot_v1.jsonl"
TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
CONTROL_RUNS = ["p7b_control_r1", "p7b_control_r2", "p7b_control_r3"]


def load_env() -> dict[str, str]:
    env_file = PROJECT_ROOT / ".env"
    env_vars = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


def build_grounding_cache(pilot_bundles: list[Any]) -> dict[str, Any]:
    """Prebuilds GroundingContext and formatted schema strings per DB to avoid redundant retrieval."""
    cache: dict[str, dict[str, Any]] = {}
    user = UserIdentity(user_id="verifier", roles=frozenset(["benchmark"]))
    prompt_builder = DirectSqlPromptBuilder()

    for bundle in pilot_bundles:
        cid = bundle.inference_case.case_id
        db_id = bundle.inference_case.db_id
        if db_id not in cache:
            catalog_tables = load_bird_catalog_tables(db_id=db_id, tables_json_path=TABLES_JSON)
            catalog = InMemoryCatalog()
            catalog.upsert_tables(catalog_tables)

            doc_builder = CatalogSearchDocumentBuilder()
            docs = [doc for t in catalog_tables for doc in doc_builder.build_search_documents(t)]
            retriever = SchemaRetriever(InMemorySchemaSearch(docs))
            auth_resources = [
                AuthorizedSqlResource(catalog_fqn=t.table_fqn, sql_identifier=t.sql_identifier)
                for t in catalog_tables
                if t.sql_identifier
            ]
            from t2s.benchmark.runtime_factory import AllTablesBenchmarkAccessPolicy
            auth_service = AuthorizationService(AllTablesBenchmarkAccessPolicy(auth_resources))
            builder = GroundingContextBuilder(
                catalog=catalog,
                schema_retriever=retriever,
                authorization_service=auth_service,
            )
            cache[db_id] = {
                "builder": builder,
                "user": user,
                "catalog_tables": catalog_tables,
                "case_contexts": {},
            }

        # Build context for this case
        db_cache = cache[db_id]
        builder = db_cache["builder"]
        from t2s.benchmark.runtime_factory import build_query_request_from_benchmark_case
        q_req = build_query_request_from_benchmark_case(bundle, evidence=bundle.inference_case.evidence)
        ctx = builder.build_grounding_context(q_req, db_cache["user"])
        formatted_schema = prompt_builder._format_authorized_schema(ctx)
        auth_tables = [t.fqn for t in ctx.tables]
        auth_cols = {t.sql_identifier: [c.name for c in t.columns] for t in ctx.tables if t.sql_identifier}

        db_cache["case_contexts"][cid] = {
            "formatted_schema": formatted_schema,
            "authorized_tables": auth_tables,
            "authorized_columns": auth_cols,
            "glossary": [f"{g.term}: {g.definition}" for g in ctx.glossary_hits],
            "value_bindings": [f"{v.phrase} -> {v.column_fqn} = {v.value}" for v in ctx.value_bindings],
        }

    return cache


def extract_verifier_candidates(
    pilot_bundles: dict[str, Any],
    grounding_cache: dict[str, Any],
) -> list[VerifierCandidateRecord]:
    records: list[VerifierCandidateRecord] = []

    for run_id in CONTROL_RUNS:
        run_dir = P7B_ROOT / run_id
        cases_file = run_dir / "cases.jsonl"
        shadow_file = run_dir / "shadow_results.json"

        cases = []
        with cases_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))

        shadow_data = json.loads(shadow_file.read_text(encoding="utf-8")) if shadow_file.exists() else {}
        shadow_map = {c["case_id"]: c for c in shadow_data.get("cases", [])}

        for c in cases:
            cid = c["case_id"]
            bundle = pilot_bundles.get(cid)
            if not bundle:
                continue

            status = c.get("runtime_status")
            candidate_sql = None
            origin = None
            is_correct = False

            if status == "SUCCESS":
                candidate_sql = c.get("generated_sql")
                origin = "EXECUTED"
                is_correct = bool(c.get("execution_correct"))
            elif status == "UNRESOLVED":
                candidate_sql = c.get("rejected_candidate_sql")
                origin = "REJECTED_BY_P5"
                sh_case = shadow_map.get(cid)
                if sh_case:
                    is_correct = sh_case.get("status") == "SHADOW_CORRECT" or sh_case.get("matches_gold") is True

            if not candidate_sql or not origin:
                continue

            db_id = c["db_id"]
            ctx_data = grounding_cache[db_id]["case_contexts"][cid]

            record = VerifierCandidateRecord(
                candidate_id=f"{run_id}_{cid}",
                source_run_id=run_id,
                case_id=cid,
                question_id=c.get("question_id"),
                db_id=db_id,
                t2s_stratum=c.get("t2s_stratum"),
                bird_difficulty=c.get("bird_difficulty"),
                question=bundle.inference_case.question,
                evidence=bundle.inference_case.evidence or "",
                dialect="sqlite",
                grounding_context=ctx_data,
                candidate_sql=candidate_sql,
                runtime_origin=origin,
                evaluator_correctness_label=is_correct,
                gold_sql=bundle.scoring_gold.official_sql,
            )
            records.append(record)

    return records


async def evaluate_llm_candidates(
    verifier: LlmSemanticVerifier,
    candidates: list[VerifierCandidateRecord],
    concurrency: int = 5,
) -> list[tuple[VerifierCandidateRecord, VerificationResult, float, int, int]]:
    sem = asyncio.Semaphore(concurrency)

    async def _verify_one(cand: VerifierCandidateRecord) -> tuple[VerifierCandidateRecord, VerificationResult, float, int, int]:
        inp = cand.to_verification_input()
        t0 = time.perf_counter()
        res = await verifier.verify(inp)
        elapsed = time.perf_counter() - t0
        # Simulated or extracted tokens
        return cand, res, elapsed, 0, 0

    tasks = []
    for cand in candidates:
        async def _wrapped(c: VerifierCandidateRecord = cand) -> tuple[VerifierCandidateRecord, VerificationResult, float, int, int]:
            async with sem:
                return await _verify_one(c)
        tasks.append(_wrapped())

    batch_results = await asyncio.gather(*tasks)
    return list(batch_results)


async def main() -> None:
    parser = argparse.ArgumentParser(description="P8-A Offline Semantic SQL Verifier Prototype")
    parser.add_argument("--concurrency", type=int, default=5, help="LLM verification concurrency")
    parser.add_argument("--model", type=str, default=None, help="Verifier LLM model name")
    parser.add_argument("--base-url", type=str, default=None, help="Verifier base URL")
    parser.add_argument("--api-key", type=str, default=None, help="Verifier API key")
    args = parser.parse_args()

    env = load_env()
    api_key = (
        args.api_key
        or os.getenv("T2S_VERIFIER_API_KEY")
        or env.get("T2S_VERIFIER_API_KEY")
        or os.getenv("T2S_LLM_API_KEY")
        or env.get("T2S_LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or env.get("OPENAI_API_KEY")
    )
    if not api_key:
        print("ERROR: API key not provided and not found in .env or environment.")
        sys.exit(1)

    base_url = (
        args.base_url
        or os.getenv("T2S_VERIFIER_BASE_URL")
        or env.get("T2S_VERIFIER_BASE_URL")
        or os.getenv("T2S_LLM_BASE_URL")
        or env.get("T2S_LLM_BASE_URL")
        or "https://api.openai.com/v1"
    )
    model = (
        args.model
        or os.getenv("T2S_VERIFIER_MODEL")
        or env.get("T2S_VERIFIER_MODEL")
        or os.getenv("T2S_LLM_MODEL")
        or env.get("T2S_LLM_MODEL")
        or "gpt-5-mini"
    )

    P8A_ROOT.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Starting P8-A Offline Semantic SQL Verifier Prototype")
    print(f"Target Output Directory: {P8A_ROOT}")
    print(f"Verifier Model: {model} ({base_url})")
    print("=" * 70)

    # 1. Load benchmark pilot cases
    print("Loading benchmark pilot cases...")
    pilot_list = load_benchmark_cases(PILOT_DATASET, BenchmarkCaseFilter(executable_only=True))
    pilot_bundles = {b.inference_case.case_id: b for b in pilot_list}
    print(f"Loaded {len(pilot_bundles)} executable pilot cases.")

    # 2. Build grounding cache
    print("Building grounding contexts...")
    grounding_cache = build_grounding_cache(pilot_list)

    # 3. Extract candidate records
    print("Extracting candidate records from frozen P7-B Control replicates...")
    candidates = extract_verifier_candidates(pilot_bundles, grounding_cache)
    print(f"Extracted {len(candidates)} candidates across replicates:")
    r_counts = Counter(c.source_run_id for c in candidates)
    for r_id, count in sorted(r_counts.items()):
        exec_count = sum(1 for c in candidates if c.source_run_id == r_id and c.runtime_origin == "EXECUTED")
        rej_count = sum(1 for c in candidates if c.source_run_id == r_id and c.runtime_origin == "REJECTED_BY_P5")
        corr_count = sum(1 for c in candidates if c.source_run_id == r_id and c.evaluator_correctness_label)
        print(f"  - {r_id}: total={count} (executed={exec_count}, rejected={rej_count}, correct={corr_count})")

    # Write verifier_candidates.jsonl
    candidates_file = P8A_ROOT / "verifier_candidates.jsonl"
    with candidates_file.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(c.model_dump_json() + "\n")
    print(f"Saved candidate dataset to {candidates_file}")

    # 4. Run Deterministic Verifier on all candidates
    print("\nRunning Deterministic AST Verifier on all candidates...")
    det_verifier = DeterministicSqlVerifier()
    det_results: list[VerificationResult] = []
    for c in candidates:
        inp = c.to_verification_input()
        res = await det_verifier.verify(inp)
        det_results.append(res)
    print("Deterministic verification complete.")

    # 5. Run LLM Semantic Verifier
    chat_client = OpenAICompatibleChatClient(
        base_url=base_url,
        api_key=api_key,
        request_timeout_seconds=120.0,
    )
    llm_verifier = LlmSemanticVerifier(
        chat_client=chat_client,
        model_name=model,
        prompt_version="v001",
    )
    print(f"Prompt hash (v001 SHA-256): {llm_verifier.prompt_sha256}")

    # Check if existing verifier_results.jsonl exists
    results_file = P8A_ROOT / "verifier_results.jsonl"
    existing_results_map: dict[str, dict[str, Any]] = {}
    if results_file.exists():
        with results_file.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    existing_results_map[item["candidate_id"]] = item
        print(f"Found {len(existing_results_map)} existing verification results in {results_file}.")

    # Evaluate candidates
    pending_candidates = [c for c in candidates if c.candidate_id not in existing_results_map]
    if pending_candidates:
        print(f"Evaluating {len(pending_candidates)} pending candidates with LLM verifier (concurrency={args.concurrency})...")
        new_batch = await evaluate_llm_candidates(llm_verifier, pending_candidates, concurrency=args.concurrency)
        with results_file.open("a", encoding="utf-8") as f:
            for cand, res, elapsed, p_tokens, o_tokens in new_batch:
                row = {
                    "candidate_id": cand.candidate_id,
                    "source_run_id": cand.source_run_id,
                    "case_id": cand.case_id,
                    "runtime_origin": cand.runtime_origin,
                    "evaluator_correctness_label": cand.evaluator_correctness_label,
                    "elapsed_seconds": round(elapsed, 3),
                    "prompt_tokens": p_tokens,
                    "output_tokens": o_tokens,
                    "result": res.model_dump(),
                }
                existing_results_map[cand.candidate_id] = row
                f.write(json.dumps(row) + "\n")
        print("LLM verification inference complete.")
    else:
        print("All candidates already verified in verifier_results.jsonl.")

    # Assemble ordered LLM results matching `candidates`
    llm_results: list[VerificationResult] = []
    latencies: list[float] = []
    for c in candidates:
        row = existing_results_map[c.candidate_id]
        llm_results.append(VerificationResult.model_validate(row["result"]))
        elapsed_val = row.get("elapsed_seconds")
        if isinstance(elapsed_val, (int, float)):
            latencies.append(float(elapsed_val))

    # 6. Evaluate Replicate Splits: r1 (Calibration) vs r2, r3 (Validation)
    r1_cands = [c for c in candidates if c.source_run_id == "p7b_control_r1"]
    r1_llm_res = [r for c, r in zip(candidates, llm_results, strict=True) if c.source_run_id == "p7b_control_r1"]
    r1_det_res = [r for c, r in zip(candidates, det_results, strict=True) if c.source_run_id == "p7b_control_r1"]

    val_cands = [c for c in candidates if c.source_run_id in ("p7b_control_r2", "p7b_control_r3")]
    val_llm_res = [r for c, r in zip(candidates, llm_results, strict=True) if c.source_run_id in ("p7b_control_r2", "p7b_control_r3")]
    val_det_res = [r for c, r in zip(candidates, det_results, strict=True) if c.source_run_id in ("p7b_control_r2", "p7b_control_r3")]

    # 7. Compute Confusion Matrices
    cm_pooled_llm = build_confusion_matrix(candidates, llm_results)
    cm_r1_llm = build_confusion_matrix(r1_cands, r1_llm_res)
    cm_val_llm = build_confusion_matrix(val_cands, val_llm_res)

    cm_pooled_det = build_confusion_matrix(candidates, det_results)
    cm_r1_det = build_confusion_matrix(r1_cands, r1_det_res)
    cm_val_det = build_confusion_matrix(val_cands, val_det_res)

    confusion_matrices = {
        "llm_verifier_pooled": cm_pooled_llm.to_dict(),
        "llm_verifier_r1_calibration": cm_r1_llm.to_dict(),
        "llm_verifier_validation_r2_r3": cm_val_llm.to_dict(),
        "deterministic_verifier_pooled": cm_pooled_det.to_dict(),
        "deterministic_verifier_r1": cm_r1_det.to_dict(),
        "deterministic_verifier_val": cm_val_det.to_dict(),
    }
    (P8A_ROOT / "confusion_matrix.json").write_text(json.dumps(confusion_matrices, indent=2), encoding="utf-8")

    # 8. Compute Risk-Coverage & Decision Policies (A, B, C)
    risk_coverage = {
        "policy_a_all_checks_pass": {
            "pooled": evaluate_policy_decisions(candidates, llm_results, "Policy A").to_dict(),
            "r1": evaluate_policy_decisions(r1_cands, r1_llm_res, "Policy A").to_dict(),
            "val_r2_r3": evaluate_policy_decisions(val_cands, val_llm_res, "Policy A").to_dict(),
        },
        "policy_b_max_1_unknown": {
            "pooled": evaluate_policy_decisions(candidates, llm_results, "Policy B").to_dict(),
            "r1": evaluate_policy_decisions(r1_cands, r1_llm_res, "Policy B").to_dict(),
            "val_r2_r3": evaluate_policy_decisions(val_cands, val_llm_res, "Policy B").to_dict(),
        },
        "policy_c_no_fail_any_unknown": {
            "pooled": evaluate_policy_decisions(candidates, llm_results, "Policy C").to_dict(),
            "r1": evaluate_policy_decisions(r1_cands, r1_llm_res, "Policy C").to_dict(),
            "val_r2_r3": evaluate_policy_decisions(val_cands, val_llm_res, "Policy C").to_dict(),
        },
    }
    (P8A_ROOT / "risk_coverage.json").write_text(json.dumps(risk_coverage, indent=2), encoding="utf-8")

    # 9. Compute Check Effectiveness
    check_effectiveness = {
        "pooled": evaluate_check_effectiveness(candidates, llm_results),
        "r1_calibration": evaluate_check_effectiveness(r1_cands, r1_llm_res),
        "val_r2_r3": evaluate_check_effectiveness(val_cands, val_llm_res),
    }
    (P8A_ROOT / "check_effectiveness.json").write_text(json.dumps(check_effectiveness, indent=2), encoding="utf-8")

    # 10. Origin Analysis (EXECUTED vs REJECTED_BY_P5)
    origin_analysis = {
        "pooled": evaluate_origin_analysis(candidates, llm_results),
        "r1_calibration": evaluate_origin_analysis(r1_cands, r1_llm_res),
        "val_r2_r3": evaluate_origin_analysis(val_cands, val_llm_res),
    }
    (P8A_ROOT / "origin_analysis.json").write_text(json.dumps(origin_analysis, indent=2), encoding="utf-8")

    # 11. Failure Slice Detection (Cross-tab vs P7-C error categories)
    failure_slices = {
        "pooled": evaluate_failure_slice_detection(candidates, llm_results),
        "r1_calibration": evaluate_failure_slice_detection(r1_cands, r1_llm_res),
        "val_r2_r3": evaluate_failure_slice_detection(val_cands, val_llm_res),
    }
    (P8A_ROOT / "failure_slices.json").write_text(json.dumps(failure_slices, indent=2), encoding="utf-8")

    # 12. Counterfactual Policies Comparison Table
    # Mean metrics across replicates (total_benchmark_requests per run = 85)
    counterfactual_policies = {
        "pooled": evaluate_counterfactual_policies(candidates, llm_results, total_benchmark_requests=85 * 3),
        "r1_calibration": evaluate_counterfactual_policies(r1_cands, r1_llm_res, total_benchmark_requests=85),
        "val_r2_r3": evaluate_counterfactual_policies(val_cands, val_llm_res, total_benchmark_requests=85 * 2),
    }
    # Deterministic verifier policy comparison
    det_policies = evaluate_counterfactual_policies(candidates, det_results, total_benchmark_requests=85 * 3)
    counterfactual_policies["deterministic_verifier"] = det_policies["llm_verifier"]  # solo verifier metrics
    (P8A_ROOT / "counterfactual_policies.json").write_text(json.dumps(counterfactual_policies, indent=2), encoding="utf-8")

    # 13. Stability Analysis across repeated cases
    case_to_reps: dict[str, list[VerificationDecision]] = defaultdict(list)
    for c, r in zip(candidates, llm_results, strict=True):
        case_to_reps[c.case_id].append(r.decision)

    cases_in_all_3 = [cid for cid, decs in case_to_reps.items() if len(decs) == 3]
    full_agreement_count = sum(1 for cid in cases_in_all_3 if len(set(case_to_reps[cid])) == 1)
    stability_data = {
        "total_unique_cases": len(case_to_reps),
        "cases_evaluated_3_times": len(cases_in_all_3),
        "full_decision_agreement_cases": full_agreement_count,
        "stability_rate": round(full_agreement_count / len(cases_in_all_3), 4) if cases_in_all_3 else 0.0,
    }
    (P8A_ROOT / "stability.json").write_text(json.dumps(stability_data, indent=2), encoding="utf-8")

    # 14. Latency Statistics
    latencies.sort()
    latency_stats = {
        "count": len(latencies),
        "mean_seconds": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "p50_seconds": round(latencies[len(latencies) // 2], 3) if latencies else 0.0,
        "p95_seconds": round(latencies[int(len(latencies) * 0.95)], 3) if latencies else 0.0,
    }

    # 15. Reproducibility Manifest
    manifest = {
        "phase": "P8-A",
        "description": "Offline Semantic SQL Verifier Prototype",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "provider": "openai_compatible",
        "model": model,
        "base_url": base_url,
        "prompt_version": "v001",
        "prompt_sha256": llm_verifier.prompt_sha256,
        "evidence_sources": CONTROL_RUNS,
        "total_candidates_analyzed": len(candidates),
        "eval_v1_used": False,
        "final_holdout_used": False,
        "gold_exposed_to_verifier": False,
        "latency_stats": latency_stats,
    }
    (P8A_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Determine Phase 8A Architecture Decision
    # Thresholds: Accepted Precision >= 70% with useful coverage -> VERIFIER_PROMISING
    # If deterministic performs similarly -> DETERMINISTIC_CHECKS_SUFFICIENT
    # If verifier cannot separate -> VERIFIER_TOO_WEAK
    pooled_prec = cm_pooled_llm.accepted_precision
    pooled_cov = cm_pooled_llm.coverage
    p5_and_ver_prec = counterfactual_policies["pooled"]["p5_and_llm_verifier"]["accepted_precision"]
    p5_and_ver_cov = counterfactual_policies["pooled"]["p5_and_llm_verifier"]["coverage"]

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print(f"LLM Verifier Solo Accepted Precision: {pooled_prec*100:.2f}% (Coverage: {pooled_cov*100:.2f}%)")
    print(f"P5 + LLM Verifier Accepted Precision: {p5_and_ver_prec*100:.2f}% (Coverage: {p5_and_ver_cov*100:.2f}%)")
    print(f"Deterministic Verifier Accepted Precision: {cm_pooled_det.accepted_precision*100:.2f}% (Coverage: {cm_pooled_det.coverage*100:.2f}%)")
    print("=" * 70)

    # 16. Generate summary.md
    summary_md = f"""# P8-A Offline Semantic SQL Verifier — Summary

## Core Metrics Comparison

| Policy | Accepted Precision | Coverage | Selective Risk | EX (Simulated) | Incorrect Execution Rate |
|---|---:|---:|---:|---:|---:|
| **Baseline 0: Accept All** | {counterfactual_policies['pooled']['accept_all']['accepted_precision']*100:.2f}% | 100.0% | {counterfactual_policies['pooled']['accept_all']['selective_risk']*100:.2f}% | {counterfactual_policies['pooled']['accept_all']['ex']*100:.2f}% | {counterfactual_policies['pooled']['accept_all']['incorrect_execution_rate']*100:.2f}% |
| **Baseline 1: Existing P5** | {counterfactual_policies['pooled']['existing_p5']['accepted_precision']*100:.2f}% | {counterfactual_policies['pooled']['existing_p5']['coverage']*100:.2f}% | {counterfactual_policies['pooled']['existing_p5']['selective_risk']*100:.2f}% | {counterfactual_policies['pooled']['existing_p5']['ex']*100:.2f}% | {counterfactual_policies['pooled']['existing_p5']['incorrect_execution_rate']*100:.2f}% |
| **Baseline 2: Deterministic Verifier** | {counterfactual_policies['deterministic_verifier']['accepted_precision']*100:.2f}% | {counterfactual_policies['deterministic_verifier']['coverage']*100:.2f}% | {counterfactual_policies['deterministic_verifier']['selective_risk']*100:.2f}% | {counterfactual_policies['deterministic_verifier']['ex']*100:.2f}% | {counterfactual_policies['deterministic_verifier']['incorrect_execution_rate']*100:.2f}% |
| **LLM Semantic Verifier (Solo)** | {counterfactual_policies['pooled']['llm_verifier']['accepted_precision']*100:.2f}% | {counterfactual_policies['pooled']['llm_verifier']['coverage']*100:.2f}% | {counterfactual_policies['pooled']['llm_verifier']['selective_risk']*100:.2f}% | {counterfactual_policies['pooled']['llm_verifier']['ex']*100:.2f}% | {counterfactual_policies['pooled']['llm_verifier']['incorrect_execution_rate']*100:.2f}% |
| **P5 AND LLM Verifier** | {counterfactual_policies['pooled']['p5_and_llm_verifier']['accepted_precision']*100:.2f}% | {counterfactual_policies['pooled']['p5_and_llm_verifier']['coverage']*100:.2f}% | {counterfactual_policies['pooled']['p5_and_llm_verifier']['selective_risk']*100:.2f}% | {counterfactual_policies['pooled']['p5_and_llm_verifier']['ex']*100:.2f}% | {counterfactual_policies['pooled']['p5_and_llm_verifier']['incorrect_execution_rate']*100:.2f}% |

## Confusion Matrix (LLM Verifier Pooled, N={cm_pooled_llm.total_candidates})
- **Correct Accepted**: {cm_pooled_llm.correct_accepted}
- **Correct Rejected**: {cm_pooled_llm.correct_rejected}
- **Correct Abstained**: {cm_pooled_llm.correct_abstained}
- **Incorrect Accepted (False Acceptance)**: {cm_pooled_llm.incorrect_accepted}
- **Incorrect Rejected**: {cm_pooled_llm.incorrect_rejected}
- **Incorrect Abstained**: {cm_pooled_llm.incorrect_abstained}

## Dimension Check Effectiveness Ranking
"""
    for dim in check_effectiveness["pooled"]["ranking"]:
        d_stat = check_effectiveness["pooled"]["dimensions"][dim]
        summary_md += f"- **`{dim}`**: Fail Precision = {d_stat['fail_precision']*100:.1f}% ({d_stat['fail_when_incorrect']}/{d_stat['fail_count']} fails on incorrect SQL, false alarms: {d_stat['fail_when_correct']})\n"

    summary_md += f"""
## Candidate Origin Analysis
- **Executed Origin (originally SUCCESS in P5)**:
  - Candidates: {origin_analysis['pooled']['executed_origin']['total_candidates']}
  - Accepted Precision: {origin_analysis['pooled']['executed_origin']['accepted_precision']*100:.2f}%
  - Coverage: {origin_analysis['pooled']['executed_origin']['coverage']*100:.2f}%
  - Selective Risk: {origin_analysis['pooled']['executed_origin']['selective_risk']*100:.2f}%
- **Rejected Origin (originally UNRESOLVED in P5)**:
  - Candidates: {origin_analysis['pooled']['rejected_origin']['total_candidates']}
  - Accepted Precision: {origin_analysis['pooled']['rejected_origin']['accepted_precision']*100:.2f}%
  - Coverage: {origin_analysis['pooled']['rejected_origin']['coverage']*100:.2f}%
  - Selective Risk: {origin_analysis['pooled']['rejected_origin']['selective_risk']*100:.2f}%

## Stability & Latency
- **Decision Stability Rate**: {stability_data['stability_rate']*100:.1f}% across 3-replicate cases
- **Mean Latency**: {latency_stats['mean_seconds']}s (P50: {latency_stats['p50_seconds']}s, P95: {latency_stats['p95_seconds']}s)
"""
    (P8A_ROOT / "summary.md").write_text(summary_md, encoding="utf-8")
    print(f"Summary written to {P8A_ROOT / 'summary.md'}")


if __name__ == "__main__":
    asyncio.run(main())
