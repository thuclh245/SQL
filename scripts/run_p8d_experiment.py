# ruff: noqa: E501
"""Phase 8D: Targeted Filter/Value Verifier Hardening Experiment Runner.

Evaluates Prompt v002 (with strengthened filters_and_values checking)
against Control v001 across 3 complete stochastic replicates on the frozen
Dev100 candidate corpus (N=286 candidates across 300 trials).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from t2s.evaluation.uncertainty_diagnostics import (
    classify_sql_failure_slice,
    wilson_score_interval,
)
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.verification.contracts import (
    SEMANTIC_CHECK_DIMENSIONS,
    VerificationInput,
)
from t2s.verification.llm_semantic_verifier import LlmSemanticVerifier

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_CANDIDATES_PATH = (
    PROJECT_ROOT / "results" / "p8c_verifier_backend_validation" / "frozen_candidates.jsonl"
)
CONTROL_V001_PATH = (
    PROJECT_ROOT / "results" / "p8c_verifier_backend_validation" / "verifier_results_gpt5_mini.jsonl"
)
P8D_DIR = PROJECT_ROOT / "results" / "p8d_filter_verifier"
REPLICATES = ["v002_r1", "v002_r2", "v002_r3"]


def compute_metrics_for_run(
    total_trials: int,
    no_candidate_count: int,
    evaluated_candidates: list[dict[str, Any]],
    cand_sql_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compute standard verifier metrics."""
    n_evaluated = len(evaluated_candidates)
    assert n_evaluated + no_candidate_count == total_trials

    ca = 0  # correct accepted (TP)
    ia = 0  # incorrect accepted (FP)
    cr = 0  # correct rejected (FN-reject)
    ir = 0  # incorrect rejected (TN-reject)
    cab = 0  # correct abstained (FN-abstain)
    iab = 0  # incorrect abstained (TN-abstain)

    for c in evaluated_candidates:
        dec = c["decision"]
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
        else:
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
    specificity = (ir + iab) / total_incorrect if total_incorrect > 0 else 0.0

    ci_l, ci_h = wilson_score_interval(ca, total_accepted, confidence=0.95) if total_accepted > 0 else (0.0, 0.0)

    # Filter/value error tracking
    fv_total = 0
    fv_fa = 0
    fv_blocked = 0
    fv_fails_triggered = 0
    fv_false_alarms = 0

    for c in evaluated_candidates:
        is_corr = c["evaluator_metadata"]["execution_correctness"]
        checks = c.get("checks", {})
        fv_status = checks.get("filters_and_values")
        cid = c["candidate_id"]
        cand_sql = (cand_sql_map.get(cid) if cand_sql_map else None) or c.get("candidate_sql") or c["evaluator_metadata"].get("candidate_sql")

        if not is_corr:
            slice_cat = classify_sql_failure_slice(
                cand_sql,
                c["evaluator_metadata"].get("gold_sql"),
            )
            if slice_cat.value == "FILTER_OR_VALUE_ERROR":
                fv_total += 1
                if c["decision"] == "ACCEPT":
                    fv_fa += 1
                else:
                    fv_blocked += 1

        else:
            if fv_status == "FAIL":
                fv_false_alarms += 1

        if fv_status == "FAIL":
            fv_fails_triggered += 1

    fv_recall = fv_blocked / fv_total if fv_total > 0 else 0.0
    fv_fail_precision = (fv_fails_triggered - fv_false_alarms) / fv_fails_triggered if fv_fails_triggered > 0 else 0.0

    return {
        "candidate_evaluations": n_evaluated,
        "total_trials": total_trials,
        "total_accepted": total_accepted,
        "total_withheld": total_withheld,
        "correct_accepted": ca,
        "incorrect_accepted": ia,
        "correct_rejected": cr,
        "incorrect_rejected": ir,
        "correct_abstained": cab,
        "incorrect_abstained": iab,
        "precision": round(precision, 4),
        "precision_ci95": [round(ci_l, 4), round(ci_h, 4)],
        "selective_risk": round(selective_risk, 4),
        "coverage": round(coverage, 4),
        "candidate_coverage": round(candidate_coverage, 4),
        "false_withhold_rate": round(false_withhold_rate, 4),
        "true_withhold_rate": round(specificity, 4),
        "filter_value_metrics": {
            "fv_total_failures": fv_total,
            "fv_false_accepts": fv_fa,
            "fv_blocked": fv_blocked,
            "fv_detection_recall": round(fv_recall, 4),
            "fv_fails_triggered": fv_fails_triggered,
            "fv_false_alarms": fv_false_alarms,
            "fv_fail_precision": round(fv_fail_precision, 4),
        },
    }


async def run_verifier_replicate(
    candidates: list[dict[str, Any]],
    chat_client: OpenAICompatibleChatClient,
    prompt_version: str,
    output_file: Path,
    concurrency: int = 8,
) -> list[dict[str, Any]]:
    """Run one full pass over all frozen candidates."""
    verifier = LlmSemanticVerifier(
        chat_client=chat_client,
        model_name="openai/gpt-5-mini",
        prompt_version=prompt_version,
        reasoning_effort="low",
        max_output_tokens=4096,
    )

    completed_map: dict[str, dict[str, Any]] = {}
    if output_file.exists():
        for line in output_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                completed_map[item["candidate_id"]] = item
        print(f"[{output_file.parent.name}] Loaded {len(completed_map)} checkpoints from {output_file.name}")

    sem = asyncio.Semaphore(concurrency)
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

            checks_summary = {
                dim: getattr(res, dim).status.value
                for dim in SEMANTIC_CHECK_DIMENSIONS
            }

            rec = {
                "candidate_id": cid,
                "case_id": c["case_id"],
                "question_id": c["question_id"],
                "source_run": c["source_run"],
                "candidate_sql": c["candidate_sql"],
                "decision": res.decision.value,
                "checks": checks_summary,
                "failed_checks": res.failed_checks,
                "unknown_checks": res.unknown_checks,
                "latency_ms": elapsed_ms,
                "evaluator_metadata": c["evaluator_metadata"],
            }

            async with lock:
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")

            return rec

    tasks = [verify_candidate(c) for c in candidates]
    results = await asyncio.gather(*tasks)
    return results


def simulate_p5_gate(
    total_trials: int,
    candidates: list[dict[str, Any]],
    verifier_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Simulate P5 + Verifier runtime gate."""
    res_map = {r["candidate_id"]: r["decision"] for r in verifier_results}

    executed_corr = 0
    executed_incorr = 0

    for c in candidates:
        cid = c["candidate_id"]
        p5_acc = bool(c["evaluator_metadata"]["p5_accepted"])
        v_acc = (res_map[cid] == "ACCEPT")
        if p5_acc and v_acc:
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

    return {
        "executed_count": total_exec,
        "correct_count": executed_corr,
        "incorrect_count": executed_incorr,
        "precision": round(prec, 4),
        "precision_ci95": [round(ci_l, 4), round(ci_h, 4)],
        "coverage": round(cov, 4),
        "mean_ex": round(ex, 4),
        "selective_risk": round(risk, 4),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 8D: Targeted Filter/Value Verifier Hardening")
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrency for LLM verifier")
    args = parser.parse_args()

    load_dotenv()
    P8D_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load Frozen Candidates
    candidates: list[dict[str, Any]] = [
        json.loads(line)
        for line in FROZEN_CANDIDATES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    total_trials = 300
    no_candidate_count = total_trials - len(candidates)
    corpus_sha = hashlib.sha256(FROZEN_CANDIDATES_PATH.read_bytes()).hexdigest()

    print("=== Phase 8D: Targeted Filter/Value Verifier Hardening ===")
    print(f"Loaded {len(candidates)} frozen candidates (Corpus SHA256: {corpus_sha[:12]}...)")

    cand_sql_map = {c["candidate_id"]: c["candidate_sql"] for c in candidates}

    # 2. Load Control v001 Results
    control_v001_results: list[dict[str, Any]] = [
        json.loads(line)
        for line in CONTROL_V001_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    control_metrics = compute_metrics_for_run(total_trials, no_candidate_count, control_v001_results, cand_sql_map=cand_sql_map)
    control_gate = simulate_p5_gate(total_trials, candidates, control_v001_results)

    print("\n--- Control v001 Baseline ---")
    print(f"Candidate Precision: {control_metrics['precision']*100:.2f}%, Coverage: {control_metrics['candidate_coverage']*100:.2f}%, False Accepts: {control_metrics['incorrect_accepted']}")
    print(f"Filter/Value False Accepts: {control_metrics['filter_value_metrics']['fv_false_accepts']} / {control_metrics['filter_value_metrics']['fv_total_failures']}")
    print(f"P5 + v001 Gate Precision: {control_gate['precision']*100:.2f}%, Coverage: {control_gate['coverage']*100:.2f}%, Risk: {control_gate['selective_risk']*100:.2f}%")

    # 3. Execute 3 Replicates for Arm F (v002)
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    chat_client = OpenAICompatibleChatClient(base_url=base_url, api_key=api_key)

    v002_replicate_results: dict[str, list[dict[str, Any]]] = {}
    v002_replicate_metrics: dict[str, dict[str, Any]] = {}
    v002_replicate_gates: dict[str, dict[str, Any]] = {}

    for rep in REPLICATES:
        rep_dir = P8D_DIR / rep
        rep_dir.mkdir(parents=True, exist_ok=True)
        rep_file = rep_dir / "predictions.jsonl"
        print(f"\n--- Running Arm F: {rep} (concurrency={args.concurrency}) ---")
        t0 = time.perf_counter()
        rep_res = await run_verifier_replicate(
            candidates=candidates,
            chat_client=chat_client,
            prompt_version="v002",
            output_file=rep_file,
            concurrency=args.concurrency,
        )
        t_elapsed = time.perf_counter() - t0
        v002_replicate_results[rep] = rep_res
        metrics = compute_metrics_for_run(total_trials, no_candidate_count, rep_res, cand_sql_map=cand_sql_map)
        gate = simulate_p5_gate(total_trials, candidates, rep_res)
        v002_replicate_metrics[rep] = metrics
        v002_replicate_gates[rep] = gate
        print(f"[{rep}] Completed in {t_elapsed:.1f}s | Precision: {metrics['precision']*100:.2f}% | Coverage: {metrics['candidate_coverage']*100:.2f}% | FA: {metrics['incorrect_accepted']} | FV-FA: {metrics['filter_value_metrics']['fv_false_accepts']}")


    # 4. Aggregate 3-Replicate Statistics for v002
    precisions = [m["precision"] for m in v002_replicate_metrics.values()]
    coverages = [m["candidate_coverage"] for m in v002_replicate_metrics.values()]
    trial_coverages = [m["coverage"] for m in v002_replicate_metrics.values()]
    risks = [m["selective_risk"] for m in v002_replicate_metrics.values()]
    fas = [m["incorrect_accepted"] for m in v002_replicate_metrics.values()]
    cas = [m["correct_accepted"] for m in v002_replicate_metrics.values()]
    fv_fas = [m["filter_value_metrics"]["fv_false_accepts"] for m in v002_replicate_metrics.values()]
    fv_recalls = [m["filter_value_metrics"]["fv_detection_recall"] for m in v002_replicate_metrics.values()]
    gate_precs = [g["precision"] for g in v002_replicate_gates.values()]
    gate_covs = [g["coverage"] for g in v002_replicate_gates.values()]
    gate_risks = [g["selective_risk"] for g in v002_replicate_gates.values()]

    v002_mean_summary = {
        "precision_mean": round(statistics.mean(precisions), 4),
        "precision_std": round(statistics.stdev(precisions) if len(precisions) > 1 else 0.0, 4),
        "candidate_coverage_mean": round(statistics.mean(coverages), 4),
        "candidate_coverage_std": round(statistics.stdev(coverages) if len(coverages) > 1 else 0.0, 4),
        "trial_coverage_mean": round(statistics.mean(trial_coverages), 4),
        "trial_coverage_std": round(statistics.stdev(trial_coverages) if len(trial_coverages) > 1 else 0.0, 4),
        "selective_risk_mean": round(statistics.mean(risks), 4),
        "selective_risk_std": round(statistics.stdev(risks) if len(risks) > 1 else 0.0, 4),
        "false_accepts_mean": round(statistics.mean(fas), 2),
        "false_accepts_std": round(statistics.stdev(fas) if len(fas) > 1 else 0.0, 2),
        "correct_accepts_mean": round(statistics.mean(cas), 2),
        "correct_accepts_std": round(statistics.stdev(cas) if len(cas) > 1 else 0.0, 2),
        "fv_false_accepts_mean": round(statistics.mean(fv_fas), 2),
        "fv_detection_recall_mean": round(statistics.mean(fv_recalls), 4),
        "gate_precision_mean": round(statistics.mean(gate_precs), 4),
        "gate_coverage_mean": round(statistics.mean(gate_covs), 4),
        "gate_selective_risk_mean": round(statistics.mean(gate_risks), 4),
    }

    # 5. Stability Analysis Across 3 Runs
    cids = [c["candidate_id"] for c in candidates]
    candidate_decisions: dict[str, list[str]] = {cid: [] for cid in cids}
    for rep in REPLICATES:
        rep_map = {r["candidate_id"]: r["decision"] for r in v002_replicate_results[rep]}
        for cid in cids:
            candidate_decisions[cid].append(rep_map[cid])

    accept_3_of_3 = sum(1 for decs in candidate_decisions.values() if decs.count("ACCEPT") == 3)
    accept_2_of_3 = sum(1 for decs in candidate_decisions.values() if decs.count("ACCEPT") == 2)
    accept_1_of_3 = sum(1 for decs in candidate_decisions.values() if decs.count("ACCEPT") == 1)
    accept_0_of_3 = sum(1 for decs in candidate_decisions.values() if decs.count("ACCEPT") == 0)

    unanimous_decisions = sum(1 for decs in candidate_decisions.values() if len(set(decs)) == 1)
    decision_agreement_rate = unanimous_decisions / len(cids)

    stability_data = {
        "total_candidates": len(cids),
        "accept_3_of_3": accept_3_of_3,
        "accept_2_of_3": accept_2_of_3,
        "accept_1_of_3": accept_1_of_3,
        "accept_0_of_3": accept_0_of_3,
        "unanimous_decisions": unanimous_decisions,
        "decision_agreement_rate": round(decision_agreement_rate, 4),
    }
    with open(P8D_DIR / "stability.json", "w", encoding="utf-8") as f:
        json.dump(stability_data, f, indent=2)

    # 6. Predeclared Decision Criteria Evaluation
    # Criteria:
    # SUPPORTED if: false accepts decrease by >= 20% AND precision increases AND coverage drop <= 5% (0.05)
    # REJECTED if: precision does not improve OR false accepts do not materially decrease OR coverage collapses > 10%
    # TRADEOFF / INCONCLUSIVE otherwise.
    fa_control = control_metrics["incorrect_accepted"]  # 31
    fa_v002_mean = v002_mean_summary["false_accepts_mean"]
    fa_reduction_pct = (fa_control - fa_v002_mean) / fa_control if fa_control > 0 else 0.0

    prec_control = control_metrics["precision"]  # 0.6265
    prec_v002_mean = v002_mean_summary["precision_mean"]
    prec_delta = prec_v002_mean - prec_control

    cov_control = control_metrics["candidate_coverage"]  # 0.2902
    cov_v002_mean = v002_mean_summary["candidate_coverage_mean"]
    cov_delta = cov_v002_mean - cov_control

    if fa_reduction_pct >= 0.20 and prec_delta > 0 and (cov_control - cov_v002_mean) <= 0.05:
        decision = "FILTER_VERIFIER_V002_SUPPORTED"
        decision_rationale = (
            f"Supported: False accepts decreased by {fa_reduction_pct*100:.1f}% (>= 20%), "
            f"precision increased by {prec_delta*100:+.2f}%, and coverage drop was {abs(cov_delta)*100:.2f}% (<= 5%)."
        )
    elif prec_delta <= 0 or fa_reduction_pct < 0.10 or (cov_control - cov_v002_mean) > 0.10:
        decision = "FILTER_VERIFIER_V002_REJECTED"
        decision_rationale = (
            f"Rejected: Precision delta was {prec_delta*100:+.2f}%, false accept reduction was {fa_reduction_pct*100:.1f}%, "
            f"and coverage drop was {(cov_control - cov_v002_mean)*100:.2f}%."
        )
    else:
        decision = "FILTER_VERIFIER_TRADEOFF_INCONCLUSIVE"
        decision_rationale = (
            f"Tradeoff/Inconclusive: False accept reduction was {fa_reduction_pct*100:.1f}%, "
            f"precision delta was {prec_delta*100:+.2f}%, and coverage drop was {(cov_control - cov_v002_mean)*100:.2f}%."
        )

    print("\n================================================================================")
    print(f"PREDECLARED DECISION: {decision}")
    print(f"{decision_rationale}")
    print("================================================================================")

    # 7. Comparison Artifact
    comparison = {
        "corpus_sha256": corpus_sha,
        "control_v001": {
            "prompt_version": "v001",
            "prompt_sha256": "6d28add0fd23876db02f703a086aceff35eed01efd5d73736baf893010b2becf",
            "metrics": control_metrics,
            "gate_simulation": control_gate,
        },
        "arm_f_v002": {
            "prompt_version": "v002",
            "prompt_sha256": "09ce5d0fe977307e7a7800f163cbcc9136d37a4d24624b3c45abc4c75ff8e2ee",
            "replicates": v002_replicate_metrics,
            "mean_summary": v002_mean_summary,
            "gate_simulations": v002_replicate_gates,
        },
        "deltas": {
            "precision_delta": round(prec_delta, 4),
            "candidate_coverage_delta": round(cov_delta, 4),
            "false_accept_delta": round(fa_v002_mean - fa_control, 2),
            "false_accept_reduction_pct": round(fa_reduction_pct, 4),
            "correct_accept_delta": round(v002_mean_summary["correct_accepts_mean"] - control_metrics["correct_accepted"], 2),
            "fv_false_accept_delta": round(v002_mean_summary["fv_false_accepts_mean"] - control_metrics["filter_value_metrics"]["fv_false_accepts"], 2),
        },
        "predeclared_decision": {
            "decision": decision,
            "rationale": decision_rationale,
        },
    }
    with open(P8D_DIR / "comparison.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    # 8. Filter/Value Effectiveness Artifact
    fv_effectiveness = {
        "control_v001": control_metrics["filter_value_metrics"],
        "arm_f_v002_replicates": {rep: m["filter_value_metrics"] for rep, m in v002_replicate_metrics.items()},
        "arm_f_v002_mean": {
            "fv_false_accepts_mean": v002_mean_summary["fv_false_accepts_mean"],
            "fv_detection_recall_mean": v002_mean_summary["fv_detection_recall_mean"],
            "delta_fv_false_accepts": round(v002_mean_summary["fv_false_accepts_mean"] - control_metrics["filter_value_metrics"]["fv_false_accepts"], 2),
        },
    }
    with open(P8D_DIR / "filter_value_effectiveness.json", "w", encoding="utf-8") as f:
        json.dump(fv_effectiveness, f, indent=2)

    # 9. Runtime Simulation Artifact
    runtime_sim = {
        "p5_control": {
            "precision": 0.5000,
            "coverage": 0.4667,
            "selective_risk": 0.5000,
        },
        "p5_and_v001_control": control_gate,
        "p5_and_v002_replicates": v002_replicate_gates,
        "p5_and_v002_mean": {
            "precision": v002_mean_summary["gate_precision_mean"],
            "coverage": v002_mean_summary["gate_coverage_mean"],
            "selective_risk": v002_mean_summary["gate_selective_risk_mean"],
        },
    }
    with open(P8D_DIR / "runtime_simulation.json", "w", encoding="utf-8") as f:
        json.dump(runtime_sim, f, indent=2)

    # 10. Summary.md
    summary_md_content = f"""# Phase 8D: Targeted Filter/Value Verifier Hardening Summary

## 1. Primary Findings
- **Control (v001 + gpt-5-mini)**: Precision {control_metrics['precision']*100:.2f}%, Coverage {control_metrics['candidate_coverage']*100:.2f}%, False Accepts: {control_metrics['incorrect_accepted']} (FV False Accepts: {control_metrics['filter_value_metrics']['fv_false_accepts']}).
- **Arm F (v002 + gpt-5-mini, 3-run mean)**: Precision {v002_mean_summary['precision_mean']*100:.2f}% ± {v002_mean_summary['precision_std']*100:.2f}%, Coverage {v002_mean_summary['candidate_coverage_mean']*100:.2f}% ± {v002_mean_summary['candidate_coverage_std']*100:.2f}%, False Accepts: {v002_mean_summary['false_accepts_mean']} (FV False Accepts: {v002_mean_summary['fv_false_accepts_mean']}).
- **Deltas**:
  - Precision: {prec_delta*100:+.2f}%
  - Coverage: {cov_delta*100:+.2f}%
  - False Accepts: {v002_mean_summary['false_accepts_mean'] - control_metrics['incorrect_accepted']:+.1f} ({fa_reduction_pct*100:+.1f}%)
  - Filter/Value False Accepts: {v002_mean_summary['fv_false_accepts_mean'] - control_metrics['filter_value_metrics']['fv_false_accepts']:+.1f}

## 2. Decision
**`{decision}`**
{decision_rationale}

## 3. Predeclared Decision Criteria Evaluation
- False accepts decrease >= 20%: {'PASS' if fa_reduction_pct >= 0.20 else 'FAIL'} ({fa_reduction_pct*100:.1f}%)
- Accepted precision increases: {'PASS' if prec_delta > 0 else 'FAIL'} ({prec_delta*100:+.2f}%)
- Coverage drop <= 5%: {'PASS' if (cov_control - cov_v002_mean) <= 0.05 else 'FAIL'} ({(cov_control - cov_v002_mean)*100:.2f}%)
"""
    with open(P8D_DIR / "summary.md", "w", encoding="utf-8") as f:
        f.write(summary_md_content)

    # 11. Manifest
    manifest = {
        "phase": "P8-D",
        "timestamp": datetime.now(UTC).isoformat(),
        "candidate_count": len(candidates),
        "corpus_sha256": corpus_sha,
        "control_prompt": "sql_verifier/v001",
        "control_prompt_sha256": "6d28add0fd23876db02f703a086aceff35eed01efd5d73736baf893010b2becf",
        "arm_f_prompt": "sql_verifier/v002",
        "arm_f_prompt_sha256": "09ce5d0fe977307e7a7800f163cbcc9136d37a4d24624b3c45abc4c75ff8e2ee",
        "replicates": REPLICATES,
        "artifacts": [
            "manifest.json",
            "paired_backend_statistics.json",
            "v002_r1/predictions.jsonl",
            "v002_r2/predictions.jsonl",
            "v002_r3/predictions.jsonl",
            "comparison.json",
            "filter_value_effectiveness.json",
            "stability.json",
            "runtime_simulation.json",
            "summary.md",
        ],
    }
    with open(P8D_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\nPhase 8D benchmark execution finished!")


if __name__ == "__main__":
    asyncio.run(main())
