# ruff: noqa: E501
"""Phase 8C: Model-Shift Deconfounding & Verifier Backend Validation.

Holding candidate SQL constant from P8-B (N=286 candidates across 300 trials),
evaluates multiple verifier backends:
- Arm V0: Deterministic Verifier (baseline AST/schema)
- Arm V1: openai/gpt-oss-120b (same-model verifier)
- Arm V2: openai/gpt-5-mini (cross-family verifier)

Measures causal impact of verifier backend on precision, selective risk,
failure slice leakage, and pairwise agreement.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from t2s.evaluation.uncertainty_diagnostics import wilson_score_interval
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.verification.contracts import (
    SEMANTIC_CHECK_DIMENSIONS,
    VerificationInput,
)
from t2s.verification.deterministic_verifier import DeterministicSqlVerifier
from t2s.verification.llm_semantic_verifier import LlmSemanticVerifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results" / "p8c_verifier_backend_validation"
FROZEN_CANDIDATES_PATH = RESULTS_DIR / "frozen_candidates.jsonl"


def compute_metrics(
    total_trials: int,
    no_candidate_count: int,
    evaluated_candidates: list[dict[str, Any]],
    decision_key: str,
) -> dict[str, Any]:
    """Compute precision, coverage, selective risk, and confusion metrics."""
    n_evaluated = len(evaluated_candidates)
    assert n_evaluated + no_candidate_count == total_trials

    # Mutually exclusive buckets
    ca = 0  # correct accepted (TP)
    ia = 0  # incorrect accepted (FP)
    cr = 0  # correct rejected (FN-reject)
    ir = 0  # incorrect rejected (TN-reject)
    cab = 0  # correct abstained (FN-abstain)
    iab = 0  # incorrect abstained (TN-abstain)

    for c in evaluated_candidates:
        dec = c[decision_key]
        is_corr = c["evaluator_metadata"]["execution_correctness"]
        if dec == "ACCEPT":
            if is_corr:
                ca += 1
            else:
                ia += 1
        elif dec == "REJECT":
            if is_corr:
                cr += 1
            else:
                ir += 1
        else:  # ABSTAIN or other
            if is_corr:
                cab += 1
            else:
                iab += 1

    total_accepted = ca + ia
    total_withheld = cr + ir + cab + iab
    total_correct = ca + cr + cab
    total_incorrect = ia + ir + iab

    precision = ca / total_accepted if total_accepted > 0 else 0.0
    selective_risk = ia / total_accepted if total_accepted > 0 else 0.0
    coverage = total_accepted / total_trials
    candidate_coverage = total_accepted / n_evaluated if n_evaluated > 0 else 0.0
    false_withhold_rate = (cr + cab) / total_correct if total_correct > 0 else 0.0
    pure_false_reject_rate = cr / total_correct if total_correct > 0 else 0.0
    specificity = (ir + iab) / total_incorrect if total_incorrect > 0 else 0.0
    pure_reject_specificity = ir / total_incorrect if total_incorrect > 0 else 0.0

    ci_low, ci_high = wilson_score_interval(ca, total_accepted, confidence=0.95) if total_accepted > 0 else (0.0, 0.0)

    return {
        "candidate_evaluations": n_evaluated,
        "trials_without_candidate": no_candidate_count,
        "total_trials": total_trials,
        "total_accepted": total_accepted,
        "total_withheld": total_withheld,
        "total_correct": total_correct,
        "total_incorrect": total_incorrect,
        "correct_accepted": ca,
        "incorrect_accepted": ia,
        "correct_rejected": cr,
        "incorrect_rejected": ir,
        "correct_abstained": cab,
        "incorrect_abstained": iab,
        "precision": round(precision, 4),
        "precision_ci95": [round(ci_low, 4), round(ci_high, 4)],
        "selective_risk": round(selective_risk, 4),
        "coverage": round(coverage, 4),
        "candidate_coverage": round(candidate_coverage, 4),
        "false_withhold_rate": round(false_withhold_rate, 4),
        "pure_false_reject_rate": round(pure_false_reject_rate, 4),
        "true_withhold_rate": round(specificity, 4),
        "pure_reject_specificity": round(pure_reject_specificity, 4),
    }


async def run_deterministic_arm(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Evaluate Arm V0: Deterministic Verifier."""
    det_verifier = DeterministicSqlVerifier()
    results: list[dict[str, Any]] = []

    for c in candidates:
        v_input = VerificationInput(
            question=c["question"],
            evidence=c["evidence"],
            dialect=c["dialect"],
            authorized_schema=c["authorized_schema"],
            candidate_sql=c["candidate_sql"],
            authorized_tables=c["authorized_tables"],
            authorized_columns=c["authorized_columns"],
        )
        t0 = time.perf_counter()
        res = await det_verifier.verify(v_input)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

        results.append({
            "candidate_id": c["candidate_id"],
            "case_id": c["case_id"],
            "question_id": c["question_id"],
            "source_run": c["source_run"],
            "decision": res.decision.value,
            "failed_checks": res.failed_checks,
            "unknown_checks": res.unknown_checks,
            "latency_ms": elapsed_ms,
            "evaluator_metadata": c["evaluator_metadata"],
        })

    return results


async def run_gpt5_mini_arm(
    candidates: list[dict[str, Any]],
    chat_client: OpenAICompatibleChatClient,
    concurrency: int = 8,
    checkpoint_file: Path | None = None,
) -> list[dict[str, Any]]:
    """Evaluate Arm V2: openai/gpt-5-mini over frozen candidates."""
    verifier = LlmSemanticVerifier(
        chat_client=chat_client,
        model_name="openai/gpt-5-mini",
        reasoning_effort="low",
        max_output_tokens=4096,
    )

    # Check for existing checkpoint
    completed_map: dict[str, dict[str, Any]] = {}
    if checkpoint_file and checkpoint_file.exists():
        for line in checkpoint_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                completed_map[item["candidate_id"]] = item
        print(f"[Arm V2] Loaded {len(completed_map)} checkpoints from {checkpoint_file.name}")

    sem = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []
    lock = asyncio.Lock()

    async def verify_candidate(c: dict[str, Any]) -> dict[str, Any]:
        cid = c["candidate_id"]
        if cid in completed_map:
            return completed_map[cid]

        async with sem:
            v_input = VerificationInput(
                question=c["question"],
                evidence=c["evidence"],
                dialect=c["dialect"],
                authorized_schema=c["authorized_schema"],
                candidate_sql=c["candidate_sql"],
                authorized_tables=c["authorized_tables"],
                authorized_columns=c["authorized_columns"],
            )
            t0 = time.perf_counter()
            res = await verifier.verify(v_input)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

            # Extract check details
            checks_summary = {
                dim: getattr(res, dim).status.value
                for dim in SEMANTIC_CHECK_DIMENSIONS
            }

            rec = {
                "candidate_id": cid,
                "case_id": c["case_id"],
                "question_id": c["question_id"],
                "source_run": c["source_run"],
                "decision": res.decision.value,
                "checks": checks_summary,
                "failed_checks": res.failed_checks,
                "unknown_checks": res.unknown_checks,
                "latency_ms": elapsed_ms,
                "evaluator_metadata": c["evaluator_metadata"],
            }

            if checkpoint_file:
                async with lock:
                    with open(checkpoint_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec) + "\n")

            return rec

    tasks = [verify_candidate(c) for c in candidates]
    results = await asyncio.gather(*tasks)
    return results


def compute_pairwise_agreement(
    arm_a_results: list[dict[str, Any]],
    arm_b_results: list[dict[str, Any]],
    arm_a_name: str,
    arm_b_name: str,
) -> dict[str, Any]:
    """Compute 2x2 agreement matrix and breakdown by ground truth correctness."""
    b_map = {r["candidate_id"]: r for r in arm_b_results}
    n = len(arm_a_results)

    both_accept = 0
    both_withhold = 0
    a_accept_b_withhold = 0
    b_accept_a_withhold = 0

    both_accept_correct = 0
    both_accept_incorrect = 0

    a_acc_b_with_correct = 0
    a_acc_b_with_incorrect = 0

    b_acc_a_with_correct = 0
    b_acc_a_with_incorrect = 0

    both_withhold_correct = 0
    both_withhold_incorrect = 0

    for a in arm_a_results:
        cid = a["candidate_id"]
        b = b_map[cid]
        is_corr = a["evaluator_metadata"]["execution_correctness"]

        a_acc = a["decision"] == "ACCEPT"
        b_acc = b["decision"] == "ACCEPT"

        if a_acc and b_acc:
            both_accept += 1
            if is_corr:
                both_accept_correct += 1
            else:
                both_accept_incorrect += 1
        elif not a_acc and not b_acc:
            both_withhold += 1
            if is_corr:
                both_withhold_correct += 1
            else:
                both_withhold_incorrect += 1
        elif a_acc and not b_acc:
            a_accept_b_withhold += 1
            if is_corr:
                a_acc_b_with_correct += 1
            else:
                a_acc_b_with_incorrect += 1
        else:  # not a_acc and b_acc
            b_accept_a_withhold += 1
            if is_corr:
                b_acc_a_with_correct += 1
            else:
                b_acc_a_with_incorrect += 1

    agreement_rate = (both_accept + both_withhold) / n if n > 0 else 0.0

    return {
        "arm_a": arm_a_name,
        "arm_b": arm_b_name,
        "total_pairs": n,
        "overall_agreement_rate": round(agreement_rate, 4),
        "raw_counts": {
            "both_accept": both_accept,
            "both_withhold": both_withhold,
            f"{arm_a_name}_accept_{arm_b_name}_withhold": a_accept_b_withhold,
            f"{arm_b_name}_accept_{arm_a_name}_withhold": b_accept_a_withhold,
        },
        "correctness_breakdown": {
            "both_accept": {
                "correct": both_accept_correct,
                "incorrect": both_accept_incorrect,
                "precision": round(both_accept_correct / both_accept, 4) if both_accept > 0 else 0.0,
            },
            "both_withhold": {
                "correct_false_withhold": both_withhold_correct,
                "incorrect_true_withhold": both_withhold_incorrect,
            },
            f"{arm_a_name}_accept_{arm_b_name}_withhold": {
                "correct": a_acc_b_with_correct,
                "incorrect": a_acc_b_with_incorrect,
            },
            f"{arm_b_name}_accept_{arm_a_name}_withhold": {
                "correct": b_acc_a_with_correct,
                "incorrect": b_acc_a_with_incorrect,
            },
        },
    }


def compute_failure_leakage(
    candidates: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze check failure rates across the 7 semantic dimensions."""
    res_map = {r["candidate_id"]: r for r in results}
    dimension_blocks: Counter[str] = Counter()
    dimension_unknowns: Counter[str] = Counter()
    false_accept_count = 0
    total_rejections = 0
    total_abstains = 0


    for c in candidates:
        r = res_map[c["candidate_id"]]
        dec = r["decision"]
        is_corr = c["evaluator_metadata"]["execution_correctness"]

        if dec == "ACCEPT" and not is_corr:
            false_accept_count += 1
        elif dec == "REJECT":
            total_rejections += 1
        elif dec == "ABSTAIN":
            total_abstains += 1

        checks = r.get("checks", {})
        for dim, status in checks.items():
            if status == "FAIL":
                dimension_blocks[dim] += 1
            elif status == "UNKNOWN":
                dimension_unknowns[dim] += 1

    return {
        "false_accept_count": false_accept_count,
        "total_rejections": total_rejections,
        "total_abstains": total_abstains,
        "dimension_blocks": dict(dimension_blocks.most_common()),
        "dimension_unknowns": dict(dimension_unknowns.most_common()),
    }


def simulate_runtime_policies(
    total_trials: int,
    candidates: list[dict[str, Any]],
    v0_results: list[dict[str, Any]],
    v1_results: list[dict[str, Any]],
    v2_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Simulate runtime policies (P5 alone, P5+V0, P5+V1, P5+V2, Dual V1+V2, Solo)."""
    v0_map = {r["candidate_id"]: r["decision"] for r in v0_results}
    v1_map = {r["candidate_id"]: r["decision"] for r in v1_results}
    v2_map = {r["candidate_id"]: r["decision"] for r in v2_results}

    policies: dict[str, Callable[[dict[str, Any]], bool]] = {
        "accept_all": lambda c: True,
        "p5_control": lambda c: bool(c["evaluator_metadata"]["p5_accepted"]),
        "p5_and_v0_det": lambda c: bool(c["evaluator_metadata"]["p5_accepted"]) and v0_map[c["candidate_id"]] == "ACCEPT",
        "p5_and_v1_oss120b": lambda c: bool(c["evaluator_metadata"]["p5_accepted"]) and v1_map[c["candidate_id"]] == "ACCEPT",
        "p5_and_v2_gpt5mini": lambda c: bool(c["evaluator_metadata"]["p5_accepted"]) and v2_map[c["candidate_id"]] == "ACCEPT",
        "p5_and_dual_v1_and_v2": lambda c: bool(c["evaluator_metadata"]["p5_accepted"]) and v1_map[c["candidate_id"]] == "ACCEPT" and v2_map[c["candidate_id"]] == "ACCEPT",
        "p5_and_either_v1_or_v2": lambda c: bool(c["evaluator_metadata"]["p5_accepted"]) and (v1_map[c["candidate_id"]] == "ACCEPT" or v2_map[c["candidate_id"]] == "ACCEPT"),
        "v1_solo": lambda c: v1_map[c["candidate_id"]] == "ACCEPT",
        "v2_solo": lambda c: v2_map[c["candidate_id"]] == "ACCEPT",
    }

    policy_results: dict[str, Any] = {}

    for pol_name, pol_fn in policies.items():
        executed_corr = 0
        executed_incorr = 0

        for c in candidates:
            if pol_fn(c):
                if c["evaluator_metadata"]["execution_correctness"]:
                    executed_corr += 1
                else:
                    executed_incorr += 1

        total_exec = executed_corr + executed_incorr
        prec = executed_corr / total_exec if total_exec > 0 else 0.0
        cov = total_exec / total_trials
        risk = executed_incorr / total_exec if total_exec > 0 else 0.0
        ex = executed_corr / total_trials
        ci_l, ci_h = wilson_score_interval(executed_corr, total_exec, confidence=0.95) if total_exec > 0 else (0.0, 0.0)

        policy_results[pol_name] = {
            "executed_count": total_exec,
            "correct_count": executed_corr,
            "incorrect_count": executed_incorr,
            "precision": round(prec, 4),
            "precision_ci95": [round(ci_l, 4), round(ci_h, 4)],
            "coverage": round(cov, 4),
            "mean_ex": round(ex, 4),
            "selective_risk": round(risk, 4),
        }

    return policy_results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 8C: Verifier Backend Validation")
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrency for LLM verifier")
    parser.add_argument("--run-v2", action="store_true", default=True, help="Run Arm V2 (gpt-5-mini)")
    args = parser.parse_args()

    load_dotenv()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load Frozen Candidates
    if not FROZEN_CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"Frozen candidates corpus not found: {FROZEN_CANDIDATES_PATH}")

    candidates: list[dict[str, Any]] = [
        json.loads(line)
        for line in FROZEN_CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    total_trials = 300
    no_candidate_count = total_trials - len(candidates)
    corpus_sha = hashlib.sha256(FROZEN_CANDIDATES_PATH.read_bytes()).hexdigest()

    print("=== Phase 8C: Verifier Backend Validation ===")
    print(f"Loaded {len(candidates)} frozen candidates (Corpus SHA256: {corpus_sha[:12]}...)")
    print(f"Total trials: {total_trials}, Without candidate: {no_candidate_count}")

    # 2. Arm V0: Deterministic Verifier
    print("\n--- Running Arm V0: Deterministic Verifier ---")
    v0_results = await run_deterministic_arm(candidates)
    v0_file = RESULTS_DIR / "verifier_results_deterministic.jsonl"
    with open(v0_file, "w", encoding="utf-8") as f:
        for r in v0_results:
            f.write(json.dumps(r) + "\n")
    v0_metrics = compute_metrics(total_trials, no_candidate_count, v0_results, "decision")
    print(f"Arm V0 Candidate Precision: {v0_metrics['precision']*100:.2f}%, Coverage: {v0_metrics['candidate_coverage']*100:.2f}%")

    # 3. Arm V1: openai/gpt-oss-120b (Reproduced from P8-B frozen metadata)
    print("\n--- Compiling Arm V1: openai/gpt-oss-120b ---")
    v1_results: list[dict[str, Any]] = []
    for c in candidates:
        eval_meta = c["evaluator_metadata"]
        v1_results.append({
            "candidate_id": c["candidate_id"],
            "case_id": c["case_id"],
            "question_id": c["question_id"],
            "source_run": c["source_run"],
            "decision": eval_meta["p8b_verifier_decision"],
            "checks": eval_meta.get("p8b_verifier_checks") or {},
            "latency_ms": 0.0,
            "evaluator_metadata": eval_meta,
        })
    v1_file = RESULTS_DIR / "verifier_results_gpt_oss_120b.jsonl"
    with open(v1_file, "w", encoding="utf-8") as f:
        for r in v1_results:
            f.write(json.dumps(r) + "\n")
    v1_metrics = compute_metrics(total_trials, no_candidate_count, v1_results, "decision")
    print(f"Arm V1 Candidate Precision: {v1_metrics['precision']*100:.2f}%, Coverage: {v1_metrics['candidate_coverage']*100:.2f}%")

    # 4. Arm V2: openai/gpt-5-mini
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    v2_file = RESULTS_DIR / "verifier_results_gpt5_mini.jsonl"
    v2_metrics: dict[str, Any] = {}

    if args.run_v2 and api_key:
        print(f"\n--- Running Arm V2: openai/gpt-5-mini (Concurrency: {args.concurrency}) ---")
        chat_client = OpenAICompatibleChatClient(base_url=base_url, api_key=api_key)
        v2_results = await run_gpt5_mini_arm(
            candidates=candidates,
            chat_client=chat_client,
            concurrency=args.concurrency,
            checkpoint_file=v2_file,
        )
        v2_metrics = compute_metrics(total_trials, no_candidate_count, v2_results, "decision")
        print(f"Arm V2 Candidate Precision: {v2_metrics['precision']*100:.2f}%, Coverage: {v2_metrics['candidate_coverage']*100:.2f}%")
    else:
        print("\n--- Arm V2: NOT RUN (No valid API credentials configured) ---")
        v2_results = []
        v2_metrics = {"status": "NOT_RUN"}

    # 5. Backend Comparison
    backend_comparison = {
        "corpus_sha256": corpus_sha,
        "total_trials": total_trials,
        "total_candidates": len(candidates),
        "arms": {
            "v0_deterministic": v0_metrics,
            "v1_gpt_oss_120b": v1_metrics,
            "v2_gpt5_mini": v2_metrics,
        },
    }
    with open(RESULTS_DIR / "backend_comparison.json", "w", encoding="utf-8") as f:
        json.dump(backend_comparison, f, indent=2)

    # 6. Pairwise Decision Agreement
    pairwise_agreements: dict[str, Any] = {}
    pairwise_agreements["v0_vs_v1"] = compute_pairwise_agreement(
        v0_results, v1_results, "v0_deterministic", "v1_gpt_oss_120b"
    )
    if v2_results:
        pairwise_agreements["v1_vs_v2"] = compute_pairwise_agreement(
            v1_results, v2_results, "v1_gpt_oss_120b", "v2_gpt5_mini"
        )
        pairwise_agreements["v0_vs_v2"] = compute_pairwise_agreement(
            v0_results, v2_results, "v0_deterministic", "v2_gpt5_mini"
        )
    with open(RESULTS_DIR / "decision_agreement.json", "w", encoding="utf-8") as f:
        json.dump(pairwise_agreements, f, indent=2)

    # 7. Failure Leakage Analysis
    leakage_analysis = {
        "v1_gpt_oss_120b": compute_failure_leakage(candidates, v1_results),
    }
    if v2_results:
        leakage_analysis["v2_gpt5_mini"] = compute_failure_leakage(candidates, v2_results)
    with open(RESULTS_DIR / "failure_leakage.json", "w", encoding="utf-8") as f:
        json.dump(leakage_analysis, f, indent=2)

    # 8. Offline Policy Simulation
    if v2_results:
        policy_sim = simulate_runtime_policies(
            total_trials=total_trials,
            candidates=candidates,
            v0_results=v0_results,
            v1_results=v1_results,
            v2_results=v2_results,
        )
        with open(RESULTS_DIR / "policy_simulation.json", "w", encoding="utf-8") as f:
            json.dump(policy_sim, f, indent=2)
        print("\n--- Policy Simulation Summary ---")
        for p_name, p_res in policy_sim.items():
            print(f"{p_name:<28}: Precision {p_res['precision']*100:6.2f}% | Coverage {p_res['coverage']*100:5.2f}% | Risk {p_res['selective_risk']*100:5.2f}%")

    # 9. Verifier Stability
    stability_data = {
        "v1_pairwise_agreement_with_v2": pairwise_agreements.get("v1_vs_v2", {}).get("overall_agreement_rate"),
        "v1_vs_v0_agreement": pairwise_agreements.get("v0_vs_v1", {}).get("overall_agreement_rate"),
        "v2_vs_v0_agreement": pairwise_agreements.get("v0_vs_v2", {}).get("overall_agreement_rate") if v2_results else None,
    }
    with open(RESULTS_DIR / "stability.json", "w", encoding="utf-8") as f:
        json.dump(stability_data, f, indent=2)

    # 10. Manifest
    manifest = {
        "phase": "P8-C",
        "timestamp": datetime.now(UTC).isoformat(),
        "frozen_candidates_count": len(candidates),
        "corpus_sha256": corpus_sha,
        "evaluated_arms": ["Arm V0 (Deterministic)", "Arm V1 (gpt-oss-120b)", "Arm V2 (gpt-5-mini)"] if v2_results else ["Arm V0 (Deterministic)", "Arm V1 (gpt-oss-120b)"],
        "artifacts": [
            "frozen_candidates.jsonl",
            "candidate_accounting.json",
            "verifier_results_deterministic.jsonl",
            "verifier_results_gpt_oss_120b.jsonl",
            "verifier_results_gpt5_mini.jsonl",
            "backend_comparison.json",
            "decision_agreement.json",
            "failure_leakage.json",
            "policy_simulation.json",
            "stability.json",
            "summary.md",
        ],
    }
    with open(RESULTS_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\nPhase 8C benchmark completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
