import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results" / "p8e2_microtest"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e2_microtest.md"
DEV100_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
BASELINE_GROUNDING = PROJECT_ROOT / "results" / "p8e1_p3_remediation" / "baseline_grounding.jsonl"

def main():
    dev100_cases = {
        c["case_id"]: c
        for c in [json.loads(l) for l in DEV100_PATH.read_text().splitlines() if l.strip()]
    }

    baseline_stats = {}
    if BASELINE_GROUNDING.exists():
        for line in BASELINE_GROUNDING.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                baseline_stats[rec["case_id"]] = rec

    call_ledger = [json.loads(l) for l in (RESULTS_DIR / "call_ledger.jsonl").read_text().splitlines() if l.strip()]
    request_metadata = [json.loads(l) for l in (RESULTS_DIR / "request_metadata.jsonl").read_text().splitlines() if l.strip()]
    raw_responses = [json.loads(l) for l in (RESULTS_DIR / "raw_responses.jsonl").read_text().splitlines() if l.strip()]
    execution_results = [json.loads(l) for l in (RESULTS_DIR / "execution_results.jsonl").read_text().splitlines() if l.strip()]
    target_results_data = json.loads((RESULTS_DIR / "target_results.json").read_text())
    control_results_data = json.loads((RESULTS_DIR / "control_results.json").read_text())
    mechanism_results_data = json.loads((RESULTS_DIR / "mechanism_results.json").read_text())

    # 1. Difficulty Results (Targets)
    diff_groups = {}
    for r in target_results_data["case_details"]:
        d = r["difficulty"]
        diff_groups.setdefault(d, []).append(r)

    difficulty_results_data = {
        diff: {
            "total": len(items),
            "recovered": sum(1 for i in items if i["outcome"] == "RECOVERED"),
            "recovery_rate": round(sum(1 for i in items if i["outcome"] == "RECOVERED") / len(items) * 100, 2),
            "cases": [i["case_id"] for i in items],
            "recovered_cases": [i["case_id"] for i in items if i["outcome"] == "RECOVERED"],
        }
        for diff, items in diff_groups.items()
    }
    (RESULTS_DIR / "difficulty_results.json").write_text(json.dumps(difficulty_results_data, indent=2))

    # 2. Context Delta Analysis
    context_delta_records = []
    for r in target_results_data["case_details"] + control_results_data["case_details"]:
        qid = r["case_id"]
        req_m = [m for m in request_metadata if m["case_id"] == qid][0]
        base_s = baseline_stats.get(qid, {})

        base_tbls = base_s.get("table_count", 0)
        base_cols = base_s.get("column_count", 0)
        base_toks = base_s.get("estimated_prompt_tokens", 0)

        ab_tbls = req_m["grounding_table_count"]
        ab_cols = req_m["grounding_column_count"]
        ab_toks = req_m["estimated_prompt_tokens"]

        context_delta_records.append({
            "case_id": qid,
            "cohort": "TARGET" if qid in [t["case_id"] for t in target_results_data["case_details"]] else "CONTROL",
            "mechanism": r.get("mechanism", "Control"),
            "difficulty": r["difficulty"],
            "db_id": r["db_id"],
            "outcome": r["outcome"],
            "baseline_tables": base_tbls,
            "ab_tables": ab_tbls,
            "delta_tables": ab_tbls - base_tbls,
            "baseline_columns": base_cols,
            "ab_columns": ab_cols,
            "delta_columns": ab_cols - base_cols,
            "baseline_tokens": base_toks,
            "ab_tokens": ab_toks,
            "delta_tokens": ab_toks - base_toks,
        })
    (RESULTS_DIR / "context_delta_analysis.json").write_text(json.dumps(context_delta_records, indent=2))

    # 3. Usage Summary
    tot_input_tokens = sum(r["input_tokens"] or 0 for r in call_ledger)
    tot_output_tokens = sum(r["output_tokens"] or 0 for r in call_ledger)
    tot_tokens = tot_input_tokens + tot_output_tokens
    usage_summary_data = {
        "planned_calls": 20,
        "attempted_calls": len(call_ledger),
        "successful_api_responses": sum(1 for r in call_ledger if r["status"] == "SUCCESS"),
        "api_errors": sum(1 for r in call_ledger if r["status"] == "API_ERROR"),
        "total_input_tokens": tot_input_tokens,
        "total_output_tokens": tot_output_tokens,
        "total_tokens": tot_tokens,
        "provider_reported_cost": "NOT_RETURNED_BY_ENDPOINT",
    }
    (RESULTS_DIR / "usage_summary.json").write_text(json.dumps(usage_summary_data, indent=2))

    # 4. Final Decision
    recovered_targets = target_results_data["recovered_cases"]
    regressed_controls = control_results_data["regressed_cases"]
    n_recovered = len(recovered_targets)
    n_regressed = len(regressed_controls)
    n_api_errors = sum(1 for r in call_ledger if r["status"] == "API_ERROR")

    # In our preregistered criteria:
    # Success: Target recoveries >= 5/15 (>=33.3%) AND Control regressions == 0/5
    # Failure: Target recoveries < 5/15 OR Control regressions > 0/5
    # Control regressions = 3/5 (> 0), which immediately violates the non-regression invariant!
    # Additionally, target recoveries = 4/15 (< 5).
    decision = "P8_E2_RESULT = FAIL"
    next_action = "STOP_PAID_EXPANSION\nRETURN_TO_P3_P4_DIAGNOSTICS"
    reasons = []
    if n_recovered < 5:
        reasons.append(f"Target recoveries ({n_recovered}/15, {round(n_recovered/15*100, 1)}%) < 5/15 required")
    if n_regressed > 0:
        reasons.append(f"Control regressions ({n_regressed}/5, 60.0%) > 0/5 required (bird_744, bird_1344, bird_168 regressed)")
    if n_api_errors > 0:
        reasons.append(f"{n_api_errors} target calls encountered provider API errors (bird_344, bird_416)")
    decision_reason = "; ".join(reasons)

    decision_data = {
        "experiment_decision": decision,
        "next_action": next_action,
        "decision_reason": decision_reason,
        "recovered_targets_count": n_recovered,
        "regressed_controls_count": n_regressed,
        "api_errors_count": n_api_errors,
        "success_threshold_met": False,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
    }
    (RESULTS_DIR / "experiment_decision.json").write_text(json.dumps(decision_data, indent=2))

    # 5. Summary Markdown
    manifest = json.loads((RESULTS_DIR / "manifest.json").read_text())
    summary_md = f"""# Phase P8-E2: Frozen 20-Call OSS-120B Causal Micro-Test Summary

## 1. Executive Status
- **Experiment Result**: `{decision}`
- **Next Action**: `{next_action}`
- **Decision Reason**: {decision_reason}
- **Model**: `{manifest['model']}` (temperature: 0.0)
- **Zero Rerun Invariant**: Dev100 rerun = NO, Final Holdout run = NO.

---

## 2. Headline Results

| Metric | Measured Result | Required Criterion | Pass? |
|---|---:|---:|:---:|
| **Target SQL Recoveries** | **{n_recovered} / 15** ({round(n_recovered/15*100, 1)}%) | $\\ge 5 / 15$ ($\\ge 33.3\\%) | **NO** |
| **Control SQL Regressions** | **{n_regressed} / 5** (60.0%) | Exactly $0 / 5$ | **NO (3 regressed)** |
| **API Errors / Dropped Requests** | **{n_api_errors}** | 0 | **NO (2 errors)** |

---

## 3. Preregistered Target Results (15 Targets)

| Case | Mechanism | Difficulty | DB | Historical | New A+B | Outcome |
|---|---|---|---|---:|---:|---|
"""
    for r in target_results_data["case_details"]:
        summary_md += f"| `{r['case_id']}` | {r['mechanism']} | {r['difficulty']} | {r['db_id']} | {r['historical_score']} | {'CORRECT' if r['execution_correct'] else 'WRONG'} | **{r['outcome']}** |\n"

    summary_md += """
---

## 4. Preregistered Control Results (5 Controls)

| Case | Difficulty | DB | Historical | New A+B | Regression? |
|---|---|---|---:|---:|---|
"""
    for r in control_results_data["case_details"]:
        summary_md += f"| `{r['case_id']}` | {r['difficulty']} | {r['db_id']} | {r['historical_score']} | {'CORRECT' if r['execution_correct'] else 'WRONG'} | **{'NO (Preserved)' if r['outcome'] == 'CONTROL_PRESERVED' else 'YES (Regressed)'}** |\n"

    summary_md += f"""
---

## 5. Mechanism Breakdown

| Mechanism | Total (N) | Recovered | Still Wrong | API Error | Recovery Rate |
|---|---:|---:|---:|---:|---:|
| **Relationship Expansion** | 6 | {mechanism_results_data.get('Relationship Expansion', {}).get('recovered', 0)} | 3 | 0 | {mechanism_results_data.get('Relationship Expansion', {}).get('recovery_rate', 0.0)}% |
| **Column Selection** | 8 | {mechanism_results_data.get('Column Selection', {}).get('recovered', 0)} | 5 | 2 | {mechanism_results_data.get('Column Selection', {}).get('recovery_rate', 0.0)}% |
| **Column Budget** | 1 | {mechanism_results_data.get('Column Budget', {}).get('recovered', 0)} | 1 | 0 | {mechanism_results_data.get('Column Budget', {}).get('recovery_rate', 0.0)}% |

---

## 6. Difficulty Breakdown (Targets)

| Difficulty | Total (N) | Recovered | Still Wrong / Err | Recovery Rate |
|---|---:|---:|---:|---:|
| **Simple** | {difficulty_results_data.get('simple', {}).get('total', 0)} | {difficulty_results_data.get('simple', {}).get('recovered', 0)} | {difficulty_results_data.get('simple', {}).get('total', 0) - difficulty_results_data.get('simple', {}).get('recovered', 0)} | {difficulty_results_data.get('simple', {}).get('recovery_rate', 0.0)}% |
| **Moderate** | {difficulty_results_data.get('moderate', {}).get('total', 0)} | {difficulty_results_data.get('moderate', {}).get('recovered', 0)} | {difficulty_results_data.get('moderate', {}).get('total', 0) - difficulty_results_data.get('moderate', {}).get('recovered', 0)} | {difficulty_results_data.get('moderate', {}).get('recovery_rate', 0.0)}% |
| **Challenging** | {difficulty_results_data.get('challenging', {}).get('total', 0)} | {difficulty_results_data.get('challenging', {}).get('recovered', 0)} | {difficulty_results_data.get('challenging', {}).get('total', 0) - difficulty_results_data.get('challenging', {}).get('recovered', 0)} | {difficulty_results_data.get('challenging', {}).get('recovery_rate', 0.0)}% |

---

## 7. Token & Cost Usage
- **Planned Calls**: 20
- **Attempted Calls**: {len(call_ledger)}
- **Successful API Responses**: {usage_summary_data['successful_api_responses']}
- **API Errors**: {n_api_errors}
- **Total Input Tokens**: {tot_input_tokens:,}
- **Total Output Tokens**: {tot_output_tokens:,}
- **Total Tokens**: {tot_tokens:,}
- **Provider Reported Cost**: {usage_summary_data['provider_reported_cost']}
"""
    (RESULTS_DIR / "summary.md").write_text(summary_md)

    print("All artifacts successfully finalized.")
    print(f"Decision: {decision}")
    print(f"Recoveries: {n_recovered}/15, Regressions: {n_regressed}/5, API Errors: {n_api_errors}")

if __name__ == "__main__":
    main()
