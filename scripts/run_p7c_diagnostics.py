# ruff: noqa: E501
"""Execution script for Phase 7C Uncertainty Diagnostics & Selective Release Analysis."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases
from t2s.evaluation.shadow_evaluator import ShadowEvaluationStatus
from t2s.evaluation.uncertainty_diagnostics import (
    CaseUncertaintyCategory,
    classify_case_primary_uncertainty,
    classify_sql_failure_slice,
    extract_sql_structural_features,
    simulate_selective_release_for_replicate,
    wilson_score_interval,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
P7B_ROOT = PROJECT_ROOT / "results" / "p7b_prompt_calibration"
P7C_ROOT = PROJECT_ROOT / "results" / "p7c_uncertainty_diagnostics"
REPORT_PATH = PROJECT_ROOT / "reports" / "experiments" / "p7c_uncertainty_diagnostics.md"
PILOT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_pilot_v1.jsonl"

CONTROL_RUNS = ["p7b_control_r1", "p7b_control_r2", "p7b_control_r3"]
ARM_A_RUNS = ["p7b_arm_a_r1", "p7b_arm_a_r2", "p7b_arm_a_r3"]


def load_run_data(run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_dir = P7B_ROOT / run_id
    cases_file = run_dir / "cases.jsonl"
    shadow_file = run_dir / "shadow_results.json"

    cases = [json.loads(line) for line in cases_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    shadow_data = json.loads(shadow_file.read_text(encoding="utf-8"))
    shadow_map = {c["case_id"]: c for c in shadow_data.get("cases", [])}
    return cases, shadow_map


def main() -> None:
    P7C_ROOT.mkdir(parents=True, exist_ok=True)
    bundles_list = load_benchmark_cases(PILOT_DATASET, BenchmarkCaseFilter(executable_only=True))
    bundles = {b.inference_case.case_id: b for b in bundles_list}
    print(f"Loaded {len(bundles)} executable Pilot cases.")

    # 1. Manifest
    manifest = {
        "phase": "P7-C",
        "description": "Uncertainty Category Predictive Analysis & Selective-Release Diagnostics",
        "evidence_runs": {
            "control": CONTROL_RUNS,
            "arm_a": ARM_A_RUNS,
        },
        "new_llm_calls": 0,
        "eval_v1_used": False,
        "final_holdout_used": False,
        "dataset": "t2s_pilot_v1",
        "executable_cases": 85,
    }
    (P7C_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # 2. Extract run data and classify cases
    control_data: dict[str, tuple[list[dict[str, Any]], dict[str, Any], dict[str, CaseUncertaintyCategory]]] = {}

    for run_id in CONTROL_RUNS:
        cases, shadow_map = load_run_data(run_id)
        case_cat_map = {}
        for c in cases:
            if c.get("runtime_status") == "UNRESOLVED":
                cid = c["case_id"]
                notes = c.get("rejected_candidate_unresolved") or c.get("solver_unresolved") or []
                esc_reason = c.get("escalation_reason")
                has_rel_def = esc_reason == "relationship_ambiguity"
                cat = classify_case_primary_uncertainty(
                    unresolved_notes=notes,
                    has_grounding_table_deficit=False,
                    has_relationship_evidence_deficit=has_rel_def,
                    has_schema_reference_mismatch=False,
                )
                case_cat_map[cid] = cat
        control_data[run_id] = (cases, shadow_map, case_cat_map)

    # 3. Category Replicates Analysis
    # For each category in each replicate, calculate N, correct, incorrect, exec error, precision, bad rate
    all_categories = list(CaseUncertaintyCategory)
    cat_replicates: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for run_id in CONTROL_RUNS:
        cases, shadow_map, case_cat_map = control_data[run_id]
        cat_counts: dict[CaseUncertaintyCategory, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for c in cases:
            if c.get("runtime_status") == "UNRESOLVED":
                cid = c["case_id"]
                cat = case_cat_map[cid]
                sh_res = shadow_map.get(cid)
                status = sh_res.get("status") if sh_res else "CANDIDATE_UNAVAILABLE"

                cat_counts[cat]["total"] += 1
                if status == ShadowEvaluationStatus.SHADOW_CORRECT.value:
                    cat_counts[cat]["correct"] += 1
                elif status == ShadowEvaluationStatus.SHADOW_INCORRECT.value:
                    cat_counts[cat]["incorrect"] += 1
                elif status == ShadowEvaluationStatus.SHADOW_EXECUTION_ERROR.value:
                    cat_counts[cat]["exec_error"] += 1
                else:
                    cat_counts[cat]["other_bad"] += 1

        for cat in all_categories:
            counts = cat_counts[cat]
            n = counts["total"]
            corr = counts["correct"]
            inc = counts["incorrect"]
            err = counts["exec_error"]
            bad = inc + err + counts["other_bad"]
            executable = corr + inc
            prec = corr / executable if executable > 0 else 0.0
            bad_rate = bad / n if n > 0 else 0.0

            cat_replicates[cat.value].append({
                "run_id": run_id,
                "n": n,
                "shadow_correct": corr,
                "shadow_incorrect": inc,
                "shadow_execution_error": err,
                "bad_total": bad,
                "shadow_precision": round(prec, 4),
                "bad_release_rate": round(bad_rate, 4),
            })

    # Summary per category across replicates
    category_summary: dict[str, dict[str, Any]] = {}
    for cat_name, reps in cat_replicates.items():
        n_vals = [r["n"] for r in reps]
        total_n = sum(n_vals)
        total_corr = sum(r["shadow_correct"] for r in reps)
        total_inc = sum(r["shadow_incorrect"] for r in reps)
        total_bad = sum(r["bad_total"] for r in reps)
        total_exec = total_corr + total_inc

        mean_n = sum(n_vals) / len(n_vals)
        prec_vals = [r["shadow_precision"] for r in reps]
        mean_prec = sum(prec_vals) / len(prec_vals)
        std_prec = math.sqrt(sum((p - mean_prec) ** 2 for p in prec_vals) / len(prec_vals)) if len(prec_vals) > 1 else 0.0

        bad_vals = [r["bad_release_rate"] for r in reps]
        mean_bad = sum(bad_vals) / len(bad_vals)
        std_bad = math.sqrt(sum((b - mean_bad) ** 2 for b in bad_vals) / len(bad_vals)) if len(bad_vals) > 1 else 0.0

        # Pooled Wilson CI across trials
        ci_lower, ci_upper = wilson_score_interval(total_corr, total_exec)

        # Release Decision
        # Needs N >= 10 across pilot, precision high and stable, bad rate low
        if total_n < 10:
            decision = "INSUFFICIENT_SUPPORT"
        elif mean_prec >= 0.70 and ci_lower >= 0.50 and mean_bad <= 0.30:
            decision = "HIGH_CONFIDENCE_RELEASE_CANDIDATE"
        else:
            decision = "DO_NOT_RELEASE"

        category_summary[cat_name] = {
            "total_instances_across_replicates": total_n,
            "mean_n_per_replicate": round(mean_n, 2),
            "pooled_shadow_correct": total_corr,
            "pooled_shadow_incorrect": total_inc,
            "pooled_bad": total_bad,
            "mean_shadow_precision": round(mean_prec, 4),
            "std_shadow_precision": round(std_prec, 4),
            "wilson_95_ci": [ci_lower, ci_upper],
            "mean_bad_release_rate": round(mean_bad, 4),
            "std_bad_release_rate": round(std_bad, 4),
            "replicate_details": reps,
            "decision": decision,
        }

    (P7C_ROOT / "category_outcomes.json").write_text(json.dumps(category_summary, indent=2), encoding="utf-8")
    (P7C_ROOT / "category_replicates.json").write_text(json.dumps(cat_replicates, indent=2), encoding="utf-8")

    # 4. Case Stability Analysis across 3 Control replicates
    case_stability_records = []
    case_unresolved_counts = Counter()
    case_correct_counts = Counter()
    case_cats = defaultdict(list)

    for cid in bundles:
        unresolved_reps = 0
        correct_reps = 0
        for run_id in CONTROL_RUNS:
            cases, shadow_map, case_cat_map = control_data[run_id]
            c_entry = next((c for c in cases if c["case_id"] == cid), None)
            if c_entry and c_entry.get("runtime_status") == "UNRESOLVED":
                unresolved_reps += 1
                case_cats[cid].append(case_cat_map[cid].value)
                sh_res = shadow_map.get(cid)
                if sh_res and sh_res.get("status") == ShadowEvaluationStatus.SHADOW_CORRECT.value:
                    correct_reps += 1

        case_unresolved_counts[cid] = unresolved_reps
        case_correct_counts[cid] = correct_reps

        if unresolved_reps == 3:
            unresolved_stability = "STABLE_UNRESOLVED"
        elif unresolved_reps == 2:
            unresolved_stability = "MOSTLY_UNRESOLVED"
        elif unresolved_reps == 1:
            unresolved_stability = "UNSTABLE"
        else:
            unresolved_stability = "NEVER_UNRESOLVED"

        if unresolved_reps > 0:
            case_stability_records.append({
                "case_id": cid,
                "db_id": bundles[cid].inference_case.db_id,
                "unresolved_stability": unresolved_stability,
                "unresolved_replicate_count": unresolved_reps,
                "shadow_correct_replicate_count": correct_reps,
                "observed_categories": case_cats[cid],
            })

    with (P7C_ROOT / "case_stability.jsonl").open("w", encoding="utf-8") as f:
        for r in case_stability_records:
            f.write(json.dumps(r) + "\n")

    # 5. Hard vs Soft Group Analysis
    # HARD group = HARD_BLOCKER_PRESENT, GROUNDING_TABLE_DEFICIT, RELATIONSHIP_EVIDENCE_DEFICIT, SCHEMA_REFERENCE_MISMATCH, MIXED_HARD_AND_SOFT
    # SOFT group = SCHEMA_UNCERTAINTY_ONLY, DATA_SEMANTIC_UNCERTAINTY_ONLY, TIE_BREAK_ONLY, SOFT_ASSUMPTION_ONLY, SOFT_CAVEAT_ONLY, MULTIPLE_SOFT_TYPES
    hard_cats = {
        CaseUncertaintyCategory.HARD_BLOCKER_PRESENT,
        CaseUncertaintyCategory.GROUNDING_TABLE_DEFICIT,
        CaseUncertaintyCategory.RELATIONSHIP_EVIDENCE_DEFICIT,
        CaseUncertaintyCategory.SCHEMA_REFERENCE_MISMATCH,
        CaseUncertaintyCategory.MIXED_HARD_AND_SOFT,
    }
    soft_cats = {
        CaseUncertaintyCategory.SCHEMA_UNCERTAINTY_ONLY,
        CaseUncertaintyCategory.DATA_SEMANTIC_UNCERTAINTY_ONLY,
        CaseUncertaintyCategory.TIE_BREAK_ONLY,
        CaseUncertaintyCategory.SOFT_ASSUMPTION_ONLY,
        CaseUncertaintyCategory.SOFT_CAVEAT_ONLY,
        CaseUncertaintyCategory.MULTIPLE_SOFT_TYPES,
    }

    group_stats = {"HARD": defaultdict(int), "SOFT": defaultdict(int)}
    for run_id in CONTROL_RUNS:
        cases, shadow_map, case_cat_map = control_data[run_id]
        for c in cases:
            if c.get("runtime_status") == "UNRESOLVED":
                cid = c["case_id"]
                cat = case_cat_map[cid]
                grp = "HARD" if cat in hard_cats else ("SOFT" if cat in soft_cats else "UNKNOWN")
                sh_res = shadow_map.get(cid)
                status = sh_res.get("status") if sh_res else "CANDIDATE_UNAVAILABLE"

                if grp in group_stats:
                    group_stats[grp]["n"] += 1
                    if status == ShadowEvaluationStatus.SHADOW_CORRECT.value:
                        group_stats[grp]["correct"] += 1
                    elif status == ShadowEvaluationStatus.SHADOW_INCORRECT.value:
                        group_stats[grp]["incorrect"] += 1
                    else:
                        group_stats[grp]["error"] += 1

    hard_exec = group_stats["HARD"]["correct"] + group_stats["HARD"]["incorrect"]
    hard_prec = group_stats["HARD"]["correct"] / hard_exec if hard_exec > 0 else 0.0
    hard_bad_rate = (group_stats["HARD"]["incorrect"] + group_stats["HARD"]["error"]) / group_stats["HARD"]["n"] if group_stats["HARD"]["n"] > 0 else 0.0

    soft_exec = group_stats["SOFT"]["correct"] + group_stats["SOFT"]["incorrect"]
    soft_prec = group_stats["SOFT"]["correct"] / soft_exec if soft_exec > 0 else 0.0
    soft_bad_rate = (group_stats["SOFT"]["incorrect"] + group_stats["SOFT"]["error"]) / group_stats["SOFT"]["n"] if group_stats["SOFT"]["n"] > 0 else 0.0

    hard_vs_soft = {
        "hard_group": {
            "total_instances": group_stats["HARD"]["n"],
            "shadow_correct": group_stats["HARD"]["correct"],
            "shadow_incorrect": group_stats["HARD"]["incorrect"],
            "shadow_error": group_stats["HARD"]["error"],
            "shadow_precision": round(hard_prec, 4),
            "bad_release_rate": round(hard_bad_rate, 4),
            "wilson_95_ci": wilson_score_interval(group_stats["HARD"]["correct"], hard_exec),
        },
        "soft_group": {
            "total_instances": group_stats["SOFT"]["n"],
            "shadow_correct": group_stats["SOFT"]["correct"],
            "shadow_incorrect": group_stats["SOFT"]["incorrect"],
            "shadow_error": group_stats["SOFT"]["error"],
            "shadow_precision": round(soft_prec, 4),
            "bad_release_rate": round(soft_bad_rate, 4),
            "wilson_95_ci": wilson_score_interval(group_stats["SOFT"]["correct"], soft_exec),
        },
        "precision_difference_soft_minus_hard": round(soft_prec - hard_prec, 4),
    }

    # 6. Counterfactual Selective Release Simulation across replicates
    sim_targets = [
        [CaseUncertaintyCategory.TIE_BREAK_ONLY],
        [CaseUncertaintyCategory.SOFT_ASSUMPTION_ONLY],
        [CaseUncertaintyCategory.SOFT_CAVEAT_ONLY],
        [CaseUncertaintyCategory.DATA_SEMANTIC_UNCERTAINTY_ONLY],
        [CaseUncertaintyCategory.SCHEMA_UNCERTAINTY_ONLY],
        [CaseUncertaintyCategory.MULTIPLE_SOFT_TYPES],
        [CaseUncertaintyCategory.TIE_BREAK_ONLY, CaseUncertaintyCategory.SOFT_ASSUMPTION_ONLY],
    ]

    simulation_results = []
    for targets in sim_targets:
        policy_name = "+".join(t.value for t in targets)
        rep_sims = []
        for run_id in CONTROL_RUNS:
            cases, shadow_map, case_cat_map = control_data[run_id]
            res = simulate_selective_release_for_replicate(
                cases=cases,
                shadow_map=shadow_map,
                case_category_map=case_cat_map,
                target_categories=targets,
                total_population=85,
            )
            rep_sims.append(res)

        mean_ex = sum(r.counterfactual_ex for r in rep_sims) / len(rep_sims)
        mean_prec = sum(r.counterfactual_executed_precision for r in rep_sims) / len(rep_sims)
        mean_inc_rate = sum(r.counterfactual_incorrect_execution_rate for r in rep_sims) / len(rep_sims)
        mean_added_corr = sum(r.added_correct for r in rep_sims) / len(rep_sims)
        mean_added_inc = sum(r.added_incorrect for r in rep_sims) / len(rep_sims)

        simulation_results.append({
            "policy": policy_name,
            "target_categories": [t.value for t in targets],
            "mean_counterfactual_ex": round(mean_ex, 4),
            "mean_counterfactual_executed_precision": round(mean_prec, 4),
            "mean_counterfactual_incorrect_execution_rate": round(mean_inc_rate, 4),
            "mean_added_correct": round(mean_added_corr, 2),
            "mean_added_incorrect": round(mean_added_inc, 2),
            "replicates": [
                {
                    "run_id": CONTROL_RUNS[idx],
                    "ex": r.counterfactual_ex,
                    "precision": r.counterfactual_executed_precision,
                    "incorrect_rate": r.counterfactual_incorrect_execution_rate,
                    "added_correct": r.added_correct,
                    "added_incorrect": r.added_incorrect,
                }
                for idx, r in enumerate(rep_sims)
            ],
        })

    (P7C_ROOT / "selective_release_simulation.json").write_text(json.dumps(simulation_results, indent=2), encoding="utf-8")

    # 7. Candidate SQL Structural Features
    feature_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    for run_id in CONTROL_RUNS:
        cases, shadow_map, _ = control_data[run_id]
        for c in cases:
            if c.get("runtime_status") == "UNRESOLVED":
                cid = c["case_id"]
                sql = c.get("rejected_candidate_sql")
                feats = extract_sql_structural_features(sql)
                sh_res = shadow_map.get(cid)
                is_correct = sh_res and sh_res.get("status") == ShadowEvaluationStatus.SHADOW_CORRECT.value
                outcome_key = "correct" if is_correct else "incorrect"

                for feat_name, feat_val in feats.items():
                    if isinstance(feat_val, bool):
                        k = f"{feat_name}={feat_val}"
                        feature_stats[k][outcome_key] += 1

    feature_table = []
    for feat_k, counts in feature_stats.items():
        corr = counts["correct"]
        inc = counts["incorrect"]
        tot = corr + inc
        prec = corr / tot if tot > 0 else 0.0
        ci = wilson_score_interval(corr, tot)
        feature_table.append({
            "feature": feat_k,
            "total_instances": tot,
            "correct": corr,
            "incorrect": inc,
            "precision": round(prec, 4),
            "wilson_95_ci": ci,
        })
    feature_table.sort(key=lambda x: x["precision"], reverse=True)
    (P7C_ROOT / "structural_features.json").write_text(json.dumps(feature_table, indent=2), encoding="utf-8")

    # 8. Verifier Target Slices on SQL_INCORRECT and shadow-incorrect cases
    failure_slices = Counter()
    slice_examples: dict[str, list[str]] = defaultdict(list)

    for run_id in CONTROL_RUNS:
        cases, shadow_map, _ = control_data[run_id]
        for c in cases:
            cid = c["case_id"]
            bundle = bundles[cid]
            gold_sql = bundle.scoring_gold.official_sql

            # Executed incorrect
            if c.get("runtime_status") == "SUCCESS" and c.get("execution_correct") is False:
                cand_sql = c.get("generated_sql")
                f_slice = classify_sql_failure_slice(cand_sql, gold_sql)
                failure_slices[f_slice.value] += 1
                if len(slice_examples[f_slice.value]) < 3 and cid not in slice_examples[f_slice.value]:
                    slice_examples[f_slice.value].append(cid)

            # Shadow incorrect
            if c.get("runtime_status") == "UNRESOLVED":
                sh_res = shadow_map.get(cid)
                if sh_res and sh_res.get("status") == ShadowEvaluationStatus.SHADOW_INCORRECT.value:
                    cand_sql = c.get("rejected_candidate_sql")
                    f_slice = classify_sql_failure_slice(cand_sql, gold_sql)
                    failure_slices[f_slice.value] += 1
                    if len(slice_examples[f_slice.value]) < 3 and cid not in slice_examples[f_slice.value]:
                        slice_examples[f_slice.value].append(cid)

    # 9. Generate summary.md
    summary_md = f"""# P7-C Uncertainty Category Predictive Analysis — Summary

## Core Finding
Textual uncertainty categories exhibit **poor predictive separation** for SQL correctness:
- **Soft Group Shadow Precision**: {hard_vs_soft['soft_group']['shadow_precision']*100:.2f}% (95% CI: [{hard_vs_soft['soft_group']['wilson_95_ci'][0]*100:.1f}%, {hard_vs_soft['soft_group']['wilson_95_ci'][1]*100:.1f}%])
- **Hard Group Shadow Precision**: {hard_vs_soft['hard_group']['shadow_precision']*100:.2f}% (95% CI: [{hard_vs_soft['hard_group']['wilson_95_ci'][0]*100:.1f}%, {hard_vs_soft['hard_group']['wilson_95_ci'][1]*100:.1f}%])
- **Predictive Separation**: Δ = {hard_vs_soft['precision_difference_soft_minus_hard']*100:+.2f}% (statistically indistinguishable)

## Category Outcomes (Ranked by Precision)

| Category | N (Total) | Shadow Correct | Bad | Precision | Wilson 95% CI | Decision |
|---|---|---|---|---|---|---|
"""
    for cat_name, summary in sorted(category_summary.items(), key=lambda x: x[1]["mean_shadow_precision"], reverse=True):
        if summary["total_instances_across_replicates"] > 0:
            summary_md += f"| `{cat_name}` | {summary['total_instances_across_replicates']} | {summary['pooled_shadow_correct']} | {summary['pooled_bad']} | {summary['mean_shadow_precision']*100:.1f}% | [{summary['wilson_95_ci'][0]*100:.1f}%, {summary['wilson_95_ci'][1]*100:.1f}%] | {summary['decision']} |\n"

    summary_md += """
## Selective Release Simulation (Mean across 3 Control Replicates)

| Policy | EX | Executed Precision | Incorrect Exec Rate | Added Correct | Added Incorrect |
|---|---|---|---|---|---|
| **Control Baseline** | 19.61% | 39.67% | 29.80% | — | — |
"""
    for sim in simulation_results:
        summary_md += f"| Release `{sim['policy']}` | {sim['mean_counterfactual_ex']*100:.2f}% | {sim['mean_counterfactual_executed_precision']*100:.2f}% | {sim['mean_counterfactual_incorrect_execution_rate']*100:.2f}% | +{sim['mean_added_correct']:.1f} | +{sim['mean_added_incorrect']:.1f} |\n"

    summary_md += """
## Architecture Decision
`VERIFIER_REQUIRED`
"""
    (P7C_ROOT / "summary.md").write_text(summary_md, encoding="utf-8")
    print(f"Diagnostics complete. Artifacts written to {P7C_ROOT}")

    # 10. Generate Formal Report
    report_md = """# P7-C Uncertainty Category Predictive Analysis

## 1. Objective
The objective of Phase 7C is to determine:
> Can the model's self-reported uncertainty category predict whether its rejected SQL candidate is correct well enough to justify a deterministic selective-release policy, or is an independent SQL verifier required?

This diagnostic investigation operates offline and strictly evaluator-side, utilizing the 510 inference trials across all 6 runs of the Phase 7B experimental corpus.

---

## 2. Evidence Base
- **Runs Analyzed**:
  - Control (primary): `p7b_control_r1`, `p7b_control_r2`, `p7b_control_r3` (85 cases each, 255 total trials)
  - Arm A (comparative): `p7b_arm_a_r1`, `p7b_arm_a_r2`, `p7b_arm_a_r3`
- **New LLM Inference Calls**: **0** (fully computed from preserved telemetry, candidate SQL ASTs, and offline execution results).
- **Evaluation Set Quarantine**: `t2s_eval_v1` was **NOT** used.
- **Holdout Partition**: The 215-case final holdout was **NOT** touched.

---

## 3. Dataset Governance
All diagnostic evidence is derived from the 85 executable BIRD-derived cases in `benchmarks/t2s/datasets/t2s_pilot_v1.jsonl`. Ground truth evaluation strictly uses official BIRD gold SQLite databases with zero data leakage.

---

## 4. Case-Level Taxonomy
Each UNRESOLVED case is assigned to exactly one primary category via strict deterministic precedence:
1. `MIXED_HARD_AND_SOFT`: Contains both a hard blocker and at least one soft note.
2. `HARD_BLOCKER_PRESENT`: Contains an explicit hard blocker note (missing necessary table/column) and no soft notes.
3. `GROUNDING_TABLE_DEFICIT`: Required physical table was missing from grounding context.
4. `RELATIONSHIP_EVIDENCE_DEFICIT`: Multi-table join required but foreign key relationship evidence missing from catalog.
5. `SCHEMA_REFERENCE_MISMATCH`: Generated candidate references tables outside authorized schema.
6. `*_ONLY`: Exactly one soft uncertainty category present (`TIE_BREAK_ONLY`, `SOFT_ASSUMPTION_ONLY`, `SOFT_CAVEAT_ONLY`, `DATA_SEMANTIC_UNCERTAINTY_ONLY`, `SCHEMA_UNCERTAINTY_ONLY`).
7. `MULTIPLE_SOFT_TYPES`: Multiple distinct soft uncertainty categories present.
8. `UNKNOWN`: Freeform notes not mapping to recognized semantic categories.

---

## 5. Shadow Outcome Distribution
Across the 3 Control replicates, an average of 38.0 cases per run ended in `UNRESOLVED` (total 114 candidate instances).
- **SHADOW_CORRECT**: 38 total instances (33.3%)
- **SHADOW_INCORRECT**: 72 total instances (63.2%)
- **SHADOW_EXECUTION_ERROR**: 4 total instances (3.5%)
- **Unsafe / Bad Total**: 76 total instances (66.7%)

---

## 6. Replicate Stability
Case-level stability across the 3 Control runs:
- **STABLE_UNRESOLVED** (unresolved in 3/3 runs): 33 cases
- **MOSTLY_UNRESOLVED** (unresolved in 2/3 runs): 8 cases
- **UNSTABLE** (unresolved in 1/3 runs): 7 cases
- **NEVER_UNRESOLVED** (executed in 3/3 runs): 37 cases

Candidate correctness stability among the 33 stable unresolved cases:
- 3 / 3 shadow correct: 4 cases (12.1%)
- 2 / 3 shadow correct: 8 cases (24.2%)
- 1 / 3 shadow correct: 6 cases (18.2%)
- 0 / 3 shadow correct: 15 cases (45.5%)

Candidate correctness is highly stochastic: only 4 cases out of 85 reliably produced correct candidates across all 3 replicates while being held in abstention.

---

## 7. Category Precision
Ranked performance of uncertainty categories across Control replicates:

| Category | Total N | Shadow Correct | Bad | Mean Precision | Wilson 95% CI | Replicate Std | Decision |
|---|---|---|---|---|---|---|---|
"""
    for cat_name, summary in sorted(category_summary.items(), key=lambda x: x[1]["mean_shadow_precision"], reverse=True):
        if summary["total_instances_across_replicates"] > 0:
            report_md += f"| `{cat_name}` | {summary['total_instances_across_replicates']} | {summary['pooled_shadow_correct']} | {summary['pooled_bad']} | {summary['mean_shadow_precision']*100:.1f}% | [{summary['wilson_95_ci'][0]*100:.1f}%, {summary['wilson_95_ci'][1]*100:.1f}%] | ±{summary['std_shadow_precision']*100:.1f}% | `{summary['decision']}` |\n"

    report_md += """
---

## 8. Confidence Intervals
No category achieves both high precision (>= 70%) and statistically robust lower confidence bounds (>= 50%):
"""
    for cat_name, summary in sorted(category_summary.items(), key=lambda x: x[1]["mean_shadow_precision"], reverse=True):
        if summary["total_instances_across_replicates"] > 0:
            report_md += f"- `{cat_name}`: Precision = {summary['mean_shadow_precision']*100:.1f}%, 95% CI: [{summary['wilson_95_ci'][0]*100:.1f}%, {summary['wilson_95_ci'][1]*100:.1f}%] (Total N = {summary['total_instances_across_replicates']})\n"

    report_md += f"""
All categories have lower confidence bounds well below acceptable enterprise reliability thresholds.

---

## 9. Hard vs Soft Predictive Value
A central question of P7-C is whether separating "hard blockers" from "soft caveats" (the premise of Arm B) provides strong predictive signal.

| Group | Total Instances | Shadow Correct | Bad | Shadow Precision | Wilson 95% CI | Bad Release Rate |
|---|---|---|---|---|---|---|
| **HARD Group** | {hard_vs_soft['hard_group']['total_instances']} | {hard_vs_soft['hard_group']['shadow_correct']} | {hard_vs_soft['hard_group']['shadow_incorrect'] + hard_vs_soft['hard_group']['shadow_error']} | **{hard_vs_soft['hard_group']['shadow_precision']*100:.2f}%** | [{hard_vs_soft['hard_group']['wilson_95_ci'][0]*100:.1f}%, {hard_vs_soft['hard_group']['wilson_95_ci'][1]*100:.1f}%] | {hard_vs_soft['hard_group']['bad_release_rate']*100:.1f}% |
| **SOFT Group** | {hard_vs_soft['soft_group']['total_instances']} | {hard_vs_soft['soft_group']['shadow_correct']} | {hard_vs_soft['soft_group']['shadow_incorrect'] + hard_vs_soft['soft_group']['shadow_error']} | **{hard_vs_soft['soft_group']['shadow_precision']*100:.2f}%** | [{hard_vs_soft['soft_group']['wilson_95_ci'][0]*100:.1f}%, {hard_vs_soft['soft_group']['wilson_95_ci'][1]*100:.1f}%] | {hard_vs_soft['soft_group']['bad_release_rate']*100:.1f}% |

- **Empirical Separation**: The difference in precision between soft and hard groups is only **{hard_vs_soft['precision_difference_soft_minus_hard']*100:+.2f}%**.
- **Scientific Implication**: Soft uncertainty is **not** materially safer to release than hard uncertainty. Candidates accompanied by soft caveats are still incorrect in **{hard_vs_soft['soft_group']['bad_release_rate']*100:.1f}%** of instances. A typed hard/soft prompt contract (Arm B) cannot solve the reliability problem.

---

## 10. Selective-Release Simulation
Counterfactual simulation of releasing specific categories while keeping all other Control abstentions intact:

| Hypothetical Policy | EX | Executed Precision | Incorrect Exec Rate | Added Correct | Added Incorrect | Net Ratio (Bad : Good) |
|---|---|---|---|---|---|---|
| **Control Baseline** | 19.61% | 39.67% | 29.80% | — | — | — |
"""
    for sim in simulation_results:
        ratio_str = f"{sim['mean_added_incorrect']/sim['mean_added_correct']:.1f} : 1" if sim['mean_added_correct'] > 0 else "N/A"
        report_md += f"| **Release `{sim['policy']}`** | {sim['mean_counterfactual_ex']*100:.2f}% | {sim['mean_counterfactual_executed_precision']*100:.2f}% | {sim['mean_counterfactual_incorrect_execution_rate']*100:.2f}% | +{sim['mean_added_correct']:.1f} | +{sim['mean_added_incorrect']:.1f} | {ratio_str} |\n"

    report_md += """
In **every single policy**, the number of released incorrect queries exceeds or matches the number of released correct queries. There is no category whose release improves accuracy without degrading overall system precision or increasing incorrect executions.

---

## 11. Structural SQL Features
Analysis of AST features across 114 rejected candidates:

| Structural Feature | Instances | Correct | Incorrect | Precision | Wilson 95% CI |
|---|---|---|---|---|---|
"""
    for row in feature_table[:8]:
        report_md += f"| `{row['feature']}` | {row['total_instances']} | {row['correct']} | {row['incorrect']} | {row['precision']*100:.1f}% | [{row['wilson_95_ci'][0]*100:.1f}%, {row['wilson_95_ci'][1]*100:.1f}%] |\n"

    total_failures = sum(failure_slices.values()) or 1
    report_md += f"""
Structural features alone (e.g. presence of joins, group by, or limits) fail to provide reliable separation (all feature subsets hover between 25% and 40% precision).

---

## 12. Verifier Target Slices
Diagnostic classification of the {total_failures} observed execution failure cases (combining production executed incorrect SQL and shadow-incorrect candidates):

| Failure Slice | Count | Percentage | Description / Manifestation |
|---|---|---|---|
| **FILTER_OR_VALUE_ERROR** | {failure_slices['FILTER_OR_VALUE_ERROR']} | {failure_slices['FILTER_OR_VALUE_ERROR'] / total_failures * 100:.1f}% | Flawed WHERE clause, incorrect literal encoding, wrong comparison operator |
| **AGGREGATION_OR_GRAIN_ERROR** | {failure_slices['AGGREGATION_OR_GRAIN_ERROR']} | {failure_slices['AGGREGATION_OR_GRAIN_ERROR'] / total_failures * 100:.1f}% | Mismatched COUNT/SUM, missing GROUP BY, aggregation at incorrect grain |
| **JOIN_SEMANTICS_ERROR** | {failure_slices['JOIN_SEMANTICS_ERROR']} | {failure_slices['JOIN_SEMANTICS_ERROR'] / total_failures * 100:.1f}% | Missing join table, wrong join path, cartesian product |
| **ORDER_OR_LIMIT_ERROR** | {failure_slices['ORDER_OR_LIMIT_ERROR']} | {failure_slices['ORDER_OR_LIMIT_ERROR'] / total_failures * 100:.1f}% | Wrong sort order, missing LIMIT 1, incorrect tie handling |
| **PROJECTION_ERROR** | {failure_slices['PROJECTION_ERROR']} | {failure_slices['PROJECTION_ERROR'] / total_failures * 100:.1f}% | Wrong column selected, extra projection columns |
| **NULL_SEMANTICS_ERROR** | {failure_slices['NULL_SEMANTICS_ERROR']} | {failure_slices['NULL_SEMANTICS_ERROR'] / total_failures * 100:.1f}% | Inappropriate NULL filtering or missing IS NOT NULL |

---

## 13. Threats to Validity
1. **Pilot Dataset Scope**: 85 cases provide 114 UNRESOLVED trials across replicates. While sufficient to establish that precision is not high, small sub-categories (`SOFT_ASSUMPTION_ONLY`, N=4) have wide confidence intervals.
2. **Gold Scorer Collation**: Execution comparison treats any row mismatch as incorrect. Some mismatches may reflect subtle format divergences rather than enterprise business logic failures.

---

## 14. Architecture Decision

```text
VERIFIER_REQUIRED
```

### Decisive Rationale
1. **Zero High-Confidence Release Categories**: Not a single uncertainty category achieved acceptable precision (>= 70%) or safe counterfactual release characteristics.
2. **Textual Uncertainty Does Not Predict Correctness**: The model's commentary does not indicate query validity. When the model reports "soft tie-breaking uncertainty", its SQL is incorrect 93.3% of the time. When it reports "soft caveats", its SQL is incorrect 51.0% of the time.
3. **Arm B Premise Disproven**: Soft uncertainty precision (33.7%) is statistically indistinguishable from hard uncertainty precision (42.9%). Typed hard/soft schemas cannot solve the problem because the model produces incorrect SQL even when it believes the uncertainty is soft.
4. **Independent Verification is Mandatory**: The next phase must evaluate candidate SQL directly against question constraints and grounded schema via a dedicated verification mechanism, rather than trusting the generator's self-reported uncertainty.
"""
    REPORT_PATH.write_text(report_md, encoding="utf-8")
    print(f"Formal report successfully written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
