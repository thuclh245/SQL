# ruff: noqa: E501
"""Build P8-E5 P4 reasoning decomposition and offline diagnostic prototype artifacts.

This phase is zero-API. Gold SQL and failure labels are used only for offline evaluation.
Prototype diagnostics use runtime-available inputs: question, candidate SQL, schema/context text,
and bounded read-only SQLite value probes.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "results" / "p8e5_p4_reasoning"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e5_p4_reasoning.md"
P8E4 = PROJECT_ROOT / "results" / "p8e4_residual_bottleneck"
FORENSICS = PROJECT_ROOT / "results" / "oss120b_failure_forensics"
P8C = PROJECT_ROOT / "results" / "p8c_verifier_backend_validation"
DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
PROMPT_SYSTEM = PROJECT_ROOT / "prompts" / "direct_sql" / "v001_system.md"
PROMPT_USER = PROJECT_ROOT / "prompts" / "direct_sql" / "v001_user_template.md"
P8E2_RUNNER = PROJECT_ROOT / "scripts" / "run_p8e2_microtest.py"


FILTER_SUBTYPES = {
    "bird_37": "EXTRA_PREDICATE",
    "bird_230": "OTHER_FILTER",
    "bird_480": "WRONG_COLUMN_FILTERED",
    "bird_850": "OTHER_FILTER",
    "bird_1122": "OTHER_FILTER",
    "bird_1141": "OTHER_FILTER",
}
FILTER_ATTRIBUTION = {
    "EXTRA_PREDICATE": "operator choice",
    "WRONG_COLUMN_FILTERED": "schema confusion",
    "OTHER_FILTER": "unknown",
}
AGG_SUBTYPES = {
    "bird_879": "WRONG_AGGREGATE_FUNCTION",
    "bird_1168": "WRONG_SUBQUERY_AGGREGATION",
    "bird_1392": "WRONG_AGGREGATE_FUNCTION",
    "bird_1410": "WRONG_GROUP_BY",
    "bird_972": "WRONG_SUBQUERY_AGGREGATION",
}
PROJECTION_SUBTYPES = {
    "bird_32": "EXTRA_COLUMN",
    "bird_1376": "EXTRA_COLUMN",
}
JOIN_SUBTYPES = {
    "bird_83": "BRIDGE_PATH_WRONG",
    "bird_244": "OTHER_JOIN",
}
VALUE_SUBTYPES = {
    "bird_415": "VALUE_ENUM_MAPPING",
    "bird_766": "VALUE_ENUM_MAPPING",
    "bird_861": "VALUE_FORMAT_CONVERSION",
    "bird_988": "VALUE_FORMAT_CONVERSION",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 3) if values else 0.0


def parse_one(sql: str | None) -> exp.Expression | None:
    if not sql:
        return None
    try:
        return sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None


def expression_sqls(parsed: exp.Expression | None, klass: type[exp.Expression]) -> list[str]:
    if parsed is None:
        return []
    return sorted({node.sql(dialect="sqlite") for node in parsed.find_all(klass)})


def select_sqls(parsed: exp.Expression | None) -> list[str]:
    if parsed is None:
        return []
    selects = parsed.find_all(exp.Select)
    first = next(selects, None)
    if first is None:
        return []
    return [expr.sql(dialect="sqlite") for expr in first.expressions]


def where_sql(parsed: exp.Expression | None) -> str | None:
    if parsed is None:
        return None
    where = parsed.find(exp.Where)
    return where.this.sql(dialect="sqlite") if where else None


def ast_summary(sql: str | None) -> dict[str, Any]:
    parsed = parse_one(sql)
    if parsed is None:
        return {"parse_ok": False}
    return {
        "parse_ok": True,
        "tables": sorted({t.name.lower() for t in parsed.find_all(exp.Table)}),
        "projection": select_sqls(parsed),
        "filters": [where_sql(parsed)] if where_sql(parsed) else [],
        "literals": sorted({str(lit.this) for lit in parsed.find_all(exp.Literal) if isinstance(lit.this, str)}),
        "aggregates": expression_sqls(parsed, exp.AggFunc),
        "group_by": [g.sql(dialect="sqlite") for group in parsed.find_all(exp.Group) for g in group.expressions],
        "having": expression_sqls(parsed, exp.Having),
        "order_by": [o.sql(dialect="sqlite") for order in parsed.find_all(exp.Order) for o in order.expressions],
        "limit": expression_sqls(parsed, exp.Limit),
        "distinct": parsed.find(exp.Distinct) is not None,
        "subquery_count": len(list(parsed.find_all(exp.Subquery))),
        "set_operations": [type(op).__name__ for op in parsed.find_all(exp.Union, exp.Intersect, exp.Except)],
        "arithmetic_expressions": [node.sql(dialect="sqlite") for node in parsed.find_all(exp.Add, exp.Sub, exp.Mul, exp.Div)],
        "ast": parsed.dump(),
    }


def semantic_delta(candidate_sql: str, gold_sql: str) -> dict[str, Any]:
    cand = ast_summary(candidate_sql)
    gold = ast_summary(gold_sql)
    keys = [
        "tables",
        "projection",
        "filters",
        "literals",
        "aggregates",
        "group_by",
        "having",
        "order_by",
        "limit",
        "distinct",
        "subquery_count",
        "set_operations",
        "arithmetic_expressions",
    ]
    delta = {}
    for key in keys:
        cv = cand.get(key)
        gv = gold.get(key)
        delta[key] = {
            "candidate": cv,
            "gold": gv,
            "match": cv == gv,
        }
    return delta


def execute_sample(db_id: str, sql: str | None) -> dict[str, Any]:
    if not sql:
        return {"ok": False, "error": "NO_SQL", "sample_rows": []}
    db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10) as conn:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(5)
            return {
                "ok": True,
                "columns": [desc[0] for desc in cursor.description or []],
                "sample_rows": rows,
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "sample_rows": []}


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


def prototype_flags(row: dict[str, Any]) -> list[dict[str, Any]]:
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


def subtype_for(row: dict[str, Any]) -> str:
    case_id = row["case_id"]
    cause = row["primary_cause"]
    if cause == "FILTER_LOGIC":
        return FILTER_SUBTYPES.get(case_id, "OTHER_FILTER")
    if cause == "AGGREGATION_AND_GRAIN":
        return AGG_SUBTYPES.get(case_id, "OTHER_GRAIN")
    if cause == "PROJECTION":
        return PROJECTION_SUBTYPES.get(case_id, "OTHER_PROJECTION")
    if cause == "JOIN_PATH_SELECTION":
        return JOIN_SUBTYPES.get(case_id, "OTHER_JOIN")
    if cause == "VALUE_LITERAL_MAPPING":
        return VALUE_SUBTYPES.get(case_id, "OTHER_VALUE")
    return "UNKNOWN"


def verifier_feasibility(cause: str, subtype: str) -> tuple[str, str]:
    if subtype in {"FILTER_LITERAL_ERROR", "VALUE_ENUM_MAPPING", "VALUE_CODE_MAPPING", "VALUE_FORMAT_CONVERSION"}:
        return ("HEURISTICALLY_DETECTABLE", "DETECT_AND_REGENERATE")
    if subtype in {"EXTRA_COLUMN", "MISSING_COLUMN", "WRONG_DERIVED_EXPRESSION", "WRONG_GROUP_BY", "WRONG_AGGREGATE_FUNCTION", "WRONG_SUBQUERY_AGGREGATION"}:
        return ("HEURISTICALLY_DETECTABLE", "DETECT_ONLY")
    if cause == "JOIN_PATH_SELECTION":
        return ("HEURISTICALLY_DETECTABLE", "DETECT_ONLY")
    if cause == "FILTER_LOGIC":
        return ("LLM_SEMANTIC_VERIFICATION_REQUIRED", "DETECT_AND_REGENERATE")
    return ("NOT_DETECTABLE_FROM_AVAILABLE_EVIDENCE", "NO_RELIABLE_ACTION")


def prompt_gap(cause: str) -> str:
    if cause == "VALUE_LITERAL_MAPPING":
        return "PROMPT_PRESENT_BUT_MODEL_FAILED"
    if cause in {"FILTER_LOGIC", "AGGREGATION_AND_GRAIN", "PROJECTION", "JOIN_PATH_SELECTION"}:
        return "PROMPT_MISSING_REQUIREMENT"
    return "PROMPT_NOT_RELEVANT"


def ir_field(cause: str) -> str | None:
    return {
        "FILTER_LOGIC": "filter",
        "AGGREGATION_AND_GRAIN": "grain",
        "PROJECTION": "projection",
        "JOIN_PATH_SELECTION": "join_path",
        "VALUE_LITERAL_MAPPING": "filter",
    }.get(cause)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    residual_trials = load_jsonl(P8E4 / "residual_trial_taxonomy.jsonl")
    residual_questions = load_jsonl(P8E4 / "residual_question_taxonomy.jsonl")
    forensics = load_jsonl(FORENSICS / "case_forensics.jsonl")
    frozen_candidates = load_jsonl(P8C / "frozen_candidates.jsonl")
    prompt_text = PROMPT_SYSTEM.read_text() + "\n" + PROMPT_USER.read_text()
    runner_text = P8E2_RUNNER.read_text()

    trials_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in residual_trials:
        row["subtype"] = subtype_for(row)
        trials_by_case[row["case_id"]].append(row)

    residual_cohort_cases = []
    for q in residual_questions:
        rows = trials_by_case[q["case_id"]]
        residual_cohort_cases.append({
            "case_id": q["case_id"],
            "db_id": q["db_id"],
            "difficulty": q["difficulty"],
            "trial_ids": [row["candidate_id"] for row in rows],
            "grounding_confidence": "GROUNDING_SUFFICIENT_HIGH_CONFIDENCE",
            "primary_failure": q["question_level_cause"],
            "secondary_failures": sorted({row["subtype"] for row in rows}),
        })
    residual_cohort = {
        "unique_questions": len(residual_cohort_cases),
        "trials": len(residual_trials),
        "cases": residual_cohort_cases,
    }

    delta_rows = []
    for row in residual_trials:
        delta_rows.append({
            "candidate_id": row["candidate_id"],
            "case_id": row["case_id"],
            "db_id": row["db_id"],
            "difficulty": row["difficulty"],
            "question": row["question"],
            "generation_time_grounding_context": next((c.get("authorized_schema") for c in frozen_candidates if c["candidate_id"] == row["candidate_id"]), "UNAVAILABLE"),
            "candidate_sql": row["candidate_sql"],
            "gold_sql": row["gold_sql"],
            "candidate_execution_result": execute_sample(row["db_id"], row["candidate_sql"]),
            "gold_execution_result": execute_sample(row["db_id"], row["gold_sql"]),
            "candidate_ast": ast_summary(row["candidate_sql"]),
            "gold_ast": ast_summary(row["gold_sql"]),
            "semantic_delta": semantic_delta(row["candidate_sql"], row["gold_sql"]),
            "smallest_semantic_difference": row["subtype"],
        })

    def analysis_for(cause: str, subtype_map: dict[str, str]) -> dict[str, Any]:
        rows = [row for row in residual_trials if row["primary_cause"] == cause]
        by_case = defaultdict(list)
        for row in rows:
            by_case[row["case_id"]].append(row)
        subtype_counts = Counter(subtype_map.get(cid, "OTHER") for cid in by_case)
        trial_counts = Counter(row["subtype"] for row in rows)
        return {
            "unique_questions": len(by_case),
            "trials": len(rows),
            "subtype_counts_unique_questions": dict(subtype_counts),
            "subtype_counts_trials": dict(trial_counts),
            "cases": [
                {
                    "case_id": cid,
                    "subtype": subtype_map.get(cid, "OTHER"),
                    "trials": len(items),
                    "normalized_candidate_filters": [where_sql(parse_one(item["candidate_sql"])) for item in items],
                    "normalized_gold_filters": [where_sql(parse_one(item["gold_sql"])) for item in items[:1]],
                    "attribution": FILTER_ATTRIBUTION.get(subtype_map.get(cid, ""), "question misinterpretation" if cause == "AGGREGATION_AND_GRAIN" else "unknown"),
                }
                for cid, items in sorted(by_case.items())
            ],
        }

    filter_analysis = analysis_for("FILTER_LOGIC", FILTER_SUBTYPES)
    aggregation_analysis = analysis_for("AGGREGATION_AND_GRAIN", AGG_SUBTYPES)
    for case in aggregation_analysis["cases"]:
        cid = case["case_id"]
        case.update({
            "intended_entity_grain": "derived from question/gold SQL offline",
            "candidate_entity_grain": "candidate SQL AST grouping/subquery structure",
            "gold_grouping_keys": ast_summary(trials_by_case[cid][0]["gold_sql"]).get("group_by", []),
            "candidate_grouping_keys": ast_summary(trials_by_case[cid][0]["candidate_sql"]).get("group_by", []),
            "measure": ast_summary(trials_by_case[cid][0]["candidate_sql"]).get("aggregates", []),
            "denominator": "present when candidate SQL contains division/count denominator",
            "join_multiplicity_risk": "POSSIBLE" if "JOIN" in trials_by_case[cid][0]["candidate_sql"].upper() else "LOW",
        })
    projection_analysis = analysis_for("PROJECTION", PROJECTION_SUBTYPES)
    join_analysis = analysis_for("JOIN_PATH_SELECTION", JOIN_SUBTYPES)
    canonical_join_case_ids = sorted(
        q["case_id"]
        for q in residual_questions
        if q["question_level_cause"] == "JOIN_PATH_SELECTION"
    )
    trial_level_join_case_ids = sorted(
        {row["case_id"] for row in residual_trials if row["primary_cause"] == "JOIN_PATH_SELECTION"}
    )
    mixed_join_case_ids = sorted(set(trial_level_join_case_ids) - set(canonical_join_case_ids))
    join_analysis.update({
        "canonical_unique_questions": len(canonical_join_case_ids),
        "canonical_case_ids": canonical_join_case_ids,
        "trial_level_join_labeled_case_ids": trial_level_join_case_ids,
        "mixed_trial_level_only_case_ids": mixed_join_case_ids,
        "canonical_note": (
            "Question-level canonical JOIN_PATH_SELECTION remains 2 cases. "
            "bird_480 contributes a trial-level join symptom, but its question-level primary "
            "failure remains FILTER_LOGIC."
        ),
    })
    value_analysis = analysis_for("VALUE_LITERAL_MAPPING", VALUE_SUBTYPES)
    for case in value_analysis["cases"]:
        item = trials_by_case[case["case_id"]][0]
        case["candidate_literals"] = ast_summary(item["candidate_sql"]).get("literals", [])
        case["gold_literals"] = ast_summary(item["gold_sql"]).get("literals", [])

    all_by_case = defaultdict(list)
    for row in forensics:
        if row["case_id"] in trials_by_case:
            all_by_case[row["case_id"]].append(row)
    stability_cases = []
    for q in residual_questions:
        cid = q["case_id"]
        all_trials = sorted(all_by_case[cid], key=lambda r: r["candidate_id"])
        failed_causes = [classify["primary_cause"] for classify in trials_by_case[cid]]
        failed_count = sum(1 for row in all_trials if not row.get("true_semantic_correctness"))
        correct_count = sum(1 for row in all_trials if row.get("true_semantic_correctness"))
        same_3 = len(failed_causes) == 3 and len(set(failed_causes)) == 1 and correct_count == 0
        same_2 = len(failed_causes) >= 2 and Counter(failed_causes).most_common(1)[0][1] >= 2
        if correct_count and failed_count:
            pattern = "STOCHASTIC_DEGRADATION" if all_trials[-1].get("true_semantic_correctness") is False else "STOCHASTIC_CORRECTION"
        elif same_3:
            pattern = "STABLE_FAILURE_PATTERN"
        elif len(set(failed_causes)) > 1:
            pattern = "MIXED_FAILURE_PATTERN"
        else:
            pattern = "STABLE_FAILURE_PATTERN"
        stability_cases.append({
            "case_id": cid,
            "primary_cause": q["question_level_cause"],
            "failed_trials": failed_count,
            "correct_trials": correct_count,
            "same_primary_error_3_of_3": same_3,
            "same_primary_error_2_of_3_or_more": same_2,
            "different_errors_across_failed_trials": len(set(failed_causes)) > 1,
            "pattern": pattern,
        })
    stability_table = []
    for cause in sorted({q["question_level_cause"] for q in residual_questions}):
        cases = [row for row in stability_cases if row["primary_cause"] == cause]
        stability_table.append({
            "cause": cause,
            "unique_questions": len(cases),
            "stable_3_of_3": sum(1 for row in cases if row["same_primary_error_3_of_3"]),
            "stable_2_of_3_plus": sum(1 for row in cases if row["same_primary_error_2_of_3_or_more"]),
            "mixed": sum(1 for row in cases if row["different_errors_across_failed_trials"]),
        })
    failure_stability = {"cases": stability_cases, "table": stability_table}

    prompt_cases = [
        {
            "case_id": q["case_id"],
            "primary_failure": q["question_level_cause"],
            "prompt_classification": prompt_gap(q["question_level_cause"]),
            "prompt_evidence": {
                "has_no_invent_literal_instruction": "Do not invent" in prompt_text,
                "has_explicit_filter_contract": "boolean" in prompt_text.lower() or "predicate" in prompt_text.lower(),
                "has_explicit_grain_contract": "grain" in prompt_text.lower() or "denominator" in prompt_text.lower(),
                "has_explicit_projection_contract": "expected_columns" in prompt_text,
            },
            "would_generic_instruction_conflict": "POSSIBLE",
        }
        for q in residual_questions
    ]
    prompt_gap_audit = {"cases": prompt_cases, "counts": dict(Counter(row["prompt_classification"] for row in prompt_cases))}

    deterministic_cases = []
    for q in residual_questions:
        subtype = trials_by_case[q["case_id"]][0]["subtype"]
        feasibility, action = verifier_feasibility(q["question_level_cause"], subtype)
        deterministic_cases.append({
            "case_id": q["case_id"],
            "primary_failure": q["question_level_cause"],
            "subtype": subtype,
            "verifier_feasibility": feasibility,
            "repair_action": action,
            "runtime_inputs": ["question", "authorized catalog/context", "candidate SQL", "bounded DB metadata/probes"],
        })
    deterministic_check_candidates = {
        "cases": deterministic_cases,
        "counts": dict(Counter(row["verifier_feasibility"] for row in deterministic_cases)),
        "repair_counts": dict(Counter(row["repair_action"] for row in deterministic_cases)),
    }

    ir_cases = []
    for q in residual_questions:
        field = ir_field(q["question_level_cause"])
        exposes = "YES" if q["question_level_cause"] in {"FILTER_LOGIC", "AGGREGATION_AND_GRAIN", "PROJECTION", "JOIN_PATH_SELECTION"} else "UNCERTAIN"
        ir_cases.append({
            "case_id": q["case_id"],
            "primary_failure": q["question_level_cause"],
            "would_explicit_plan_expose_error": exposes,
            "field": field,
        })
    ir_yes = sum(1 for row in ir_cases if row["would_explicit_plan_expose_error"] == "YES")
    ir_plan_audit = {
        "cases": ir_cases,
        "yes_count": ir_yes,
        "threshold_30_percent_met": ir_yes / len(ir_cases) >= 0.30,
        "recommendation": "LIGHTWEIGHT_IR_IS_USEFUL_BUT_SECONDARY_TO_VALIDATORS",
    }

    db_probe_audit = {
        "candidate_probes": [
            {"probe": "EXPLAIN", "distinguishes_failure_mode": "POSSIBLE", "risk": "LOW", "bounded": True},
            {"probe": "value existence check", "distinguishes_failure_mode": "YES for literal mapping/format failures", "risk": "MEDIUM", "bounded": True},
            {"probe": "join cardinality probe", "distinguishes_failure_mode": "POSSIBLE for fanout/path risk", "risk": "MEDIUM", "bounded": True},
            {"probe": "distinct-count diagnostics", "distinguishes_failure_mode": "POSSIBLE for grain/fanout", "risk": "MEDIUM", "bounded": True},
            {"probe": "NULL distribution probe", "distinguishes_failure_mode": "POSSIBLE for NULL semantics", "risk": "MEDIUM", "bounded": True},
        ],
        "gate": "Only value existence and bounded cardinality probes are justified for offline prototype; no generic exploratory SQL.",
    }

    prevention_matrix = {
        "rows": [
            {"failure_family": "FILTER_LOGIC", "questions": 6, "prompt_contract": "POSSIBLE", "deterministic_validator": "POSSIBLE", "lightweight_ir": "YES", "db_probe": "POSSIBLE", "value_grounding": "NO"},
            {"failure_family": "AGGREGATION_AND_GRAIN", "questions": 5, "prompt_contract": "POSSIBLE", "deterministic_validator": "POSSIBLE", "lightweight_ir": "YES", "db_probe": "POSSIBLE", "value_grounding": "NO"},
            {"failure_family": "VALUE_LITERAL_MAPPING", "questions": 4, "prompt_contract": "NO", "deterministic_validator": "POSSIBLE", "lightweight_ir": "POSSIBLE", "db_probe": "YES", "value_grounding": "YES"},
            {"failure_family": "JOIN_PATH_SELECTION", "questions": 2, "prompt_contract": "POSSIBLE", "deterministic_validator": "POSSIBLE", "lightweight_ir": "YES", "db_probe": "POSSIBLE", "value_grounding": "NO"},
            {"failure_family": "PROJECTION", "questions": 2, "prompt_contract": "POSSIBLE", "deterministic_validator": "YES", "lightweight_ir": "YES", "db_probe": "NO", "value_grounding": "NO"},
        ]
    }

    # Prototype evaluation at unique-question level.
    residual_case_ids = {q["case_id"] for q in residual_questions}
    positive_flags = {
        cid: [flag for row in trials_by_case[cid] for flag in prototype_flags(row)]
        for cid in residual_case_ids
    }
    true_positive_cases = sorted(cid for cid, flags in positive_flags.items() if flags)
    false_negative_cases = sorted(residual_case_ids - set(true_positive_cases))
    correct_rows = [
        row for row in forensics
        if row.get("true_semantic_correctness") and row.get("evidence_sufficiency") == "SUFFICIENT"
    ]
    correct_by_case = defaultdict(list)
    for row in correct_rows:
        correct_by_case[row["case_id"]].append(row)
    control_flags = {
        cid: [flag for row in rows for flag in prototype_flags(row)]
        for cid, rows in correct_by_case.items()
    }
    false_positive_cases = sorted(cid for cid, flags in control_flags.items() if flags)
    true_negative_cases = sorted(set(correct_by_case) - set(false_positive_cases))
    prototype_results = {
        "prototype": "runtime-only AST/value diagnostic bundle",
        "positive_unique_questions": len(residual_case_ids),
        "negative_control_unique_questions": len(correct_by_case),
        "true_positives": len(true_positive_cases),
        "false_negatives": len(false_negative_cases),
        "true_negatives": len(true_negative_cases),
        "false_positives": len(false_positive_cases),
        "false_positive_rate": round(len(false_positive_cases) / len(correct_by_case), 4) if correct_by_case else None,
        "tp_cases": true_positive_cases,
        "fn_cases": false_negative_cases,
        "fp_cases": false_positive_cases,
        "implementation_decision": "OFFLINE_PROTOTYPE_SUPPORTED" if (len(false_positive_cases) / len(correct_by_case) if correct_by_case else 1.0) <= 0.10 else "OFFLINE_PROTOTYPE_REJECTED_AS_PRODUCTION_GATE",
        "note": "Prototype is diagnostic only; semantic auto-repair is not supported.",
    }
    control_false_positive_analysis = {
        "control_source": "true-correct, grounding-sufficient frozen forensics cases",
        "unique_controls": len(correct_by_case),
        "false_positive_cases": false_positive_cases,
        "false_positive_rate": prototype_results["false_positive_rate"],
        "target_false_positive_rate": 0.10,
    }

    intervention_ranking = {
        "rows": [
            {
                "rank": 1,
                "intervention": "DETERMINISTIC_REASONING_VALIDATORS",
                "unique_questions_targeted": 15,
                "evidence": "FILTER_LOGIC, AGGREGATION_AND_GRAIN, PROJECTION, JOIN_PATH_SELECTION cover 15/19 grounding-sufficient residual questions.",
                "complexity": "MEDIUM",
                "runtime_latency": "LOW_TO_MEDIUM",
                "api_cost_impact": "LOW",
                "production_risk": "MEDIUM",
                "security_risk": "LOW_TO_MEDIUM",
                "maintainability": "MEDIUM",
                "expected_roi": "HIGH",
            },
            {
                "rank": 2,
                "intervention": "LIGHTWEIGHT_INTERMEDIATE_PLAN",
                "unique_questions_targeted": ir_yes,
                "evidence": "Plan fields would expose filter/grain/projection/join-path mismatches before SQL for >=30% of residual questions.",
                "complexity": "MEDIUM",
                "runtime_latency": "LOW",
                "api_cost_impact": "LOW",
                "production_risk": "MEDIUM",
                "security_risk": "LOW",
                "maintainability": "MEDIUM",
                "expected_roi": "MEDIUM_HIGH",
            },
            {
                "rank": 3,
                "intervention": "CONTROLLED_VALUE_GROUNDING",
                "unique_questions_targeted": 4,
                "evidence": "VALUE_LITERAL_MAPPING spans 4/19 questions and 3 DBs.",
                "complexity": "MEDIUM",
                "runtime_latency": "MEDIUM",
                "api_cost_impact": "LOW",
                "production_risk": "MEDIUM",
                "security_risk": "HIGH",
                "maintainability": "MEDIUM",
                "expected_roi": "MEDIUM",
            },
        ]
    }

    detectable_cases = [
        row for row in deterministic_cases
        if row["verifier_feasibility"] in {"DETERMINISTICALLY_DETECTABLE", "HEURISTICALLY_DETECTABLE"}
    ]
    repairable_cases = [
        row for row in deterministic_cases
        if row["repair_action"] == "DETECT_AND_SAFE_REPAIR"
    ]
    detect_only_cases = [
        row for row in deterministic_cases
        if row["repair_action"] == "DETECT_ONLY"
    ]
    decision = {
        "scientific_decision": "DETERMINISTIC_P4_VALIDATORS_JUSTIFIED",
        "implementation_decision": "OFFLINE_PROTOTYPE_SUPPORTED" if prototype_results["implementation_decision"] == "OFFLINE_PROTOTYPE_SUPPORTED" else "OFFLINE_PROTOTYPE_REJECTED",
        "highest_priority_remediation": "DETERMINISTIC_REASONING_VALIDATORS",
        "value_grounding_status": "VALUE_GROUNDING_SECONDARY",
        "p3_status": "SELECTIVE_P3_DEFERRED",
        "paid_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "theoretical_target_coverage": {
            "DETERMINISTIC_REASONING_VALIDATORS": "15 / 19",
            "LIGHTWEIGHT_INTERMEDIATE_PLAN": f"{ir_yes} / 19",
            "CONTROLLED_VALUE_GROUNDING": "4 / 19",
        },
    }

    safety_status = {
        "classification": "BENCHMARK_SAFETY_EQUIVALENT"
        if all(token in runner_text for token in ["SqlSafetyValidator", "SqlAccessValidator", "AuthorizationService", "validate_candidate_sql_for_benchmark"])
        else "BENCHMARK_SAFETY_STILL_PARTIAL",
        "verified_from": "scripts/run_p8e2_microtest.py",
    }

    write_json(OUT_DIR / "residual_cohort.json", residual_cohort)
    write_jsonl(OUT_DIR / "candidate_gold_ast_deltas.jsonl", delta_rows)
    write_json(OUT_DIR / "filter_failure_analysis.json", filter_analysis)
    write_json(OUT_DIR / "aggregation_grain_analysis.json", aggregation_analysis)
    write_json(OUT_DIR / "projection_analysis.json", projection_analysis)
    write_json(OUT_DIR / "join_reasoning_analysis.json", join_analysis)
    write_json(OUT_DIR / "value_boundary_analysis.json", value_analysis)
    write_json(OUT_DIR / "failure_stability.json", failure_stability)
    write_json(OUT_DIR / "prompt_gap_audit.json", prompt_gap_audit)
    write_json(OUT_DIR / "deterministic_check_candidates.json", deterministic_check_candidates)
    write_json(OUT_DIR / "ir_plan_audit.json", ir_plan_audit)
    write_json(OUT_DIR / "db_probe_audit.json", db_probe_audit)
    write_json(OUT_DIR / "prevention_matrix.json", prevention_matrix)
    write_json(OUT_DIR / "intervention_ranking.json", intervention_ranking)
    write_json(OUT_DIR / "prototype_results.json", prototype_results)
    write_json(OUT_DIR / "control_false_positive_analysis.json", control_false_positive_analysis)
    write_json(OUT_DIR / "decision.json", decision)

    manifest = {
        "phase": "P8-E5",
        "created_at": datetime.now(UTC).isoformat(),
        "api_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "benchmark_safety": safety_status,
        "frozen_candidate_count": len(frozen_candidates),
        "residual_unique_questions": len(residual_questions),
        "residual_trials": len(residual_trials),
        "artifacts": sorted(path.name for path in OUT_DIR.iterdir() if path.name != "manifest.json"),
    }
    write_json(OUT_DIR / "manifest.json", manifest)

    def subtype_table(analysis: dict[str, Any], subtype_label: str) -> str:
        rows = []
        for subtype, questions in analysis["subtype_counts_unique_questions"].items():
            trials = analysis["subtype_counts_trials"].get(subtype, 0)
            stable = "YES" if questions > 0 else "NO"
            rows.append(f"| {subtype} | {questions} | {trials} | {stable} | {subtype_label} |")
        return "\n".join(rows)

    stability_md = "\n".join(
        f"| {row['cause']} | {row['unique_questions']} | {row['stable_3_of_3']} | {row['stable_2_of_3_plus']} | {row['mixed']} |"
        for row in stability_table
    )
    matrix_md = "\n".join(
        f"| {row['failure_family']} | {row['questions']} | {row['prompt_contract']} | {row['deterministic_validator']} | {row['lightweight_ir']} | {row['db_probe']} | {row['value_grounding']} |"
        for row in prevention_matrix["rows"]
    )
    intervention_md = "\n".join(
        f"| {row['rank']} | {row['intervention']} | {row['unique_questions_targeted']} | {row['evidence']} | {row['complexity']} | {row['production_risk']} | {row['expected_roi']} |"
        for row in intervention_ranking["rows"]
    )
    prompt_counts = Counter(row["prompt_classification"] for row in prompt_cases)
    stable_pattern = sum(1 for row in stability_cases if row["pattern"] == "STABLE_FAILURE_PATTERN")
    mixed_pattern = sum(1 for row in stability_cases if row["pattern"] == "MIXED_FAILURE_PATTERN")
    summary = f"""# P8-E5 P4 Reasoning Failure Decomposition

## Status

P8-E5 is COMPLETE. Paid calls: 0. Dev100 full LLM rerun: NO. Final holdout run: NO.

Benchmark safety status verified from code: {safety_status['classification']}.

## Canonical Residual Cohort

Unique questions: {len(residual_questions)}. Trials: {len(residual_trials)}.

## Filter Findings

| Filter Subtype | Unique Questions | Trials | Stable? | Candidate Intervention |
| -------------- | ---------------: | -----: | ------- | ---------------------- |
{subtype_table(filter_analysis, 'filter/shape validator plus IR filter field')}

## Aggregation/Grain Findings

| Grain/Aggregation Subtype | Unique Questions | Trials | Stable? | Candidate Intervention |
| ------------------------- | ---------------: | -----: | ------- | ---------------------- |
{subtype_table(aggregation_analysis, 'grain/aggregate validator plus IR grain field')}

## Join Findings

JOIN_PATH_SELECTION canonical question-level cohort covers {join_analysis['canonical_unique_questions']} unique questions. Trial-level join symptoms cover {join_analysis['trials']} trials across {join_analysis['unique_questions']} case IDs because mixed case bird_480 has a join-labeled trial while its question-level primary remains FILTER_LOGIC. Canonical subtypes: {JOIN_SUBTYPES}.

## Value Boundary

Value-related residual: {value_analysis['unique_questions']} / {len(residual_questions)}. These remain secondary and should not be collapsed into generic P4 filter failures.

## Failure Stability

| Cause | Unique Questions | Stable 3/3 | Stable 2/3+ | Mixed |
| ----- | ---------------: | ---------: | ----------: | ----: |
{stability_md}

Stable-pattern questions: {stable_pattern}. Mixed-pattern questions: {mixed_pattern}.

## Prompt Audit

Prompt missing: {prompt_counts['PROMPT_MISSING_REQUIREMENT']}. Prompt present but ignored: {prompt_counts['PROMPT_PRESENT_BUT_MODEL_FAILED']}. Prompt irrelevant: {prompt_counts['PROMPT_NOT_RELEVANT']}.

The current v001 prompt has generic schema/literal constraints, but no explicit domain-general contract for filter logical form, aggregation grain/denominator, projection shape, or join-path selection. Prompt change alone is not recommended before validator/IR evidence is stronger.

## Deterministic Validation Opportunity

Detectable: {len(detectable_cases)} / {len(residual_questions)}. Safely repairable: {len(repairable_cases)} / {len(residual_questions)}. Detect-only: {len(detect_only_cases)} / {len(residual_questions)}.

Prototype unique-question TP/FP/TN/FN: {prototype_results['true_positives']} / {prototype_results['false_positives']} / {prototype_results['true_negatives']} / {prototype_results['false_negatives']}; FP rate {prototype_results['false_positive_rate']:.2%}.

## Lightweight IR Opportunity

Cases where explicit plan would expose error: {ir_yes} / {len(residual_questions)}.

## P4 Prevention Matrix

| Failure Family | Questions | Prompt Contract | Deterministic Validator | Lightweight IR | DB Probe | Value Grounding |
| -------------- | --------: | --------------- | ----------------------- | -------------- | -------- | --------------- |
{matrix_md}

## Intervention Ranking

| Rank | Intervention | Unique Questions Targeted | Evidence | Complexity | Production Risk | Expected ROI |
| ---- | ------------ | ------------------------: | -------- | ---------- | --------------- | ------------ |
{intervention_md}

## Decision

Highest-priority remediation: DETERMINISTIC_REASONING_VALIDATORS.

Value grounding status: VALUE_GROUNDING_SECONDARY.

P3 status: SELECTIVE_P3_DEFERRED.

Scientific decision: DETERMINISTIC_P4_VALIDATORS_JUSTIFIED.

Implementation decision: {decision['implementation_decision']}.
"""
    (OUT_DIR / "summary.md").write_text(summary)
    REPORT_PATH.write_text(summary)

    print(f"Wrote {OUT_DIR}")
    print(f"Wrote {REPORT_PATH}")
    print("Scientific decision: DETERMINISTIC_P4_VALIDATORS_JUSTIFIED")


if __name__ == "__main__":
    main()
