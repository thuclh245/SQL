# ruff: noqa: E501
"""Build P8-E6 deterministic P4 validator hardening artifacts.

Zero API phase. Runtime validator inputs exclude gold SQL/results/labels; gold and
forensic labels are used only by this offline evaluator.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlglot
from pydantic import ValidationError
from sqlglot import exp

from t2s.verification.p4_validator import (
    P4DeterministicValidator,
    P4ValidationInput,
    P4ValidatorFamily,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "results" / "p8e6_p4_validators"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e6_p4_validators.md"
P8E4 = PROJECT_ROOT / "results" / "p8e4_residual_bottleneck"
P8E5 = PROJECT_ROOT / "results" / "p8e5_p4_reasoning"
P8C = PROJECT_ROOT / "results" / "p8c_verifier_backend_validation"
FORENSICS = PROJECT_ROOT / "results" / "oss120b_failure_forensics"
DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"

FAMILY_BY_CAUSE = {
    "FILTER_LOGIC": "Filter",
    "AGGREGATION_AND_GRAIN": "Aggregation/Grain",
    "PROJECTION": "Projection",
    "JOIN_PATH_SELECTION": "Join Path",
    "VALUE_LITERAL_MAPPING": "Value",
}

P4_FAMILIES = {"FILTER_LOGIC", "AGGREGATION_AND_GRAIN", "PROJECTION", "JOIN_PATH_SELECTION"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def parse_one(sql: str | None) -> exp.Expression | None:
    if not sql:
        return None
    try:
        return sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None


def select_sqls(parsed: exp.Expression | None) -> list[str]:
    if parsed is None:
        return []
    select = parsed.find(exp.Select)
    if select is None:
        return []
    return [item.sql(dialect="sqlite") for item in select.expressions]


def where_sql(parsed: exp.Expression | None) -> str | None:
    if parsed is None:
        return None
    where = parsed.find(exp.Where)
    return where.this.sql(dialect="sqlite") if where else None


def expression_sqls(parsed: exp.Expression | None, klass: type[exp.Expression]) -> list[str]:
    if parsed is None:
        return []
    return sorted({node.sql(dialect="sqlite") for node in parsed.find_all(klass)})


def value_exists(db_id: str, table: str, column: str, value: str) -> bool | None:
    db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5) as conn:
            conn.execute("PRAGMA query_only = ON")
            qtable = '"' + table.replace('"', '""') + '"'
            qcol = '"' + column.replace('"', '""') + '"'
            row = conn.execute(
                f"SELECT 1 FROM {qtable} WHERE {qcol} = ? LIMIT 1",
                (value,),
            ).fetchone()
            return row is not None
    except Exception:
        return None


def equality_literal_columns(sql: str | None) -> list[tuple[str | None, str, str]]:
    parsed = parse_one(sql)
    if parsed is None:
        return []
    pairs = []
    for node in parsed.find_all(exp.EQ, exp.Like):
        cols = list(node.find_all(exp.Column))
        lits = [lit for lit in node.find_all(exp.Literal) if isinstance(lit.this, str)]
        if len(cols) == 1 and len(lits) == 1:
            pairs.append((cols[0].table or None, cols[0].name, str(lits[0].this)))
    return pairs


def p8e5_prototype_flags(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Exact P8-E5 prototype reproduction logic."""
    sql = row.get("candidate_sql")
    question = row.get("question", "").lower()
    db_id = row.get("db_id")
    parsed = parse_one(sql)
    if parsed is None:
        return [{"check": "sql_parse", "action": "REGENERATE", "severity": "high"}]
    flags: list[dict[str, Any]] = []
    if re.search(r":[A-Za-z_][A-Za-z0-9_]*", sql or ""):
        flags.append({"check": "unbound_sql_parameter", "action": "REGENERATE", "severity": "high"})
    projection = select_sqls(parsed)
    if len(projection) > 1 and re.search(r"\b(which|what is|what was|who is)\b", question):
        if any(re.search(r"\b(sum|avg|count|min|max|/|\*)\b", item.lower()) for item in projection):
            flags.append({"check": "extra_projected_measure_for_entity_question", "action": "BLOCK_WRONG_SQL", "severity": "medium"})
    filter_text = where_sql(parsed) or ""
    if (" is not null" in filter_text.lower() or "nullif" in (sql or "").lower()) and "null" not in question:
        flags.append({"check": "unrequested_null_or_denominator_guard", "action": "ESCALATE", "severity": "low"})
    has_group = bool(expression_sqls(parsed, exp.Group))
    if has_group and not re.search(r"\b(each|per|by|for each|group)\b", question):
        flags.append({"check": "group_by_without_grouping_language", "action": "ESCALATE", "severity": "medium"})
    if parsed.find(exp.Subquery) and parsed.find(exp.Min, exp.Max) and not re.search(r"\b(min|max|highest|lowest|oldest|youngest|average|most|least|shortest|fastest)\b", question):
        flags.append({"check": "unrequested_superlative_subquery", "action": "ESCALATE", "severity": "medium"})
    for table, column, value in equality_literal_columns(sql):
        if table and len(value) <= 80 and not value.isdigit():
            exists = value_exists(db_id, table, column, value)
            if exists is False:
                flags.append({"check": "literal_absent_from_column_domain", "action": "REQUEST_VALUE_GROUNDING", "severity": "medium", "table": table, "column": column, "value": value})
    return flags


def confusion(tp: int, fp: int, tn: int, fn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "false_positive_rate": round(fpr, 4),
    }


def case_metric(case_ids: set[str], flagged: set[str], controls: set[str], control_flagged: set[str]) -> dict[str, Any]:
    tp_cases = sorted(case_ids & flagged)
    fn_cases = sorted(case_ids - flagged)
    fp_cases = sorted(controls & control_flagged)
    tn_cases = sorted(controls - control_flagged)
    data = confusion(len(tp_cases), len(fp_cases), len(tn_cases), len(fn_cases))
    data.update({"tp_cases": tp_cases, "fp_cases": fp_cases, "tn_cases": tn_cases, "fn_cases": fn_cases})
    return data


def p4_input(row: dict[str, Any], frozen_by_candidate: dict[str, dict[str, Any]]) -> P4ValidationInput:
    frozen = frozen_by_candidate.get(row["candidate_id"], {})
    return P4ValidationInput(
        candidate_id=row["candidate_id"],
        question=row["question"],
        candidate_sql=row["candidate_sql"],
        dialect="sqlite",
        grounding_context=frozen.get("authorized_schema", ""),
        authorized_schema=frozen.get("authorized_schema", ""),
        authorized_tables=frozen.get("grounded_tables", []),
    )


def stable_hash(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    residual_trials = load_jsonl(P8E4 / "residual_trial_taxonomy.jsonl")
    residual_questions = load_jsonl(P8E4 / "residual_question_taxonomy.jsonl")
    forensics = load_jsonl(FORENSICS / "case_forensics.jsonl")
    frozen_candidates = load_jsonl(P8C / "frozen_candidates.jsonl")
    p8e5_recorded = load_json(P8E5 / "prototype_results.json")
    frozen_by_candidate = {row["candidate_id"]: row for row in frozen_candidates}

    residual_case_ids = {row["case_id"] for row in residual_questions}
    positive_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in residual_trials:
        positive_by_case[row["case_id"]].append(row)

    correct_rows = [
        row for row in forensics
        if row.get("true_semantic_correctness") and row.get("evidence_sufficiency") == "SUFFICIENT"
    ]
    control_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in correct_rows:
        control_by_case[row["case_id"]].append(row)
    control_case_ids = set(control_by_case)

    baseline_positive_flags = {
        cid: [flag for row in rows for flag in p8e5_prototype_flags(row)]
        for cid, rows in positive_by_case.items()
    }
    baseline_control_flags = {
        cid: [flag for row in rows for flag in p8e5_prototype_flags(row)]
        for cid, rows in control_by_case.items()
    }
    baseline = case_metric(
        residual_case_ids,
        {cid for cid, flags in baseline_positive_flags.items() if flags},
        control_case_ids,
        {cid for cid, flags in baseline_control_flags.items() if flags},
    )
    baseline.update(
        {
            "reproduced_recorded_p8e5": {
                "TP": baseline["TP"] == p8e5_recorded["true_positives"],
                "FP": baseline["FP"] == p8e5_recorded["false_positives"],
                "TN": baseline["TN"] == p8e5_recorded["true_negatives"],
                "FN": baseline["FN"] == p8e5_recorded["false_negatives"],
            },
            "recorded_source": "results/p8e5_p4_reasoning/prototype_results.json",
        }
    )
    write_json(OUT_DIR / "baseline_reproduction.json", baseline)
    if not all(baseline["reproduced_recorded_p8e5"].values()):
        raise SystemExit("P8-E5 baseline reproduction failed; stopping per P8-E6 protocol.")

    validator = P4DeterministicValidator()
    all_rows = residual_trials + correct_rows
    row_results: list[dict[str, Any]] = []
    for row in all_rows:
        result = validator.validate(p4_input(row, frozen_by_candidate))
        row_results.append(
            {
                "candidate_id": row["candidate_id"],
                "case_id": row["case_id"],
                "db_id": row["db_id"],
                "difficulty": row.get("difficulty"),
                "question": row["question"],
                "candidate_sql": row["candidate_sql"],
                "is_positive": row["case_id"] in residual_case_ids,
                "true_semantic_correctness": row.get("true_semantic_correctness", False),
                "result": result.model_dump(mode="json"),
                "violation_codes": [v.code for v in result.violations],
                "validator_families": sorted({v.validator.value for v in result.violations}),
                "is_high_risk": result.is_high_risk,
            }
        )

    flagged_positive = {row["case_id"] for row in row_results if row["is_positive"] and row["is_high_risk"]}
    flagged_control = {row["case_id"] for row in row_results if not row["is_positive"] and row["is_high_risk"]}
    hardened = case_metric(residual_case_ids, flagged_positive, control_case_ids, flagged_control)

    combined_rows = [row for row in row_results if row["is_positive"] or row["case_id"] in control_case_ids]
    write_jsonl(OUT_DIR / "combined_validator_results.jsonl", combined_rows)
    write_json(OUT_DIR / "confusion_matrix.json", {"p8e5_prototype": baseline, "p8e6_hardened": hardened})

    family_files = {
        P4ValidatorFamily.FILTER_CONTRACT: "filter_validator_results.jsonl",
        P4ValidatorFamily.AGGREGATION_GRAIN: "aggregation_validator_results.jsonl",
        P4ValidatorFamily.PROJECTION_SHAPE: "projection_validator_results.jsonl",
        P4ValidatorFamily.JOIN_PATH_RISK: "join_validator_results.jsonl",
        P4ValidatorFamily.SQL_CONSTRUCTION_SANITY: "construction_validator_results.jsonl",
    }
    family_metrics = []
    for family, filename in family_files.items():
        fam_results = []
        for row in all_rows:
            result = validator.validate(p4_input(row, frozen_by_candidate), families={family})
            fam_results.append(
                {
                    "candidate_id": row["candidate_id"],
                    "case_id": row["case_id"],
                    "db_id": row["db_id"],
                    "is_positive": row["case_id"] in residual_case_ids,
                    "result": result.model_dump(mode="json"),
                    "is_high_risk": result.is_high_risk,
                    "violation_codes": [v.code for v in result.violations],
                }
            )
        write_jsonl(OUT_DIR / filename, fam_results)
        family_positive_causes = {
            P4ValidatorFamily.FILTER_CONTRACT: {"FILTER_LOGIC"},
            P4ValidatorFamily.AGGREGATION_GRAIN: {"AGGREGATION_AND_GRAIN"},
            P4ValidatorFamily.PROJECTION_SHAPE: {"PROJECTION"},
            P4ValidatorFamily.JOIN_PATH_RISK: {"JOIN_PATH_SELECTION"},
            P4ValidatorFamily.SQL_CONSTRUCTION_SANITY: set(),
        }[family]
        family_case_ids = {
            row["case_id"]
            for row in residual_questions
            if row["question_level_cause"] in family_positive_causes
        }
        family_flagged = {row["case_id"] for row in fam_results if row["is_positive"] and row["is_high_risk"]}
        family_fp = {row["case_id"] for row in fam_results if not row["is_positive"] and row["is_high_risk"]}
        tp = len(family_case_ids & family_flagged)
        fp = len(family_fp)
        family_metrics.append(
            {
                "validator": family.value,
                "positive_questions": len(family_case_ids),
                "detected": tp,
                "false_positives": fp,
                "recall": round(tp / len(family_case_ids), 4) if family_case_ids else 0.0,
                "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
                "tp_cases": sorted(family_case_ids & family_flagged),
                "fp_cases": sorted(family_fp),
            }
        )
    write_json(OUT_DIR / "family_metrics.json", {"rows": family_metrics})

    false_positive_rows = []
    for cid in hardened["fp_cases"]:
        examples = [row for row in row_results if row["case_id"] == cid and row["is_high_risk"]]
        for item in examples[:1]:
            false_positive_rows.append(
                {
                    "case": cid,
                    "question": item["question"],
                    "candidate_sql": item["candidate_sql"],
                    "validator_code": item["violation_codes"],
                    "why_validator_fired": item["result"]["violations"],
                    "why_sql_was_correct": "Frozen forensics label true_semantic_correctness=True and evidence_sufficiency=SUFFICIENT.",
                    "fix": "Keep rule disabled/downgraded for matching surface unless additional contract evidence exists.",
                }
            )
    write_jsonl(OUT_DIR / "false_positive_audit.jsonl", false_positive_rows)

    false_negative_rows = []
    for cid in hardened["fn_cases"]:
        qrow = next(row for row in residual_questions if row["case_id"] == cid)
        false_negative_rows.append(
            {
                "case": cid,
                "failure_family": qrow["question_level_cause"],
                "why_validator_missed": "No high-confidence deterministic contract violation was extracted from question+candidate SQL without gold SQL or DB probes.",
                "runtime_signal_missing": "minimal semantic contract fields and/or value-grounding metadata",
                "candidate_next_step": "LIGHTWEIGHT_PLAN_IR_SHOULD_BE_NEXT" if qrow["question_level_cause"] in P4_FAMILIES else "REQUEST_VALUE_GROUNDING",
            }
        )
    write_jsonl(OUT_DIR / "false_negative_audit.jsonl", false_negative_rows)

    difficulty_rows = []
    for difficulty in sorted({row["difficulty"] for row in residual_questions}):
        ids = {row["case_id"] for row in residual_questions if row["difficulty"] == difficulty}
        detected = ids & flagged_positive
        difficulty_rows.append({"difficulty": difficulty, "positive_questions": len(ids), "detected": len(detected), "recall": round(len(detected) / len(ids), 4)})
    write_json(OUT_DIR / "difficulty_metrics.json", {"rows": difficulty_rows})

    db_rows = []
    for db_id in sorted({row["db_id"] for row in residual_questions} | {row["db_id"] for row in correct_rows}):
        positive_ids = {row["case_id"] for row in residual_questions if row["db_id"] == db_id}
        control_ids = {row["case_id"] for row in correct_rows if row["db_id"] == db_id}
        db_rows.append(
            {
                "db_id": db_id,
                "positive_questions": len(positive_ids),
                "detected_correctly": len(positive_ids & flagged_positive),
                "control_questions": len(control_ids),
                "false_positive_controls": len(control_ids & flagged_control),
                "rule_codes_triggered": sorted({code for row in row_results if row["db_id"] == db_id for code in row["violation_codes"]}),
            }
        )
    write_json(OUT_DIR / "database_metrics.json", {"rows": db_rows})

    leave_one_out = []
    for cid in sorted(residual_case_ids | control_case_ids):
        pos = residual_case_ids - {cid}
        ctrl = control_case_ids - {cid}
        metric = case_metric(pos, flagged_positive - {cid}, ctrl, flagged_control - {cid})
        leave_one_out.append({"removed_case": cid, "TP": metric["TP"], "FP": metric["FP"], "FPR": metric["false_positive_rate"], "decision_same": metric["TP"] >= 9 and metric["false_positive_rate"] <= 0.10})
    write_json(OUT_DIR / "leave_one_out_sensitivity.json", {"overfit_risk": "MEDIUM" if any(not row["decision_same"] for row in leave_one_out) else "LOW", "rows": leave_one_out})

    actionability_rows = []
    for code, count in sorted(Counter(code for row in row_results for code in row["violation_codes"]).items()):
        actionability_rows.append(
            {
                "violation": code,
                "recommended_action": "REQUEST_VALUE_GROUNDING" if "LITERAL" in code else "REJECT_OR_ESCALATE",
                "safe": "YES",
                "trigger_count": count,
            }
        )
    write_json(OUT_DIR / "actionability.json", {"rows": actionability_rows})

    correct_blocked = len(flagged_control)
    correct_accepted = len(control_case_ids - flagged_control)
    wrong_blocked = len(flagged_positive)
    wrong_accepted = len(residual_case_ids - flagged_positive)
    accepted_precision = correct_accepted / (correct_accepted + wrong_accepted) if correct_accepted + wrong_accepted else 0.0
    coverage = (correct_accepted + wrong_accepted) / (len(control_case_ids) + len(residual_case_ids))
    selective = {
        "label": "OFFLINE COUNTERFACTUAL",
        "correct_accepted": correct_accepted,
        "correct_blocked": correct_blocked,
        "wrong_accepted": wrong_accepted,
        "wrong_blocked": wrong_blocked,
        "offline_accepted_precision": round(accepted_precision, 4),
        "offline_coverage": round(coverage, 4),
        "offline_selective_risk": round(1 - accepted_precision, 4),
    }
    write_json(OUT_DIR / "selective_policy_simulation.json", selective)

    oss_decisions = {row["case_id"]: row.get("oss_verifier_decision") for row in forensics}
    verifier_comparison = {
        "matched_cases": len(residual_case_ids),
        "deterministic_catches_verifier_misses": sorted(cid for cid in flagged_positive if oss_decisions.get(cid) == "ACCEPT"),
        "verifier_catches_validator_misses": sorted(cid for cid in residual_case_ids - flagged_positive if oss_decisions.get(cid) == "REJECT"),
        "both_catch": sorted(cid for cid in flagged_positive if oss_decisions.get(cid) == "REJECT"),
        "both_miss": sorted(cid for cid in residual_case_ids - flagged_positive if oss_decisions.get(cid) != "REJECT"),
        "placement_recommendation": "cheap deterministic first, then semantic verifier if unresolved",
    }
    write_json(OUT_DIR / "verifier_comparison.json", verifier_comparison)

    first_determinism_rows = [
        {"candidate_id": row["candidate_id"], "case_id": row["case_id"], "result": row["result"]}
        for row in combined_rows
    ]
    first_hash = stable_hash(first_determinism_rows)
    second_rows = []
    for row in all_rows:
        result = validator.validate(p4_input(row, frozen_by_candidate))
        if row["case_id"] in residual_case_ids or row["case_id"] in control_case_ids:
            second_rows.append({"candidate_id": row["candidate_id"], "case_id": row["case_id"], "result": result.model_dump(mode="json")})
    second_hash = stable_hash(second_rows)
    determinism = {
        "first_hash": first_hash,
        "second_hash": second_hash,
        "deterministic": first_hash == second_hash,
    }
    write_json(OUT_DIR / "determinism_check.json", determinism)

    gold_leakage = {"status": "NONE", "forbidden_fields_rejected": []}
    for field in ["gold_sql", "gold_answer", "gold_tables"]:
        try:
            P4ValidationInput.model_validate({"question": "q", "candidate_sql": "SELECT 1", field: "x"})
        except ValidationError:
            gold_leakage["forbidden_fields_rejected"].append(field)
    gold_leakage["status"] = "NONE" if len(gold_leakage["forbidden_fields_rejected"]) == 3 else "FOUND"

    semantic_contract = {
        "schema_candidate": {
            "projection": ["requested output fields"],
            "filters": ["column/operator/value/null/range/boolean composition"],
            "measures": ["aggregate function and measured column"],
            "dimensions": ["grouping dimensions"],
            "grain": ["entity level for one row"],
            "join_intent": ["required endpoints and bridge constraints"],
        },
        "assessment": "Would improve false negatives where deterministic lexical extraction cannot recover intended grain/filter/projection safely.",
        "would_validator_quality_improve": "YES",
        "implementation_status": "SCHEMA_PROPOSAL_ONLY",
    }
    write_json(OUT_DIR / "semantic_contract_assessment.json", semantic_contract)

    p4_case_ids = {row["case_id"] for row in residual_questions if row["question_level_cause"] in P4_FAMILIES}
    p4_detected = len(p4_case_ids & flagged_positive)
    p4_baseline_detected = len(p4_case_ids & set(baseline["tp_cases"]))
    supported = (
        hardened["false_positive_rate"] <= 0.10
        and hardened["TP"] >= 9
        and p4_detected > p4_baseline_detected
        and determinism["deterministic"]
        and gold_leakage["status"] == "NONE"
        and len(false_positive_rows) == hardened["FP"]
    )
    strong = hardened["TP"] >= 10 and hardened["false_positive_rate"] <= 0.05
    decision = {
        "primary_decision": "VALIDATOR_IMPLEMENTATION_SUPPORTED" if supported else "VALIDATOR_IMPLEMENTATION_NOT_READY",
        "next_direction": "PROCEED_TO_PRODUCTION_INTEGRATION_DESIGN" if supported else "LIGHTWEIGHT_PLAN_IR_SHOULD_BE_NEXT",
        "evidence_strength": "VALIDATOR_EVIDENCE_STRONG" if strong else "VALIDATOR_EVIDENCE_MODERATE_OR_WEAK",
        "paid_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "p3": "SELECTIVE_P3_DEFERRED",
        "value_grounding": "VALUE_GROUNDING_SECONDARY",
        "gold_leakage": gold_leakage,
    }
    write_json(OUT_DIR / "decision.json", decision)

    cohort = {
        "positive_cohort": {
            "source": "results/p8e4_residual_bottleneck/residual_question_taxonomy.jsonl",
            "unique_questions": len(residual_case_ids),
            "trials": len(residual_trials),
            "cases": residual_questions,
        },
        "negative_control_cohort": {
            "source": "results/oss120b_failure_forensics/case_forensics.jsonl",
            "selection": "true_semantic_correctness=True and evidence_sufficiency=SUFFICIENT",
            "unique_questions": len(control_case_ids),
            "minimum_24_met": len(control_case_ids) >= 24,
        },
        "primary_unit": "unique_question",
    }
    write_json(OUT_DIR / "evaluation_cohort.json", cohort)

    manifest = {
        "phase": "P8-E6",
        "created_at": datetime.now(UTC).isoformat(),
        "api_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "artifacts": sorted(path.name for path in OUT_DIR.iterdir() if path.name != "manifest.json"),
    }
    write_json(OUT_DIR / "manifest.json", manifest)

    family_md = "\n".join(
        f"| {row['validator'].replace('V1_FILTER_CONTRACT', 'Filter').replace('V2_AGGREGATION_GRAIN', 'Aggregation/Grain').replace('V3_PROJECTION_SHAPE', 'Projection').replace('V4_JOIN_PATH_RISK', 'Join Path').replace('V5_SQL_CONSTRUCTION_SANITY', 'Construction')} | {row['positive_questions']} | {row['detected']} | {row['false_positives']} | {row['recall']:.2%} | {row['precision']:.2%} |"
        for row in family_metrics
    )
    fp_md = "\n".join(
        f"| {row['case']} | {', '.join(row['validator_code'])} | {row['why_sql_was_correct']} |"
        for row in false_positive_rows
    ) or "| None | None | None |"
    fn_md = "\n".join(
        f"| {row['case']} | {row['failure_family']} | {row['why_validator_missed']} | {row['candidate_next_step']} |"
        for row in false_negative_rows
    )
    summary = f"""# P8-E6 Deterministic P4 Validator Hardening

## Status

P8-E6 is COMPLETE. Paid calls: 0. Dev100 full LLM rerun: NO. Final holdout run: NO.

## Baseline Reproduction

P8-E5 prototype reproduced exactly from frozen local artifacts.

| Metric | P8-E5 Prototype | P8-E6 Hardened |
| ------ | --------------: | -------------: |
| TP | {baseline['TP']} | {hardened['TP']} |
| FP | {baseline['FP']} | {hardened['FP']} |
| TN | {baseline['TN']} | {hardened['TN']} |
| FN | {baseline['FN']} | {hardened['FN']} |
| Precision | {baseline['precision']:.2%} | {hardened['precision']:.2%} |
| Recall | {baseline['recall']:.2%} | {hardened['recall']:.2%} |
| FPR | {baseline['false_positive_rate']:.2%} | {hardened['false_positive_rate']:.2%} |

## Family Results

| Validator | Positive Questions | Detected | False Positives | Recall | Precision |
| --------- | -----------------: | -------: | --------------: | -----: | --------: |
{family_md}

## P4-Only Performance

P4 residual questions: 15. Detected: {p4_detected} / 15. P8-E5 prototype detected {p4_baseline_detected} / 15.

## False Positives

| Case | Validator | Why SQL Is Correct |
| ---- | --------- | ------------------ |
{fp_md}

## False Negatives

| Case | Failure Family | Why Validator Missed | Candidate Next Step |
| ---- | -------------- | -------------------- | ------------------- |
{fn_md}

## Offline Counterfactual

OFFLINE ONLY. Correct accepted: {selective['correct_accepted']}. Correct blocked: {selective['correct_blocked']}. Wrong accepted: {selective['wrong_accepted']}. Wrong blocked: {selective['wrong_blocked']}.

Accepted precision: {selective['offline_accepted_precision']:.2%}. Coverage: {selective['offline_coverage']:.2%}. Selective risk: {selective['offline_selective_risk']:.2%}.

## Determinism And Leakage

Determinism: {'PASS' if determinism['deterministic'] else 'FAIL'}. Gold leakage: {gold_leakage['status']}.

## Decision

Scientific decision: {decision['primary_decision']}.

Next direction: {decision['next_direction']}.

P3: SELECTIVE_P3_DEFERRED. Value grounding: VALUE_GROUNDING_SECONDARY. PAID_CALLS = 0.
"""
    (OUT_DIR / "summary.md").write_text(summary)
    REPORT_PATH.write_text(summary)

    print(f"Wrote {OUT_DIR}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
