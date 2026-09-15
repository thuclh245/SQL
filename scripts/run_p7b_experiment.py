# ruff: noqa: E501
import asyncio
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases
from t2s.benchmark.runner import build_arg_parser, run_benchmark
from t2s.evaluation.shadow_evaluator import (
    ShadowEvaluator,
    UnresolvedNoteCategory,
    classify_unresolved_note,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results" / "p7b_prompt_calibration"
PILOT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_pilot_v1.jsonl"
DATABASE_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"

RUN_CONFIGS = [
    {"run_id": "p7b_control_r1", "arm": "Control", "prompt_version": "v001"},
    {"run_id": "p7b_control_r2", "arm": "Control", "prompt_version": "v001"},
    {"run_id": "p7b_control_r3", "arm": "Control", "prompt_version": "v001"},
    {"run_id": "p7b_arm_a_r1", "arm": "Arm A", "prompt_version": "v002"},
    {"run_id": "p7b_arm_a_r2", "arm": "Arm A", "prompt_version": "v002"},
    {"run_id": "p7b_arm_a_r3", "arm": "Arm A", "prompt_version": "v002"},
]


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


async def execute_run(config: dict[str, Any], api_key: str, concurrency: int = 4) -> Path:
    run_id = config["run_id"]
    prompt_version = config["prompt_version"]
    run_dir = RESULTS_ROOT / run_id
    cases_file = run_dir / "cases.jsonl"

    if cases_file.exists():
        with cases_file.open("r", encoding="utf-8") as f:
            line_count = sum(1 for line in f if line.strip())
        if line_count == 85:
            print(f"[{run_id}] Already completed with 85 cases. Skipping inference.")
            return run_dir

    print(f"[{run_id}] Starting inference with prompt {prompt_version} (concurrency={concurrency})...")
    parser = build_arg_parser()
    args = parser.parse_args([
        "run",
        "--dataset", str(PILOT_DATASET),
        "--executable-only",
        "--provider", "openai_compatible",
        "--base-url", "https://api.openai.com/v1",
        "--model", "gpt-5-mini",
        "--api-key", api_key,
        "--prompt-version", prompt_version,
        "--output", str(RESULTS_ROOT),
        "--run-id", run_id,
        "--concurrency", str(concurrency),
    ])
    output_path = await run_benchmark(args)
    print(f"[{run_id}] Inference finished.")
    return output_path


def run_shadow_eval_for_run(
    run_dir: Path,
    bundles: dict[str, Any],
    evaluator: ShadowEvaluator,
) -> dict[str, Any]:
    cases_file = run_dir / "cases.jsonl"
    shadow_file = run_dir / "shadow_results.json"

    cases = []
    with cases_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))

    shadow_case_results = []
    for c in cases:
        cid = c["case_id"]
        bundle = bundles[cid]
        if c.get("runtime_status") == "UNRESOLVED":
            candidate_sql = c.get("rejected_candidate_sql")
            notes = c.get("rejected_candidate_unresolved") or c.get("solver_unresolved") or []
            res = evaluator.evaluate_case(
                case_id=cid,
                db_id=c["db_id"],
                candidate_sql=candidate_sql,
                gold_sql=bundle.scoring_gold.official_sql,
                authorized_tables=set(c.get("final_tables") or []),
                unresolved_notes=notes,
            )
            shadow_case_results.append({
                "case_id": cid,
                "db_id": c["db_id"],
                "status": res.status.value,
                "candidate_sql": res.candidate_sql,
                "ast_valid": res.ast_valid,
                "safety_valid": res.safety_valid,
                "authorization_valid": res.authorization_valid,
                "execution_success": res.execution_success,
                "execution_error": res.execution_error,
                "matches_gold": res.matches_gold,
                "unresolved_notes": res.unresolved_notes,
                "classified_notes": [[cat.value, n] for cat, n in res.classified_notes],
                "details": res.details,
            })

    # Aggregate shadow counts
    status_counts = Counter(r["status"] for r in shadow_case_results)
    shadow_correct = status_counts.get("SHADOW_CORRECT", 0)
    shadow_incorrect = status_counts.get("SHADOW_INCORRECT", 0)
    shadow_exec_error = status_counts.get("SHADOW_EXECUTION_ERROR", 0)
    shadow_safety_rej = status_counts.get("SHADOW_SAFETY_REJECTED", 0)
    shadow_access_rej = status_counts.get("SHADOW_ACCESS_REJECTED", 0)
    shadow_unavailable = status_counts.get("CANDIDATE_UNAVAILABLE", 0)
    total_unresolved = len(shadow_case_results)

    protective_abstentions = (
        shadow_incorrect + shadow_exec_error + shadow_safety_rej + shadow_access_rej
    )
    shadow_executable = shadow_correct + shadow_incorrect
    shadow_precision = (
        shadow_correct / shadow_executable if shadow_executable > 0 else 0.0
    )

    shadow_summary = {
        "run_id": run_dir.name,
        "total_unresolved": total_unresolved,
        "shadow_correct": shadow_correct,
        "shadow_incorrect": shadow_incorrect,
        "shadow_execution_error": shadow_exec_error,
        "shadow_safety_rejected": shadow_safety_rej,
        "shadow_access_rejected": shadow_access_rej,
        "candidate_unavailable": shadow_unavailable,
        "false_positive_abstentions": shadow_correct,
        "protective_abstentions": protective_abstentions,
        "shadow_executable": shadow_executable,
        "shadow_precision": shadow_precision,
        "cases": shadow_case_results,
    }

    with shadow_file.open("w", encoding="utf-8") as f:
        json.dump(shadow_summary, f, indent=2)

    return shadow_summary


def classify_case_unresolved(notes: list[str], grounding_deficit: bool) -> str:
    if not notes:
        return "NONE"
    has_hard = any(classify_unresolved_note(n) == UnresolvedNoteCategory.HARD_BLOCKER for n in notes)
    if has_hard:
        return "HARD_BLOCKER_PRESENT"
    if grounding_deficit:
        return "GROUNDING_OR_RELATIONSHIP_DEFICIT"
    has_only_soft = all(
        classify_unresolved_note(n) in {
            UnresolvedNoteCategory.SOFT_ASSUMPTION,
            UnresolvedNoteCategory.SOFT_CAVEAT,
            UnresolvedNoteCategory.TIE_BREAK_NOTE,
        }
        for n in notes
    )
    if has_only_soft:
        return "SOFT_UNCERTAINTY_ONLY"
    return "MIXED_OR_UNKNOWN"


def compute_replicate_metrics(run_dir: Path, shadow_summary: dict[str, Any]) -> dict[str, Any]:
    cases_file = run_dir / "cases.jsonl"
    cases = []
    with cases_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))

    N = len(cases)
    success_cases = [c for c in cases if c.get("runtime_status") == "SUCCESS"]
    unresolved_cases = [c for c in cases if c.get("runtime_status") == "UNRESOLVED"]
    generation_failed_cases = [c for c in cases if c.get("runtime_status") == "GENERATION_FAILED"]

    executed_queries = len(success_cases)
    executed_correct = sum(1 for c in success_cases if c.get("execution_correct") is True)
    executed_incorrect = sum(1 for c in success_cases if c.get("execution_correct") is False)

    ex_official = executed_correct / N if N > 0 else 0.0
    executed_precision = executed_correct / executed_queries if executed_queries > 0 else 0.0
    incorrect_execution_rate = executed_incorrect / N if N > 0 else 0.0
    unresolved_rate = len(unresolved_cases) / N if N > 0 else 0.0

    escalated = sum(1 for c in cases if c.get("escalated") is True)
    same_context_stop = sum(1 for c in cases if c.get("same_context_stop") is True)
    success_after_esc = sum(
        1 for c in cases
        if c.get("escalated") is True and c.get("runtime_status") == "SUCCESS" and c.get("execution_correct") is True
    )

    # Prompt behavior
    cases_with_unresolved = 0
    total_unresolved_notes = 0
    cases_with_assumptions = 0
    total_assumptions = 0
    notes_counter = Counter()
    case_tax_counter = Counter()

    for c in cases:
        # Check notes
        u_notes = (
            c.get("rejected_candidate_unresolved")
            or c.get("solver_unresolved")
            or []
        )
        if u_notes:
            cases_with_unresolved += 1
            total_unresolved_notes += len(u_notes)
            for n in u_notes:
                cat = classify_unresolved_note(n)
                notes_counter[cat.value] += 1
            case_tax = classify_case_unresolved(u_notes, False)
            case_tax_counter[case_tax] += 1

        a_notes = (
            c.get("candidate_assumptions")
            or c.get("rejected_candidate_assumptions")
            or []
        )
        if a_notes:
            cases_with_assumptions += 1
            total_assumptions += len(a_notes)

    avg_unresolved_entries = total_unresolved_notes / N if N > 0 else 0.0
    avg_assumptions_entries = total_assumptions / N if N > 0 else 0.0

    latencies = [c.get("latency_ms", 0.0) for c in cases]
    latencies.sort()
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    p50_lat = latencies[len(latencies) // 2] if latencies else 0.0
    p95_lat = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    solver_calls = [c.get("solver_calls") or 1 for c in cases]
    avg_solver_calls = sum(solver_calls) / len(solver_calls) if solver_calls else 0.0

    grounding_calls = [c.get("grounding_calls") or 1 for c in cases]
    avg_grounding_calls = sum(grounding_calls) / len(grounding_calls) if grounding_calls else 0.0

    fp_abs = shadow_summary.get("false_positive_abstentions", 0)
    prot_abs = shadow_summary.get("protective_abstentions", 0)
    shadow_prec = shadow_summary.get("shadow_precision", 0.0)

    return {
        "run_id": run_dir.name,
        "total_cases": N,
        "ex_official": ex_official,
        "executed_queries": executed_queries,
        "executed_correct": executed_correct,
        "executed_incorrect": executed_incorrect,
        "unresolved_count": len(unresolved_cases),
        "unresolved_rate": unresolved_rate,
        "generation_failed_count": len(generation_failed_cases),
        "executed_precision": executed_precision,
        "incorrect_execution_rate": incorrect_execution_rate,
        "false_positive_abstentions": fp_abs,
        "false_positive_abstention_rate": fp_abs / N if N > 0 else 0.0,
        "protective_abstentions": prot_abs,
        "protective_abstention_rate": prot_abs / N if N > 0 else 0.0,
        "shadow_precision": shadow_prec,
        "escalation_rate": escalated / N if N > 0 else 0.0,
        "same_context_stop_rate": same_context_stop / escalated if escalated > 0 else 0.0,
        "success_after_escalation": success_after_esc,
        "avg_grounding_calls": avg_grounding_calls,
        "avg_solver_calls": avg_solver_calls,
        "cases_with_unresolved": cases_with_unresolved,
        "cases_with_unresolved_pct": cases_with_unresolved / N if N > 0 else 0.0,
        "avg_unresolved_entries": avg_unresolved_entries,
        "cases_with_assumptions": cases_with_assumptions,
        "cases_with_assumptions_pct": cases_with_assumptions / N if N > 0 else 0.0,
        "avg_assumptions_entries": avg_assumptions_entries,
        "notes_tax_counts": dict(notes_counter),
        "case_tax_counts": dict(case_tax_counter),
        "avg_latency_ms": avg_lat,
        "p50_latency_ms": p50_lat,
        "p95_latency_ms": p95_lat,
    }


def compute_arm_summary(replicate_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "ex_official",
        "unresolved_rate",
        "executed_precision",
        "incorrect_execution_rate",
        "false_positive_abstention_rate",
        "protective_abstention_rate",
        "shadow_precision",
        "escalation_rate",
        "same_context_stop_rate",
        "cases_with_unresolved_pct",
        "avg_unresolved_entries",
        "cases_with_assumptions_pct",
        "avg_assumptions_entries",
        "avg_latency_ms",
        "p50_latency_ms",
        "p95_latency_ms",
        "avg_solver_calls",
        "avg_grounding_calls",
    ]
    summary = {}
    for k in keys:
        vals = [r[k] for r in replicate_metrics]
        mean_val = sum(vals) / len(vals)
        std_val = math.sqrt(sum((v - mean_val) ** 2 for v in vals) / len(vals)) if len(vals) > 1 else 0.0
        summary[k] = {
            "mean": round(mean_val, 4),
            "std": round(std_val, 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "replicates": [round(v, 4) for v in vals],
        }

    # Sum totals across replicates
    for k in [
        "executed_queries",
        "executed_correct",
        "executed_incorrect",
        "unresolved_count",
        "false_positive_abstentions",
        "protective_abstentions",
    ]:
        vals = [r[k] for r in replicate_metrics]
        summary[k] = {
            "mean": round(sum(vals) / len(vals), 2),
            "std": round(math.sqrt(sum((v - (sum(vals)/len(vals))) ** 2 for v in vals) / len(vals)), 2),
            "min": min(vals),
            "max": max(vals),
            "replicates": vals,
        }

    return summary


def compute_paired_case_transitions(
    control_cases: list[dict[str, Any]],
    arm_a_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Compare case by case
    arm_a_map = {c["case_id"]: c for c in arm_a_cases}
    transitions = []

    for ctrl in control_cases:
        cid = ctrl["case_id"]
        arm = arm_a_map.get(cid)
        if not arm:
            continue

        ctrl_status = ctrl.get("runtime_status")
        ctrl_corr = ctrl.get("execution_correct")
        arm_status = arm.get("runtime_status")
        arm_corr = arm.get("execution_correct")

        # Classify transition
        trans_type = "UNCHANGED"
        if ctrl_corr is not True and arm_corr is True:
            if ctrl_status == "UNRESOLVED":
                trans_type = "UNRESOLVED_TO_CORRECT"
            elif ctrl_status == "SUCCESS" and ctrl_corr is False:
                trans_type = "INCORRECT_TO_CORRECT"
            else:
                trans_type = "FAILED_TO_CORRECT"
        elif ctrl_corr is True and arm_corr is not True:
            if arm_status == "UNRESOLVED":
                trans_type = "CORRECT_TO_UNRESOLVED"
            else:
                trans_type = "CORRECT_TO_INCORRECT"
        elif ctrl_status == "UNRESOLVED" and arm_status == "SUCCESS" and arm_corr is False:
            trans_type = "UNRESOLVED_TO_INCORRECT"
        elif ctrl_status == "UNRESOLVED" and arm_status == "UNRESOLVED":
            trans_type = "REMAINED_UNRESOLVED"
        elif ctrl_corr is True and arm_corr is True:
            trans_type = "REMAINED_CORRECT"
        elif ctrl_corr is False and arm_corr is False:
            trans_type = "REMAINED_INCORRECT"

        transitions.append({
            "case_id": cid,
            "db_id": ctrl["db_id"],
            "control_status": ctrl_status,
            "control_correct": ctrl_corr,
            "arm_a_status": arm_status,
            "arm_a_correct": arm_corr,
            "transition": trans_type,
            "control_rejected_sql": ctrl.get("rejected_candidate_sql"),
            "arm_a_generated_sql": arm.get("generated_sql"),
            "arm_a_rejected_sql": arm.get("rejected_candidate_sql"),
        })

    return transitions


async def main():
    env = load_env()
    api_key = env.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY missing from .env")
        sys.exit(1)

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    bundles_list = load_benchmark_cases(PILOT_DATASET, BenchmarkCaseFilter(executable_only=True))
    bundles = {b.inference_case.case_id: b for b in bundles_list}
    print(f"Loaded {len(bundles)} executable Pilot cases.")

    # 1. Run all 6 benchmark replicates
    for config in RUN_CONFIGS:
        await execute_run(config, api_key, concurrency=4)

    # 2. Run shadow evaluation on all 6 replicates
    evaluator = ShadowEvaluator(database_root=DATABASE_ROOT)
    run_metrics = {}
    shadow_summaries = {}

    for config in RUN_CONFIGS:
        run_id = config["run_id"]
        run_dir = RESULTS_ROOT / run_id
        print(f"[{run_id}] Running offline shadow evaluation...")
        shadow_sum = run_shadow_eval_for_run(run_dir, bundles, evaluator)
        shadow_summaries[run_id] = shadow_sum
        replicate_met = compute_replicate_metrics(run_dir, shadow_sum)
        run_metrics[run_id] = replicate_met

    # Group replicates by arm
    control_reps = [run_metrics[c["run_id"]] for c in RUN_CONFIGS if c["arm"] == "Control"]
    arm_a_reps = [run_metrics[c["run_id"]] for c in RUN_CONFIGS if c["arm"] == "Arm A"]

    control_summary = compute_arm_summary(control_reps)
    arm_a_summary = compute_arm_summary(arm_a_reps)

    # Compute deltas
    delta = {
        "delta_ex_official": round(arm_a_summary["ex_official"]["mean"] - control_summary["ex_official"]["mean"], 4),
        "delta_unresolved_rate": round(arm_a_summary["unresolved_rate"]["mean"] - control_summary["unresolved_rate"]["mean"], 4),
        "delta_executed_precision": round(arm_a_summary["executed_precision"]["mean"] - control_summary["executed_precision"]["mean"], 4),
        "delta_incorrect_execution_rate": round(arm_a_summary["incorrect_execution_rate"]["mean"] - control_summary["incorrect_execution_rate"]["mean"], 4),
        "delta_false_positive_abstention_rate": round(arm_a_summary["false_positive_abstention_rate"]["mean"] - control_summary["false_positive_abstention_rate"]["mean"], 4),
        "delta_protective_abstention_rate": round(arm_a_summary["protective_abstention_rate"]["mean"] - control_summary["protective_abstention_rate"]["mean"], 4),
    }

    # Case transitions: compute between replicate 1 of both arms (and also all 3 paired)
    ctrl_r1_cases = [json.loads(line) for line in (RESULTS_ROOT / "p7b_control_r1" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    arm_a_r1_cases = [json.loads(line) for line in (RESULTS_ROOT / "p7b_arm_a_r1" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    transitions = compute_paired_case_transitions(ctrl_r1_cases, arm_a_r1_cases)

    transitions_file = RESULTS_ROOT / "case_transitions.jsonl"
    with transitions_file.open("w", encoding="utf-8") as f:
        for t in transitions:
            f.write(json.dumps(t) + "\n")

    trans_counts = Counter(t["transition"] for t in transitions)

    # Save comparison.json
    comparison = {
        "dataset": {
            "name": "t2s_pilot_v1",
            "executable_cases": len(bundles),
            "replicates_per_arm": 3,
            "eval_v1_used_for_tuning": False,
        },
        "control_summary": control_summary,
        "arm_a_summary": arm_a_summary,
        "delta": delta,
        "replicate_metrics": run_metrics,
        "transition_counts_r1": dict(trans_counts),
    }

    comparison_file = RESULTS_ROOT / "comparison.json"
    with comparison_file.open("w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    # Generate summary markdown
    summary_md = f"""# P7-B Controlled Uncertainty Prompt Calibration — Summary

## Experiment Overview
- **Dataset**: 85 executable cases from `benchmarks/t2s/datasets/t2s_pilot_v1.jsonl`
- **Replicates**: 3 Control runs (`v001`), 3 Arm A runs (`v002`)
- **Primary Target**: Official BIRD Gold (`EX_official`)
- **Eval v1 Used**: NO (completely frozen)

## Primary Results (Mean ± Std [Min, Max])

| Metric | Control (v001) | Arm A (v002) | Delta (Arm A - Control) |
|---|---|---|---|
| **Execution Accuracy (EX)** | {control_summary['ex_official']['mean']*100:.2f}% ± {control_summary['ex_official']['std']*100:.2f}% | {arm_a_summary['ex_official']['mean']*100:.2f}% ± {arm_a_summary['ex_official']['std']*100:.2f}% | **{delta['delta_ex_official']*100:+.2f}%** |
| **UNRESOLVED Rate** | {control_summary['unresolved_rate']['mean']*100:.2f}% ± {control_summary['unresolved_rate']['std']*100:.2f}% | {arm_a_summary['unresolved_rate']['mean']*100:.2f}% ± {arm_a_summary['unresolved_rate']['std']*100:.2f}% | **{delta['delta_unresolved_rate']*100:+.2f}%** |
| **Executed Query Precision** | {control_summary['executed_precision']['mean']*100:.2f}% ± {control_summary['executed_precision']['std']*100:.2f}% | {arm_a_summary['executed_precision']['mean']*100:.2f}% ± {arm_a_summary['executed_precision']['std']*100:.2f}% | **{delta['delta_executed_precision']*100:+.2f}%** |
| **Incorrect Execution Rate** | {control_summary['incorrect_execution_rate']['mean']*100:.2f}% ± {control_summary['incorrect_execution_rate']['std']*100:.2f}% | {arm_a_summary['incorrect_execution_rate']['mean']*100:.2f}% ± {arm_a_summary['incorrect_execution_rate']['std']*100:.2f}% | **{delta['delta_incorrect_execution_rate']*100:+.2f}%** |

## Abstention & Shadow Evaluation

| Metric | Control (v001) | Arm A (v002) | Delta |
|---|---|---|---|
| **False-Positive Abstentions (Mean Count)** | {control_summary['false_positive_abstentions']['mean']:.1f} / 85 | {arm_a_summary['false_positive_abstentions']['mean']:.1f} / 85 | {arm_a_summary['false_positive_abstentions']['mean'] - control_summary['false_positive_abstentions']['mean']:+.1f} |
| **Protective Abstentions (Mean Count)** | {control_summary['protective_abstentions']['mean']:.1f} / 85 | {arm_a_summary['protective_abstentions']['mean']:.1f} / 85 | {arm_a_summary['protective_abstentions']['mean'] - control_summary['protective_abstentions']['mean']:+.1f} |
| **Shadow Precision** | {control_summary['shadow_precision']['mean']*100:.2f}% | {arm_a_summary['shadow_precision']['mean']*100:.2f}% | {arm_a_summary['shadow_precision']['mean']*100 - control_summary['shadow_precision']['mean']*100:+.2f}% |

## Prompt Behavior

| Metric | Control (v001) | Arm A (v002) |
|---|---|---|
| **Cases with unresolved != []** | {control_summary['cases_with_unresolved_pct']['mean']*100:.1f}% | {arm_a_summary['cases_with_unresolved_pct']['mean']*100:.1f}% |
| **Avg unresolved notes / case** | {control_summary['avg_unresolved_entries']['mean']:.2f} | {arm_a_summary['avg_unresolved_entries']['mean']:.2f} |
| **Cases with assumptions != []** | {control_summary['cases_with_assumptions_pct']['mean']*100:.1f}% | {arm_a_summary['cases_with_assumptions_pct']['mean']*100:.1f}% |
| **Avg assumptions notes / case** | {control_summary['avg_assumptions_entries']['mean']:.2f} | {arm_a_summary['avg_assumptions_entries']['mean']:.2f} |

## Case Transitions (R1 Representative)
- Control Unresolved -> Arm A Correct: {trans_counts.get('UNRESOLVED_TO_CORRECT', 0)}
- Control Incorrect -> Arm A Correct: {trans_counts.get('INCORRECT_TO_CORRECT', 0)}
- Control Unresolved -> Arm A Incorrect: {trans_counts.get('UNRESOLVED_TO_INCORRECT', 0)}
- Control Correct -> Arm A Incorrect: {trans_counts.get('CORRECT_TO_INCORRECT', 0)}
- Remained Correct: {trans_counts.get('REMAINED_CORRECT', 0)}
- Remained Unresolved: {trans_counts.get('REMAINED_UNRESOLVED', 0)}
"""
    (RESULTS_ROOT / "summary.md").write_text(summary_md, encoding="utf-8")
    print("Experiment complete! Wrote comparison.json, case_transitions.jsonl, and summary.md")


if __name__ == "__main__":
    asyncio.run(main())
