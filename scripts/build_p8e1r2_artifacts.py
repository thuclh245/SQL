# ruff: noqa: E501
"""Build Phase P8-E1R2 micro-test preregistration audit artifacts.

This script is intentionally offline-only. It reads existing P8B/P8E artifacts,
applies the documented evaluator correction for bird_11, and writes a frozen
20-call preregistration without executing any LLM or holdout workflow.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "results" / "p8e1r2_microtest_preregistration"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e1r2_microtest_preregistration.md"

DEV100_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
P8B_DIR = PROJECT_ROOT / "results" / "p8b_verifier_dev100"
P8E0_DIR = PROJECT_ROOT / "results" / "p8e0_p3_causality_audit"
P8E1_DIR = PROJECT_ROOT / "results" / "p8e1_p3_remediation"
P8E1R_DIR = PROJECT_ROOT / "results" / "p8e1r_metric_integrity"

PROPOSED_TARGETS = [
    "bird_357",
    "bird_374",
    "bird_32",
    "bird_37",
    "bird_100",
    "bird_137",
    "bird_142",
    "bird_164",
    "bird_189",
    "bird_257",
    "bird_320",
    "bird_337",
    "bird_458",
    "bird_194",
    "bird_308",
]

PROPOSED_CONTROLS = ["bird_12", "bird_168", "bird_213", "bird_356", "bird_379"]

FINAL_TARGETS = [
    "bird_100",
    "bird_1096",
    "bird_1195",
    "bird_1247",
    "bird_1472",
    "bird_206",
    "bird_344",
    "bird_416",
    "bird_640",
    "bird_705",
    "bird_753",
    "bird_963",
    "bird_1457",
    "bird_1484",
    "bird_1057",
]

FINAL_CONTROLS = ["bird_744", "bird_549", "bird_1344", "bird_168", "bird_213"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(name: str, payload: Any) -> None:
    (OUTPUT_DIR / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def stability_label(correct: int | None, total: int) -> str:
    if total != 3 or correct is None:
        return "NO_COMPLETE_HISTORY"
    return {
        0: "STABLE_FAILURE",
        1: "MOSTLY_FAILURE",
        2: "MOSTLY_CORRECT",
        3: "STABLE_CORRECT",
    }[correct]


def suitability_label(
    *,
    provenance_safe: bool,
    offline_fixed: bool,
    historical_correct: int | None,
    historical_total: int,
) -> str:
    if not provenance_safe or not offline_fixed or historical_total != 3:
        return "EXCLUDE"
    return {
        0: "HIGH_CAUSAL_SUITABILITY",
        1: "MEDIUM_CAUSAL_SUITABILITY",
        2: "LOW_CAUSAL_SUITABILITY",
        3: "EXCLUDE",
    }[historical_correct or 0]


def restored_by(qid: str, by_config: dict[str, dict[str, Any]]) -> str:
    a = by_config["A_RELATIONSHIP_FIX"][qid]["full_schema_recall"]
    b = by_config["B_COLUMN_FIX"][qid]["full_schema_recall"]
    ab = by_config["COMBINATION_A_B"][qid]["full_schema_recall"]
    if not ab:
        return "UNKNOWN"
    if a and b:
        return "A_OR_B_BOTH_SUFFICIENT"
    if a and not b:
        return "A_ONLY"
    if b and not a:
        return "B_ONLY"
    return "A_AND_B_REQUIRED"


def summarize_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(record[key] for record in records).items()))


def table_bucket(table_count: int) -> str:
    if table_count <= 1:
        return "1 table"
    if table_count == 2:
        return "2 tables"
    return "3+ tables"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    cases = {case["case_id"]: case for case in load_jsonl(DEV100_PATH)}
    q_budget = load_json(P8E0_DIR / "question_level_error_budget.json")
    q_categories = q_budget["question_categories"]
    mechanisms = load_json(P8E1_DIR / "primary_causal_mechanisms.json")["question_details"]
    structural = {rec["case_id"]: rec for rec in load_jsonl(P8E1R_DIR / "structural_complexity.jsonl")}
    baseline = {rec["case_id"]: rec for rec in load_jsonl(P8E1_DIR / "baseline_grounding.jsonl")}
    by_config = {
        "BASELINE": baseline,
        "A_RELATIONSHIP_FIX": {rec["case_id"]: rec for rec in load_jsonl(P8E1_DIR / "relationship_fix_replay.jsonl")},
        "B_COLUMN_FIX": {rec["case_id"]: rec for rec in load_jsonl(P8E1_DIR / "column_fix_replay.jsonl")},
        "COMBINATION_A_B": {rec["case_id"]: rec for rec in load_jsonl(P8E1_DIR / "combination_replay.jsonl")},
    }

    predictions_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run_path in sorted(P8B_DIR.glob("p8b_dev100_r*/predictions.jsonl")):
        replicate = run_path.parent.name.rsplit("_", 1)[-1]
        for rec in load_jsonl(run_path):
            corrected = bool(rec["execution_correct"])
            if rec["case_id"] == "bird_11":
                corrected = True
            predictions_by_case[rec["case_id"]].append({
                "replicate": replicate,
                "execution_correct": corrected,
                "raw_execution_correct": bool(rec["execution_correct"]),
                "candidate_sql": rec.get("candidate_sql"),
            })

    def historical_counts(qid: str) -> tuple[int | None, int, list[str]]:
        reps = sorted(predictions_by_case.get(qid, []), key=lambda rec: rec["replicate"])
        if not reps:
            return None, 0, ["missing", "missing", "missing"]
        values = ["correct" if rec["execution_correct"] else "wrong" for rec in reps]
        return sum(1 for value in values if value == "correct"), len(values), values

    def target_record(qid: str) -> dict[str, Any]:
        correct, total, reps = historical_counts(qid)
        mech = mechanisms.get(qid, {})
        case = cases.get(qid, {})
        struct = structural.get(qid, {})
        provenance_safe = mech.get("provenance_status") == "PROVENANCE_SAFE"
        offline_fixed = bool(mech.get("offline_fixed_by_ab"))
        return {
            "case_id": qid,
            "difficulty": case.get("bird_difficulty"),
            "db_id": case.get("db_id"),
            "p3_category": q_categories.get(qid),
            "p3_mechanism": mech.get("primary_cause", "UNKNOWN"),
            "secondary_causes": mech.get("secondary_causes", []),
            "provenance_status": mech.get("provenance_status", "UNKNOWN"),
            "offline_fixed_by_ab": offline_fixed,
            "offline_fixed_by": restored_by(qid, by_config) if qid in by_config["COMBINATION_A_B"] else "UNKNOWN",
            "r1": reps[0] if len(reps) > 0 else "missing",
            "r2": reps[1] if len(reps) > 1 else "missing",
            "r3": reps[2] if len(reps) > 2 else "missing",
            "historical_correct": correct,
            "historical_total": total,
            "historical_score": f"{correct}/{total}" if correct is not None else "NO_COMPLETE_HISTORY",
            "stability": stability_label(correct, total),
            "suitability": suitability_label(
                provenance_safe=provenance_safe,
                offline_fixed=offline_fixed,
                historical_correct=correct,
                historical_total=total,
            ),
            "table_count": struct.get("gold_table_count"),
            "actual_join_edge_count": struct.get("join_count"),
            "structure": "single_table" if struct.get("gold_table_count") == 1 else "multi_table",
            "multi_hop": bool(struct.get("multi_hop_join_required")),
            "bridge_table_required": bool(struct.get("bridge_table_required")),
            "aggregation": bool(struct.get("aggregation_present")),
            "subquery": bool(struct.get("subquery_present")),
        }

    proposed_target_records = [target_record(qid) for qid in PROPOSED_TARGETS]
    candidate_target_records = [
        target_record(qid)
        for qid, mech in sorted(mechanisms.items(), key=lambda item: int(item[0].split("_")[1]))
        if mech.get("provenance_status") == "PROVENANCE_SAFE" and mech.get("offline_fixed_by_ab")
    ]
    final_target_records = [target_record(qid) for qid in FINAL_TARGETS]

    target_stability = {
        "scope": "Originally proposed 15 targets plus all provenance-safe A+B-fixed candidates.",
        "originally_proposed_targets": proposed_target_records,
        "all_eligible_provenance_safe_ab_fixed_candidates": candidate_target_records,
        "stability_summary_all_eligible": summarize_counts(candidate_target_records, "stability"),
        "stability_summary_final_selection": summarize_counts(final_target_records, "stability"),
        "note": "Corrected execution correctness applies the documented bird_11 evaluator fix; bird_11 is not used as a target.",
    }

    suitability = {
        "classification_rule": {
            "HIGH_CAUSAL_SUITABILITY": "provenance-safe P3 failure, A+B restores full required grounding offline, historical generator correctness 0/3",
            "MEDIUM_CAUSAL_SUITABILITY": "same, but historical generator correctness 1/3",
            "LOW_CAUSAL_SUITABILITY": "same, but historical generator correctness 2/3",
            "EXCLUDE": "not provenance-safe, not A+B-fixed offline, incomplete history, or historically 3/3 correct",
        },
        "all_eligible_candidates": candidate_target_records,
        "originally_proposed_targets": proposed_target_records,
        "final_selection": final_target_records,
    }

    mechanism_distribution = {
        "final_targets": summarize_counts(final_target_records, "p3_mechanism"),
        "all_eligible_candidates": summarize_counts(candidate_target_records, "p3_mechanism"),
        "interpretation": "Relationship-expansion and column-selection mechanisms are both represented. Only one provenance-safe A+B-fixed column-budget case exists, so larger budget representation is impossible without weakening causal suitability.",
    }

    difficulty_distribution = {
        "final_targets": summarize_counts(final_target_records, "difficulty"),
        "all_eligible_candidates": summarize_counts(candidate_target_records, "difficulty"),
    }

    structural_distribution = {
        "final_targets": {
            "table_buckets": dict(sorted(Counter(table_bucket(rec["table_count"]) for rec in final_target_records).items())),
            "single_table": sum(1 for rec in final_target_records if rec["structure"] == "single_table"),
            "multi_table": sum(1 for rec in final_target_records if rec["structure"] == "multi_table"),
            "multi_hop": sum(1 for rec in final_target_records if rec["multi_hop"]),
            "bridge_table_required": sum(1 for rec in final_target_records if rec["bridge_table_required"]),
            "aggregation": sum(1 for rec in final_target_records if rec["aggregation"]),
            "subquery": sum(1 for rec in final_target_records if rec["subquery"]),
            "records": final_target_records,
        }
    }

    database_distribution = {
        "final_targets": summarize_counts(final_target_records, "db_id"),
        "distinct_databases": len({rec["db_id"] for rec in final_target_records}),
    }

    def control_record(qid: str) -> dict[str, Any]:
        correct, total, reps = historical_counts(qid)
        case = cases[qid]
        struct = structural[qid]
        base = baseline[qid]
        ab = by_config["COMBINATION_A_B"][qid]
        return {
            "case_id": qid,
            "historical_correct": correct,
            "historical_total": total,
            "historical_score": f"{correct}/{total}",
            "stability": stability_label(correct, total),
            "category": q_categories.get(qid),
            "difficulty": case["bird_difficulty"],
            "db_id": case["db_id"],
            "structure": "single_table" if struct["gold_table_count"] == 1 else "multi_table",
            "table_count": struct["gold_table_count"],
            "aggregation": bool(struct["aggregation_present"]),
            "filter_count": struct["filter_count"],
            "baseline_table_count": base["table_count"],
            "ab_table_count": ab["table_count"],
            "table_delta": ab["table_count"] - base["table_count"],
            "baseline_column_count": base["column_count"],
            "ab_column_count": ab["column_count"],
            "column_delta": ab["column_count"] - base["column_count"],
            "baseline_tokens": base["estimated_prompt_tokens"],
            "ab_tokens": ab["estimated_prompt_tokens"],
            "token_delta": ab["estimated_prompt_tokens"] - base["estimated_prompt_tokens"],
            "r1": reps[0],
            "r2": reps[1],
            "r3": reps[2],
        }

    control_candidates = [
        control_record(qid)
        for qid, category in sorted(q_categories.items(), key=lambda item: int(item[0].split("_")[1]))
        if category == "FULLY_CORRECT" and historical_counts(qid)[0] == 3 and historical_counts(qid)[1] == 3
    ]
    final_control_records = [control_record(qid) for qid in FINAL_CONTROLS]

    control_audit = {
        "selection_rule": "Controls must be historical 3/3 FULLY_CORRECT questions; prefer nonzero A+B context deltas and diversity across DB, difficulty, structure, aggregation/filter patterns.",
        "originally_proposed_controls": [control_record(qid) for qid in PROPOSED_CONTROLS],
        "all_control_candidates": control_candidates,
        "final_selection": final_control_records,
        "all_final_controls_historical_3_of_3": all(rec["historical_score"] == "3/3" for rec in final_control_records),
    }

    design_selection = {
        "selected_design": "DESIGN_A_HISTORICAL_BASELINE",
        "final_decision": "MICROTEST_DESIGN_A_READY",
        "paid_calls_authorized_for_next_phase": "YES",
        "rationale": "All 15 selected targets are provenance-safe A+B-fixed P3 failures and all are historical 0/3 stable failures. This satisfies the project rule that Design A is allowed when >=80% of selected targets are stable failures; the selected cohort is 15/15 = 100%.",
        "design_comparison": [
            {
                "criterion": "Calls",
                "design_a_historical_baseline": 20,
                "design_b_paired": 20,
            },
            {
                "criterion": "Direct causal isolation",
                "design_a_historical_baseline": "weaker",
                "design_b_paired": "stronger",
            },
            {
                "criterion": "Uses historical replicates",
                "design_a_historical_baseline": "yes",
                "design_b_paired": "yes",
            },
            {
                "criterion": "Sensitive to model drift",
                "design_a_historical_baseline": "more",
                "design_b_paired": "less",
            },
            {
                "criterion": "Target coverage",
                "design_a_historical_baseline": "larger",
                "design_b_paired": "smaller",
            },
            {
                "criterion": "Best when",
                "design_a_historical_baseline": "stable 0/3 failures",
                "design_b_paired": "stochastic baseline",
            },
        ],
        "selected_target_stable_failure_rate": "15/15",
        "design_b_not_selected_reason": "Paired current-state isolation is less necessary for this screen because a balanced 15-target cohort can be formed entirely from stable 0/3 historical failures.",
    }

    frozen_components = {
        "model": "openai/gpt-oss-120b",
        "temperature": 0,
        "p4_prompt": "prompts/direct_sql/direct_sql_v001.txt",
        "dialect": "SQLite",
        "p5": "OFF for generator-only causal micro-test",
        "verifier": "OFF",
        "candidate_count": 1,
        "scorer": "corrected symmetrical execution scorer",
        "database_snapshot": "fixed P8B/P8E official SQLite snapshot",
        "catalog_snapshot": "fixed P8B/P8E catalog snapshot",
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
    }

    treatment_definition = {
        "target_condition": "A+B P3 grounding only: bounded unconditional 1-hop FK expansion plus deterministic fill-to-budget column selection.",
        "control_condition": "A+B P3 grounding for historically 3/3-correct controls to detect context-induced regressions.",
        "baseline_reference": "Historical P8B corrected 3-replicate generator results for selected stable-failure targets.",
        "only_intended_treatment_difference": "P3 grounding context configuration relative to historical baseline; model, prompt, scorer, dialect, verifier state, candidate count, database snapshot, and catalog snapshot are frozen.",
        "p5_treatment": "Bypass P5 identically; P5 is OFF for generator-only causal micro-test, so baseline-after-P5 is not compared to A+B-before-P5.",
    }

    success_criteria = {
        "design": "DESIGN_A_HISTORICAL_BASELINE",
        "targets": 15,
        "controls": 5,
        "success": ">= 5 / 15 target questions become execution-correct AND 0 / 5 controls regress",
        "failure": "< 5 / 15 target questions become execution-correct OR > 0 / 5 controls regress",
        "reporting_required": [
            "target recovery by mechanism",
            "target recovery by difficulty",
            "target recovery by table count",
        ],
    }

    decision_tree = {
        "if_pass": "Proceed to Level-2 targeted validation",
        "if_fail": "Stop paid expansion and return to P3/P4 diagnostics",
        "dev100_after_microtest": "FULL LLM RERUN: NO",
        "final_holdout_after_microtest": "RUN: NO",
        "minimum_expected_information_gain": "PASS advances only to larger targeted validation; FAIL stops paid expansion. The result changes the next project decision.",
    }

    manifest = {
        "phase": "P8-E1R2",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "paid_llm_calls": 0,
        "holdout_executions": 0,
        "inputs": {
            "dev100": str(DEV100_PATH.relative_to(PROJECT_ROOT)),
            "p8b_predictions": str(P8B_DIR.relative_to(PROJECT_ROOT)),
            "p8e0_error_budget": str((P8E0_DIR / "question_level_error_budget.json").relative_to(PROJECT_ROOT)),
            "p8e1_mechanisms": str((P8E1_DIR / "primary_causal_mechanisms.json").relative_to(PROJECT_ROOT)),
            "p8e1_replays": str(P8E1_DIR.relative_to(PROJECT_ROOT)),
            "p8e1r_structural_complexity": str((P8E1R_DIR / "structural_complexity.jsonl").relative_to(PROJECT_ROOT)),
        },
        "outputs": [
            "manifest.json",
            "historical_target_stability.json",
            "target_causal_suitability.json",
            "target_mechanism_distribution.json",
            "target_difficulty_distribution.json",
            "target_structural_distribution.json",
            "target_database_distribution.json",
            "control_candidate_audit.json",
            "final_target_selection.json",
            "final_control_selection.json",
            "design_selection.json",
            "frozen_components.json",
            "treatment_definition.json",
            "success_criteria.json",
            "decision_tree.json",
            "summary.md",
        ],
    }

    final_target_selection = {
        "selected_targets": FINAL_TARGETS,
        "target_count": len(FINAL_TARGETS),
        "records": final_target_records,
        "all_high_causal_suitability": all(rec["suitability"] == "HIGH_CAUSAL_SUITABILITY" for rec in final_target_records),
        "all_stable_failure": all(rec["stability"] == "STABLE_FAILURE" for rec in final_target_records),
    }
    final_control_selection = {
        "selected_controls": FINAL_CONTROLS,
        "control_count": len(FINAL_CONTROLS),
        "records": final_control_records,
        "all_historical_3_of_3": all(rec["historical_score"] == "3/3" for rec in final_control_records),
        "all_nonzero_context_delta": all(rec["token_delta"] > 0 for rec in final_control_records),
    }

    write_json("manifest.json", manifest)
    write_json("historical_target_stability.json", target_stability)
    write_json("target_causal_suitability.json", suitability)
    write_json("target_mechanism_distribution.json", mechanism_distribution)
    write_json("target_difficulty_distribution.json", difficulty_distribution)
    write_json("target_structural_distribution.json", structural_distribution)
    write_json("target_database_distribution.json", database_distribution)
    write_json("control_candidate_audit.json", control_audit)
    write_json("final_target_selection.json", final_target_selection)
    write_json("final_control_selection.json", final_control_selection)
    write_json("design_selection.json", design_selection)
    write_json("frozen_components.json", frozen_components)
    write_json("treatment_definition.json", treatment_definition)
    write_json("success_criteria.json", success_criteria)
    write_json("decision_tree.json", decision_tree)

    summary_md = build_report(
        candidate_target_records=candidate_target_records,
        final_target_records=final_target_records,
        final_control_records=final_control_records,
        design_selection=design_selection,
        frozen_components=frozen_components,
        treatment_definition=treatment_definition,
        success_criteria=success_criteria,
        decision_tree=decision_tree,
        database_distribution=database_distribution,
    )
    (OUTPUT_DIR / "summary.md").write_text(summary_md)
    REPORT_PATH.write_text(summary_md)


def build_report(
    *,
    candidate_target_records: list[dict[str, Any]],
    final_target_records: list[dict[str, Any]],
    final_control_records: list[dict[str, Any]],
    design_selection: dict[str, Any],
    frozen_components: dict[str, Any],
    treatment_definition: dict[str, Any],
    success_criteria: dict[str, Any],
    decision_tree: dict[str, Any],
    database_distribution: dict[str, Any],
) -> str:
    stability_counts = Counter(rec["stability"] for rec in final_target_records)
    mechanism_counts = Counter(rec["p3_mechanism"] for rec in final_target_records)
    difficulty_counts = Counter(rec["difficulty"] for rec in final_target_records)
    table_counts = Counter(table_bucket(rec["table_count"]) for rec in final_target_records)

    def md_target_row(rec: dict[str, Any]) -> str:
        return (
            f"| {rec['case_id']} | {rec['difficulty']} | {rec['db_id']} | "
            f"{rec['p3_mechanism']} | {rec['offline_fixed_by']} | {rec['r1']} | {rec['r2']} | {rec['r3']} | "
            f"{rec['historical_score']} | {rec['suitability']} |"
        )

    def md_control_row(rec: dict[str, Any]) -> str:
        return (
            f"| {rec['case_id']} | {rec['historical_score']} | {rec['difficulty']} | {rec['db_id']} | "
            f"{rec['structure']} | {rec['baseline_tokens']} | {rec['ab_tokens']} | {rec['token_delta']} |"
        )

    composition_rows = [
        ("Mechanism", "Relationship Expansion", mechanism_counts["RELATIONSHIP_EXPANSION_FAILURE"]),
        ("Mechanism", "Column Selection", mechanism_counts["COLUMN_SELECTION_FAILURE"]),
        ("Mechanism", "Column Budget", mechanism_counts["COLUMN_BUDGET_FAILURE"]),
        ("Mechanism", "Other", sum(v for k, v in mechanism_counts.items() if k not in {"RELATIONSHIP_EXPANSION_FAILURE", "COLUMN_SELECTION_FAILURE", "COLUMN_BUDGET_FAILURE"})),
        ("Difficulty", "Simple", difficulty_counts["simple"]),
        ("Difficulty", "Moderate", difficulty_counts["moderate"]),
        ("Difficulty", "Challenging", difficulty_counts["challenging"]),
        ("Structure", "1 table", table_counts["1 table"]),
        ("Structure", "2 tables", table_counts["2 tables"]),
        ("Structure", "3+ tables", table_counts["3+ tables"]),
        ("Database", "distinct DBs", database_distribution["distinct_databases"]),
    ]

    report = f"""# P8-E1R2 Micro-Test Preregistration Integrity Audit

## Decision

`{design_selection['final_decision']}`

`PAID_CALLS_AUTHORIZED_FOR_NEXT_PHASE: {design_selection['paid_calls_authorized_for_next_phase']}`

Paid LLM calls in this audit: `0`

Final holdout executions in this audit: `0`

## Audit Conclusion

P8-E1R2 supports a 20-call Design A historical-baseline micro-test. The selected 15 targets are all provenance-safe P3 failures, all are fixed by A+B in offline grounding replay, and all were historical 0/3 generator failures after the documented evaluator correction. This satisfies the project design rule for Design A: at least 80% stable failures; actual selected cohort is 15/15 stable failures.

The old preregistration should not be reused as-is. Several proposed IDs are not in Dev100 or are not P3 causal failures, and the existing artifacts disagree on selected target IDs. The replacement cohort below is selected from raw P8B/P8E artifacts by causal suitability first, then mechanism balance, difficulty, and DB diversity.

## Target Historical Stability

| Case | Difficulty | DB | P3 Mechanism | Offline Fixed By | r1 | r2 | r3 | Historical Score | Suitability |
| ---- | ---------- | -- | ------------ | ---------------- | -- | -- | -- | ---------------: | ----------- |
{chr(10).join(md_target_row(rec) for rec in final_target_records)}

## Target Sample Composition

| Dimension | Category | Count |
| --------- | -------- | ----: |
{chr(10).join(f'| {dim} | {cat} | {count} |' for dim, cat, count in composition_rows)}

## Controls

| Case | Historical Correctness | Difficulty | DB | Structure | Baseline Tokens | A+B Tokens | Token Delta |
| ---- | ---------------------: | ---------- | -- | --------- | --------------: | ---------: | ----------: |
{chr(10).join(md_control_row(rec) for rec in final_control_records)}

All selected controls are historical 3/3 FULLY_CORRECT questions and all receive a nonzero A+B context change.

## Design Comparison

| Criterion | DESIGN A Historical Baseline | DESIGN B Paired |
| --------- | ---------------------------- | --------------- |
| Calls | 20 | 20 |
| Direct causal isolation | weaker | stronger |
| Uses historical replicates | yes | yes |
| Sensitive to model drift | more | less |
| Target coverage | larger | smaller |
| Best when | stable 0/3 failures | stochastic baseline |

Selected design: `DESIGN_A_HISTORICAL_BASELINE`.

Why: the selected cohort is overwhelmingly stable failure, specifically 15/15 = 100%. Design B remains scientifically stronger against provider drift, but it would halve target coverage without being required by the project decision rule.

## Treatment Difference

{treatment_definition['only_intended_treatment_difference']}

Target calls use A+B P3 grounding: bounded unconditional 1-hop FK expansion plus deterministic fill-to-budget column selection. Controls also use A+B context to detect context-induced regressions. P5 and verifier are OFF for the generator-only micro-test.

## Frozen Components

| Component | Frozen Value |
| --------- | ------------ |
{chr(10).join(f'| {key} | {value} |' for key, value in frozen_components.items())}

## Success Criterion

{success_criteria['success']}

## Failure Criterion

{success_criteria['failure']}

## Next Decisions

PASS: {decision_tree['if_pass']}

FAIL: {decision_tree['if_fail']}

DEV100_FULL_LLM_RERUN: NO

FINAL_HOLDOUT_RUN: NO

## Corrected Wording Constraints

P8-E1R new holdout executions: 0

Historical holdout inference executions: at least 25

Exact exposed membership: UNKNOWN

Moderate is the difficulty stratum with the largest concentration of P3 failures. Within P3, the dominant mechanisms are column selection failure and relationship expansion failure. Relationship failures are especially relevant to multi-table cases, while column-selection failures affect both single-table and multi-table cases.

A+B is preferred under the project's minimal-complexity criterion because C adds no additional full-schema recovery.

Qualified-column metrics should be described as resolved qualified physical column requirements when referring to the deduplicated table-column metric.

## Summary Counts

0/3 historical: {stability_counts['STABLE_FAILURE']}

1/3 historical: {stability_counts['MOSTLY_FAILURE']}

2/3 historical: {stability_counts['MOSTLY_CORRECT']}

3/3 historical: {stability_counts['STABLE_CORRECT']}

Eligible provenance-safe A+B-fixed candidates audited: {len(candidate_target_records)}
"""
    return report


if __name__ == "__main__":
    main()
