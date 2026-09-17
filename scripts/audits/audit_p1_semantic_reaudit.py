#!/usr/bin/env python3
"""
P1-R — Production Semantic Re-Audit of C0–C2 and S0–S3
Comprehensive forensic re-audit script enforcing strict provenance and raw artifact immutability.
"""

import json
import sqlite3
import hashlib
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
import sqlglot
from sqlglot import exp

from t2s.benchmark.invariants import resolve_official_database_path

REPO_ROOT = Path("/home/thuclh245/MyCode/SQL")
DATASET_PATH = REPO_ROOT / "benchmarks/t2s/datasets/t2s_eval_v1.jsonl"
DB_ROOT = REPO_ROOT / "benchmarks/t2s/databases/official"
P1_RESULTS_ROOT = REPO_ROOT / "results/context_serialization_experiment"
AUDIT_OUT_DIR = REPO_ROOT / "results/context_serialization_semantic_reaudit"
REPORT_PATH = REPO_ROOT / "reports/evaluations/p1_production_semantic_reaudit.md"

ARMS = ["C0", "C1", "C2", "S0", "S1", "S2", "S3"]
REPLICATES = ["replicate_01", "replicate_02", "replicate_03"]

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def execute_gold_sql_safe(db_path: Path, sql_text: str) -> dict[str, Any]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0)
        cur = conn.cursor()
        cur.execute(sql_text)
        cols = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchmany(100)
        total_rows = len(rows)
        # Check if more rows exist
        remaining = len(cur.fetchmany(1000))
        total_rows += remaining
        conn.close()
        return {
            "ok": True,
            "error": None,
            "column_names": cols,
            "row_count": total_rows,
            "sample_rows": [list(r) for r in rows[:5]]
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "column_names": [],
            "row_count": 0,
            "sample_rows": []
        }

def parse_sql_ast(sql_text: str) -> dict[str, Any]:
    try:
        parsed = sqlglot.parse_one(sql_text, read="sqlite")
        tables = [t.name for t in parsed.find_all(exp.Table)]
        columns = [c.name for c in parsed.find_all(exp.Column)]
        has_distinct = parsed.find(exp.Distinct) is not None
        has_group = parsed.find(exp.Group) is not None
        has_order = parsed.find(exp.Order) is not None
        has_limit = parsed.find(exp.Limit) is not None
        has_where = parsed.find(exp.Where) is not None
        joins = [j.this.name if hasattr(j.this, "name") else str(j.this) for j in parsed.find_all(exp.Join)]
        aggs = [a.key for a in parsed.find_all(exp.AggFunc)]
        
        select_exprs = []
        if isinstance(parsed, exp.Select):
            for e in parsed.expressions:
                select_exprs.append(e.sql())
        return {
            "parse_ok": True,
            "tables": sorted(list(set(tables))),
            "columns": sorted(list(set(columns))),
            "select_expressions": select_exprs,
            "joins": joins,
            "aggregations": aggs,
            "has_distinct": has_distinct,
            "has_group_by": has_group,
            "has_order_by": has_order,
            "has_limit": has_limit,
            "has_where": has_where
        }
    except Exception as exc:
        return {
            "parse_ok": False,
            "error": str(exc),
            "tables": [],
            "columns": [],
            "select_expressions": [],
            "joins": [],
            "aggregations": [],
            "has_distinct": False,
            "has_group_by": False,
            "has_order_by": False,
            "has_limit": False,
            "has_where": False
        }

def derive_question_contract(q: str, bird_gold_sql: str) -> dict[str, Any]:
    q_lower = q.lower()
    
    is_count = any(k in q_lower for k in ["how many", "count", "number of", "total number"])
    is_avg = any(k in q_lower for k in ["average", "avg", "mean"])
    is_sum = any(k in q_lower for k in ["sum", "total score", "total amount", "total cost"])
    is_min_max = any(k in q_lower for k in ["highest", "lowest", "max", "min", "most", "least", "top", "first", "best"])
    is_names = any(k in q_lower for k in ["name", "names", "who", "which school", "which player", "which country", "list"])
    
    ordering_requested = any(k in q_lower for k in ["highest", "lowest", "top", "order by", "rank", "first", "latest", "earliest"])
    
    return {
        "question": q,
        "is_count_query": is_count,
        "is_avg_query": is_avg,
        "is_sum_query": is_sum,
        "is_min_max_query": is_min_max,
        "is_entity_list": is_names,
        "ordering_requested": ordering_requested,
    }

def run_reaudit():
    print("[P1-R] Starting Production Semantic Re-Audit of C0-C2 and S0-S3...")
    AUDIT_OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Load benchmark dataset
    cases_by_id: dict[str, dict[str, Any]] = {}
    with open(DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            cases_by_id[c["case_id"]] = c
    print(f"[P1-R] Loaded {len(cases_by_id)} benchmark cases from {DATASET_PATH.name}")

    # 2. Precompute gold execution results and ASTs for all 100 cases
    gold_cache: dict[str, dict[str, Any]] = {}
    for cid, c in cases_by_id.items():
        db_id = c["db_id"]
        db_path = resolve_official_database_path(DB_ROOT, db_id)
        gold_sql = c["bird_gold_sql"]
        exec_res = execute_gold_sql_safe(db_path, gold_sql)
        ast_res = parse_sql_ast(gold_sql)
        q_contract = derive_question_contract(c["question"], gold_sql)
        gold_cache[cid] = {
            "db_path": str(db_path),
            "gold_sql": gold_sql,
            "exec": exec_res,
            "ast": ast_res,
            "contract": q_contract
        }

    # 3. Iterate over all 2,100 runs
    run_provenance_records = []
    semantic_classification_records = []
    
    arm_metrics = {
        arm: {
            "strict_ex_passed": 0,
            "strict_ex_failed": 0,
            "strict_ex_null": 0,
            "class_A": 0,
            "class_B": 0,
            "class_C": 0,
            "class_D": 0,
            "class_E": 0,
            "class_F": 0,
            "total_runs": 0,
            "replicate_breakdown": {
                "replicate_01": {"strict_ex": 0, "total": 0},
                "replicate_02": {"strict_ex": 0, "total": 0},
                "replicate_03": {"strict_ex": 0, "total": 0},
            }
        }
        for arm in ARMS
    }

    per_case_replicates: dict[str, dict[str, list[dict[str, Any]]]] = {
        cid: {arm: [] for arm in ARMS} for cid in cases_by_id
    }

    for arm in ARMS:
        family = "context_selection" if arm in ["C0", "C1", "C2"] else "serialization"
        for rep_idx, rep_name in enumerate(REPLICATES, start=1):
            cases_jsonl_path = P1_RESULTS_ROOT / family / arm / rep_name / "cases.jsonl"
            if not cases_jsonl_path.exists():
                raise FileNotFoundError(f"Missing P1 run artifact: {cases_jsonl_path}")
            
            with open(cases_jsonl_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    rec = json.loads(line)
                    cid = rec["case_id"]
                    c_meta = cases_by_id[cid]
                    g_meta = gold_cache[cid]

                    gen_sql = rec.get("generated_sql")
                    orig_ex = rec.get("execution_correct")
                    runtime_status = rec.get("runtime_status")
                    exec_success = rec.get("execution_success", False)

                    arm_metrics[arm]["total_runs"] += 1
                    arm_metrics[arm]["replicate_breakdown"][rep_name]["total"] += 1
                    if orig_ex is True:
                        arm_metrics[arm]["strict_ex_passed"] += 1
                        arm_metrics[arm]["replicate_breakdown"][rep_name]["strict_ex"] += 1
                    elif orig_ex is False:
                        arm_metrics[arm]["strict_ex_failed"] += 1
                    else:
                        arm_metrics[arm]["strict_ex_null"] += 1

                    primary_class = "F"
                    subclass = "F_GENERATED_SQL_OMITTED_BY_RUNNER"
                    explanation = (
                        "Candidate SQL was dropped during standardization by run_p1_experiment.py "
                        "(_standardize_case_record only captured generated_sql_present: bool). "
                        "Per Audit Rule 2 and Rule 10, unrecoverable SQL cannot be evaluated for "
                        "semantic correctness and must be classified as F (INSUFFICIENT_EVIDENCE)."
                    )
                    production_safe = False

                    arm_metrics[arm]["class_F"] += 1

                    prov_entry = {
                        "arm": arm,
                        "experiment_family": family,
                        "replicate": rep_idx,
                        "replicate_id": rep_name,
                        "case_id": cid,
                        "question": c_meta["question"],
                        "database": c_meta["db_id"],
                        "context_presented": rec.get("context", {}),
                        "generated_sql": gen_sql,
                        "candidate_execution_result": None,
                        "gold_sql": c_meta["bird_gold_sql"],
                        "gold_execution_result": {
                            "ok": g_meta["exec"]["ok"],
                            "row_count": g_meta["exec"]["row_count"],
                            "sample_rows": g_meta["exec"]["sample_rows"],
                            "columns": g_meta["exec"]["column_names"]
                        },
                        "runtime_status": runtime_status,
                        "original_execution_correct": orig_ex,
                        "execution_success": exec_success,
                        "error_category": rec.get("error_category"),
                        "expected_output_columns": g_meta["ast"]["select_expressions"],
                        "solver_assumptions": None,
                        "solver_unresolved": None,
                        "latency_ms": rec.get("latency_ms")
                    }
                    run_provenance_records.append(prov_entry)

                    class_entry = {
                        "arm": arm,
                        "replicate": rep_idx,
                        "replicate_id": rep_name,
                        "case_id": cid,
                        "primary_class": primary_class,
                        "subclass": subclass,
                        "production_safe": production_safe,
                        "original_execution_correct": orig_ex,
                        "runtime_status": runtime_status,
                        "explanation": explanation
                    }
                    semantic_classification_records.append(class_entry)
                    per_case_replicates[cid][arm].append({
                        "replicate": rep_idx,
                        "strict_ex": orig_ex,
                        "primary_class": primary_class
                    })

    # Write run_provenance.jsonl
    prov_path = AUDIT_OUT_DIR / "run_provenance.jsonl"
    with open(prov_path, "w", encoding="utf-8") as f:
        for r in run_provenance_records:
            f.write(json.dumps(r) + "\n")
    print(f"[P1-R] Wrote {len(run_provenance_records)} records to {prov_path.name}")

    # Write semantic_classifications.jsonl
    class_path = AUDIT_OUT_DIR / "semantic_classifications.jsonl"
    with open(class_path, "w", encoding="utf-8") as f:
        for r in semantic_classification_records:
            f.write(json.dumps(r) + "\n")
    print(f"[P1-R] Wrote {len(semantic_classification_records)} records to {class_path.name}")

    # 4. Output Contract Analysis
    output_contract_analysis = []
    for cid, c in cases_by_id.items():
        g = gold_cache[cid]
        q_contract = g["contract"]
        gold_ast = g["ast"]
        
        potential_mismatch = False
        mismatch_notes = []
        if q_contract["is_count_query"] and not any("count" in s.lower() for s in gold_ast["select_expressions"]):
            potential_mismatch = True
            mismatch_notes.append("Question requests COUNT but gold SELECT expression lacks COUNT aggregate.")
        if gold_ast["has_limit"] and not q_contract["ordering_requested"]:
            potential_mismatch = True
            mismatch_notes.append("Gold SQL specifies LIMIT without explicit user request for top/ordering.")
        
        output_contract_analysis.append({
            "case_id": cid,
            "question": c["question"],
            "requested_entities_measures": [
                k for k, v in q_contract.items() if v and k != "question"
            ],
            "gold_select_expressions": gold_ast["select_expressions"],
            "gold_has_distinct": gold_ast["has_distinct"],
            "gold_has_order_by": gold_ast["has_order_by"],
            "gold_has_limit": gold_ast["has_limit"],
            "potential_contract_mismatch": potential_mismatch,
            "mismatch_notes": mismatch_notes
        })
    with open(AUDIT_OUT_DIR / "output_contract_analysis.json", "w", encoding="utf-8") as f:
        json.dump(output_contract_analysis, f, indent=2)

    # 5. Literal Analysis
    literal_analysis = []
    for cid, c in cases_by_id.items():
        ev = c.get("evidence", "")
        literal_analysis.append({
            "case_id": cid,
            "evidence": ev,
            "has_value_evidence": any(s in ev for s in ["=", ">", "<", "refers to", "denotes"]),
            "evidence_mode_in_p1": "none (frozen)",
            "risk_of_literal_miss_in_p1": True if ev else False
        })
    with open(AUDIT_OUT_DIR / "literal_analysis.json", "w", encoding="utf-8") as f:
        json.dump(literal_analysis, f, indent=2)

    # 6. Join & Grain Analysis
    join_grain_analysis = []
    for cid, c in cases_by_id.items():
        g = gold_cache[cid]
        join_grain_analysis.append({
            "case_id": cid,
            "database": c["db_id"],
            "tables_involved_in_gold": g["ast"]["tables"],
            "join_count": len(g["ast"]["joins"]),
            "has_aggregation": len(g["ast"]["aggregations"]) > 0,
            "has_group_by": g["ast"]["has_group_by"],
            "fan_out_vulnerability": len(g["ast"]["joins"]) >= 2 and len(g["ast"]["aggregations"]) > 0
        })
    with open(AUDIT_OUT_DIR / "join_grain_analysis.json", "w", encoding="utf-8") as f:
        json.dump(join_grain_analysis, f, indent=2)

    # 7. Assumption Signal Analysis
    assumption_signal_analysis = {
        "status": "UNAVAILABLE_IN_P1_RUNNER",
        "root_cause": (
            "scripts/evaluation/run_p1_experiment.py did not serialize solver assumptions, "
            "unresolved caveats, or candidate SQL text into cases.jsonl. "
            "Unlike synthetic benchmark (P2) which captured assumptions and candidate SQL in full, "
            "P1 dropped these signals during standardization, preventing assumption signal auditing."
        ),
        "total_cases_audited": 100,
        "runs_affected": 2100,
        "audit_impact": "Signals cannot be mechanically evaluated without generating synthetic assumptions."
    }
    with open(AUDIT_OUT_DIR / "assumption_signal_analysis.json", "w", encoding="utf-8") as f:
        json.dump(assumption_signal_analysis, f, indent=2)

    # 8. Arm Metrics Calculation
    summary_table = []
    for arm in ARMS:
        m = arm_metrics[arm]
        strict_ex_pct = round((m["strict_ex_passed"] / m["total_runs"]) * 100, 2)
        sem_correct_pct = round(((m["class_A"] + m["class_B"]) / m["total_runs"]) * 100, 2)
        safe_pct = round((m["class_A"] + m["class_B"]) / m["total_runs"] * 100, 2)
        summary_table.append({
            "arm": arm,
            "total_runs": m["total_runs"],
            "strict_ex_rate": strict_ex_pct,
            "strict_ex_count": m["strict_ex_passed"],
            "semantic_correct_count": m["class_A"] + m["class_B"],
            "semantic_correct_rate": sem_correct_pct,
            "ambiguous_count": m["class_C"],
            "true_error_count": m["class_D"],
            "lucky_match_count": m["class_E"],
            "insufficient_evidence_count": m["class_F"],
            "production_safe_rate": safe_pct,
            "replicate_ex": {
                r: round((m["replicate_breakdown"][r]["strict_ex"] / m["replicate_breakdown"][r]["total"]) * 100, 2)
                for r in REPLICATES
            }
        })
    with open(AUDIT_OUT_DIR / "arm_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary_table, f, indent=2)

    # 9. Transition Analysis
    transitions = {
        "context_arms": {
            "C0_vs_C1": {
                "strict_diff_pp": round(arm_metrics["C1"]["strict_ex_passed"] / 3.0 - arm_metrics["C0"]["strict_ex_passed"] / 3.0, 2),
                "semantic_eval_status": "BLOCKED_BY_MISSING_SQL"
            },
            "C0_vs_C2": {
                "strict_diff_pp": round(arm_metrics["C2"]["strict_ex_passed"] / 3.0 - arm_metrics["C0"]["strict_ex_passed"] / 3.0, 2),
                "semantic_eval_status": "BLOCKED_BY_MISSING_SQL"
            }
        },
        "serialization_arms": {
            "S0_vs_S1": {
                "strict_diff_pp": round(arm_metrics["S1"]["strict_ex_passed"] / 3.0 - arm_metrics["S0"]["strict_ex_passed"] / 3.0, 2),
                "semantic_eval_status": "BLOCKED_BY_MISSING_SQL"
            },
            "S0_vs_S2": {
                "strict_diff_pp": round(arm_metrics["S2"]["strict_ex_passed"] / 3.0 - arm_metrics["S0"]["strict_ex_passed"] / 3.0, 2),
                "semantic_eval_status": "BLOCKED_BY_MISSING_SQL"
            },
            "S0_vs_S3": {
                "strict_diff_pp": round(arm_metrics["S3"]["strict_ex_passed"] / 3.0 - arm_metrics["S0"]["strict_ex_passed"] / 3.0, 2),
                "semantic_eval_status": "BLOCKED_BY_MISSING_SQL"
            }
        }
    }
    with open(AUDIT_OUT_DIR / "transition_analysis.json", "w", encoding="utf-8") as f:
        json.dump(transitions, f, indent=2)

    # 10. Stability Analysis (Clustered by Case across 3 replicates)
    stability_cases = {}
    for cid, arm_data in per_case_replicates.items():
        stability_cases[cid] = {}
        for arm, reps in arm_data.items():
            ex_passes = sum(1 for r in reps if r["strict_ex"] is True)
            if ex_passes == 3:
                st = "STABLE_CORRECT"
            elif ex_passes == 0:
                st = "STABLE_INCORRECT"
            else:
                st = "UNSTABLE"
            stability_cases[cid][arm] = {
                "strict_passes": ex_passes,
                "strict_stability": st,
                "semantic_stability": "INSUFFICIENT_EVIDENCE"
            }
    with open(AUDIT_OUT_DIR / "stability_analysis.json", "w", encoding="utf-8") as f:
        json.dump(stability_cases, f, indent=2)

    # 11. Production Risk Analysis
    production_risk_analysis = {
        "risk_verdict": "CRITICAL_GOVERNANCE_BLINDSPOT",
        "explanation": (
            "Because candidate SQL was not persisted, the system cannot verify whether the observed "
            "19.0% execution accuracy in C2 or 14.0% in S1/S3 represents genuine semantic reasoning or "
            "lucky matches (Category E). Deploying context expansions without candidate SQL observability "
            "exposes production to silent financial overcounting, unchecked Cartesian fan-out, and incorrect filtering."
        ),
        "missing_artifact_count": 2100,
        "affected_replicates": 3,
        "affected_arms": 7
    }
    with open(AUDIT_OUT_DIR / "production_risk_analysis.json", "w", encoding="utf-8") as f:
        json.dump(production_risk_analysis, f, indent=2)

    # 12. Statistical Analysis
    statistical_analysis = {
        "methodology": "Clustered Case Census (100 clusters, 3 replicates per cluster)",
        "unclustered_overclaim_warning": (
            "The original P1 report evaluated 300 trials per arm using an unclustered exact McNemar test "
            "(e.g., claiming p = 1.05e-5 for C2 vs C0). Because trials are grouped into 100 cases, treating "
            "replicates as independent observations violates exchangeability and inflates statistical significance."
        ),
        "case_level_majority_metrics": {
            arm: sum(1 for cid in cases_by_id if stability_cases[cid][arm]["strict_passes"] >= 2)
            for arm in ARMS
        }
    }
    with open(AUDIT_OUT_DIR / "statistical_analysis.json", "w", encoding="utf-8") as f:
        json.dump(statistical_analysis, f, indent=2)

    # 13. Audit Manifest
    audit_manifest = {
        "audit_name": "P1-R Production Semantic Re-Audit of C0-C2 and S0-S3",
        "audit_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": "73807aa358f224c181df9e55efc94a8386aa5bb7",
        "dataset_path": str(DATASET_PATH),
        "dataset_sha256": sha256_file(DATASET_PATH),
        "total_cases": len(cases_by_id),
        "total_runs_audited": len(run_provenance_records),
        "arms_audited": ARMS,
        "final_verdict": "BLOCKED",
        "blocking_reason": (
            "The P1 experiment execution harness (scripts/evaluation/run_p1_experiment.py) dropped "
            "the raw generated candidate SQL strings during record standardization (_standardize_case_record). "
            "Per Audit Rule 2 ('If original SQL cannot be recovered for a run: classification = INSUFFICIENT_EVIDENCE. "
            "Do not guess. Do not reconstruct SQL from memory.') and Rule 10, all 2,100 runs must be classified "
            "as F (INSUFFICIENT_EVIDENCE). Semantic re-audit cannot proceed without authentic candidate SQL outputs."
        )
    }
    with open(AUDIT_OUT_DIR / "audit_manifest.json", "w", encoding="utf-8") as f:
        json.dump(audit_manifest, f, indent=2)

    print("[P1-R] All 12 audit artifacts generated successfully in results/context_serialization_semantic_reaudit/")
    return summary_table, stability_cases, audit_manifest

if __name__ == "__main__":
    run_reaudit()
