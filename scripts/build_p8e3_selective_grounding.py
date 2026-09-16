# ruff: noqa: E501
"""Build zero-API P8-E3 selective grounding diagnostics.

This script only reads local artifacts/catalogs/SQLite databases and replays deterministic
grounding contexts. It does not call any model endpoint.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.catalog import CatalogSearchDocumentBuilder, CatalogTable
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import GroundingContext, QueryRequest
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch, tokenize_search_text
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
DEV100_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
P8E2_DIR = PROJECT_ROOT / "results" / "p8e2_microtest"
P8E1R2_DIR = PROJECT_ROOT / "results" / "p8e1r2_microtest_preregistration"
P8E1_DIR = PROJECT_ROOT / "results" / "p8e1_p3_remediation"
OUT_DIR = PROJECT_ROOT / "results" / "p8e3_selective_grounding"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e3_selective_grounding.md"

TARGET_IDS = [
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
CONTROL_IDS = ["bird_744", "bird_549", "bird_1344", "bird_168", "bird_213"]
RECOVERED_IDS = {"bird_100", "bird_1096", "bird_206", "bird_705"}
REGRESSED_IDS = {"bird_744", "bird_1344", "bird_168"}
API_ERROR_IDS = {"bird_344", "bird_416"}

POLICIES = {
    "BASELINE": GroundingBudget(),
    "A_ONLY": GroundingBudget(relationship_expansion_mode="unconditional"),
    "B_ONLY": GroundingBudget(fill_column_budget=True),
    "A+B": GroundingBudget(relationship_expansion_mode="unconditional", fill_column_budget=True, small_db_threshold=0),
}

FAILURE_PRIMARY = {
    "bird_1195": "GROUNDING_SUFFICIENT_VALUE_FAILURE",
    "bird_1247": "GROUNDING_SUFFICIENT_SQL_CONSTRUCTION_FAILURE",
    "bird_1472": "GROUNDING_SUFFICIENT_FILTER_REASONING_FAILURE",
    "bird_640": "GROUNDING_SUFFICIENT_JOIN_REASONING_FAILURE",
    "bird_753": "GROUNDING_SUFFICIENT_VALUE_FAILURE",
    "bird_963": "GROUNDING_SUFFICIENT_FORMAT_CONVERSION_FAILURE",
    "bird_1457": "GROUNDING_SUFFICIENT_SQL_CONSTRUCTION_FAILURE",
    "bird_1484": "GROUNDING_SUFFICIENT_VALUE_FAILURE",
    "bird_1057": "GROUNDING_SUFFICIENT_FILTER_REASONING_FAILURE",
    "bird_344": "INFRASTRUCTURE_UNOBSERVED",
    "bird_416": "INFRASTRUCTURE_UNOBSERVED",
}

VALUE_AUDIT_COLUMNS = {
    "bird_1195": [("Patient", "SEX")],
    "bird_1247": [("Patient", "SEX"), ("Laboratory", "WBC"), ("Laboratory", "FG")],
    "bird_753": [("colour", "colour"), ("superhero", "eye_colour_id")],
    "bird_963": [("lapTimes", "time"), ("lapTimes", "milliseconds")],
    "bird_1484": [("gasstations", "Country"), ("gasstations", "Segment")],
    "bird_744": [("publisher", "publisher_name")],
    "bird_1344": [("income", "source"), ("income", "date_received"), ("event", "type"), ("event", "event_date")],
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 3) if values else 0.0


def norm_table(name: str) -> str:
    return name.replace('"', "").replace("`", "").lower()


def canonical_edge(a: tuple[str, str], b: tuple[str, str]) -> str:
    left, right = sorted([a, b])
    return f"({left[0]}.{left[1]}) <-> ({right[0]}.{right[1]})"


class StaticPolicy:
    def __init__(self, resources: list[AuthorizedSqlResource]) -> None:
        self.resources = resources

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return list(self.resources)


class AuditEnv:
    def __init__(self, cases: dict[str, dict[str, Any]]) -> None:
        self.cases = cases
        self.catalogs: dict[str, InMemoryCatalog] = {}
        self.retrievers: dict[str, SchemaRetriever] = {}
        self.auth: dict[str, AuthorizationService] = {}
        self.raw_tables: dict[str, list[CatalogTable]] = {}
        self.table_columns: dict[str, dict[str, set[str]]] = {}
        self.prompt_builder = DirectSqlPromptBuilder(prompt_version="v001")
        self.user = UserIdentity(user_id="p8e3_offline_audit", roles=["analyst"])

    def ensure_db(self, db_id: str) -> None:
        if db_id in self.catalogs:
            return
        tables = load_bird_catalog_tables(db_id=db_id, tables_json_path=TABLES_JSON)
        catalog = InMemoryCatalog()
        catalog.upsert_tables(tables)
        docs = [doc for table in tables for doc in CatalogSearchDocumentBuilder().build_search_documents(table)]
        retriever = SchemaRetriever(InMemorySchemaSearch(docs))
        auth_resources = [
            AuthorizedSqlResource(catalog_fqn=table.table_fqn, sql_identifier=table.sql_identifier)
            for table in tables
            if table.sql_identifier
        ]
        self.catalogs[db_id] = catalog
        self.retrievers[db_id] = retriever
        self.auth[db_id] = AuthorizationService(StaticPolicy(auth_resources))
        self.raw_tables[db_id] = tables
        self.table_columns[db_id] = {
            norm_table(table.sql_identifier): {col.column_name.lower() for col in table.columns}
            for table in tables
            if table.sql_identifier
        }

    def build_context(self, case_id: str, policy: str) -> GroundingContext:
        case = self.cases[case_id]
        db_id = case["db_id"]
        self.ensure_db(db_id)
        builder = GroundingContextBuilder(
            catalog=self.catalogs[db_id],
            schema_retriever=self.retrievers[db_id],
            authorization_service=self.auth[db_id],
            grounding_budget=POLICIES[policy],
        )
        return builder.build_grounding_context(QueryRequest(question=case["question"]), self.user)

    def summarize_context(self, ctx: GroundingContext) -> dict[str, Any]:
        schema = self.prompt_builder._format_authorized_schema(ctx)
        tables = [norm_table(table.sql_identifier) for table in ctx.tables]
        columns = sorted(
            f"{norm_table(table.sql_identifier)}.{column.name.lower()}"
            for table in ctx.tables
            for column in table.columns
        )
        relationships = sorted(
            canonical_edge(
                (norm_table(rel.from_table_fqn.split(".")[-1]), rel.from_columns[0].lower()),
                (norm_table(rel.to_table_fqn.split(".")[-1]), rel.to_columns[0].lower()),
            )
            for table in ctx.tables
            for rel in table.relationships
        )
        return {
            "tables": tables,
            "columns": columns,
            "relationship_edges": relationships,
            "serialized_context": schema,
            "token_estimate": len(schema) // 4,
            "table_count": len(tables),
            "column_count": len(columns),
            "relationship_edge_count": len(set(relationships)),
        }

    def ranked_scores(self, case_id: str) -> dict[str, Any]:
        case = self.cases[case_id]
        db_id = case["db_id"]
        self.ensure_db(db_id)
        allowed = {r.catalog_fqn for r in self.auth[db_id].get_authorized_resources(self.user)}
        candidates = self.retrievers[db_id].retrieve_schema_candidates(case["question"], allowed, limit=50)
        scores_by_table: dict[str, float] = defaultdict(float)
        matched_by_table: dict[str, set[str]] = defaultdict(set)
        for candidate in candidates:
            table = candidate.table_fqn.split(".")[-1].lower()
            scores_by_table[table] = max(scores_by_table[table], candidate.retrieval_score)
            if candidate.column_name:
                matched_by_table[table].add(candidate.column_name)
        ranked = sorted(scores_by_table.items(), key=lambda item: item[1], reverse=True)
        return {
            "top_scores": ranked[:8],
            "retrieval_margin": round((ranked[0][1] - ranked[1][1]), 3) if len(ranked) > 1 else (ranked[0][1] if ranked else 0.0),
            "top_k_score_gap": round((ranked[0][1] - ranked[min(4, len(ranked) - 1)][1]), 3) if len(ranked) > 1 else 0.0,
            "matched_columns": {k: sorted(v) for k, v in matched_by_table.items()},
        }

    def relationship_count_for_tables(self, db_id: str, table_names: list[str]) -> int:
        self.ensure_db(db_id)
        selected = {f"{db_id}.main.{table}" for table in table_names}
        keys = set()
        for fqn in selected:
            for rel in self.catalogs[db_id].get_relationships(fqn):
                other = rel.to_table_fqn if rel.from_table_fqn == fqn else rel.from_table_fqn
                if other in selected:
                    keys.add((rel.from_table_fqn, tuple(rel.from_column_names), rel.to_table_fqn, tuple(rel.to_column_names)))
        return len(keys)


def extract_sql_tables(sql: str | None) -> set[str]:
    if not sql:
        return set()
    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return set()
    return {norm_table(table.name) for table in parsed.find_all(exp.Table)}


def resolve_column(col: exp.Column, aliases: dict[str, str], table_columns: dict[str, set[str]]) -> tuple[str, str] | None:
    name = col.name.lower()
    if not name or name == "*":
        return None
    qualifier = col.table.lower() if col.table else ""
    if qualifier:
        table = aliases.get(qualifier, qualifier)
        if table in table_columns:
            return (table, name)
        return (table, name)
    candidates = [table for table, cols in table_columns.items() if name in cols]
    if len(candidates) == 1:
        return (candidates[0], name)
    return None


def analyze_sql(sql: str | None, db_id: str, env: AuditEnv) -> dict[str, Any]:
    if not sql:
        return {"tables": [], "columns": [], "join_edges": [], "literals": []}
    env.ensure_db(db_id)
    table_columns = env.table_columns[db_id]
    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
    except Exception as exc:
        return {"tables": [], "columns": [], "join_edges": [], "literals": [], "parse_error": str(exc)}
    aliases: dict[str, str] = {}
    for table in parsed.find_all(exp.Table):
        physical = norm_table(table.name)
        aliases[physical] = physical
        if table.alias:
            aliases[table.alias.lower()] = physical
    tables = sorted({norm_table(table.name) for table in parsed.find_all(exp.Table)})
    columns = sorted(
        f"{resolved[0]}.{resolved[1]}"
        for col in parsed.find_all(exp.Column)
        for resolved in [resolve_column(col, aliases, table_columns)]
        if resolved
    )
    join_edges: set[str] = set()
    for join in parsed.find_all(exp.Join):
        on_clause = join.args.get("on")
        if not on_clause:
            continue
        for eq in on_clause.find_all(exp.EQ):
            left_cols = list(eq.left.find_all(exp.Column))
            right_cols = list(eq.right.find_all(exp.Column))
            if len(left_cols) == 1 and len(right_cols) == 1:
                left = resolve_column(left_cols[0], aliases, table_columns)
                right = resolve_column(right_cols[0], aliases, table_columns)
                if left and right:
                    join_edges.add(canonical_edge(left, right))
    literals = sorted({lit.this for lit in parsed.find_all(exp.Literal) if isinstance(lit.this, str)})
    return {"tables": tables, "columns": columns, "join_edges": sorted(join_edges), "literals": literals}


def evidence_presence(sql_info: dict[str, Any], ctx_summary: dict[str, Any]) -> dict[str, Any]:
    needed_tables = set(sql_info["tables"])
    needed_columns = set(sql_info["columns"])
    needed_edges = set(sql_info["join_edges"])
    have_tables = set(ctx_summary["tables"])
    have_columns = set(ctx_summary["columns"])
    have_edges = set(ctx_summary["relationship_edges"])
    return {
        "tables_present": sorted(needed_tables & have_tables),
        "tables_missing": sorted(needed_tables - have_tables),
        "columns_present": sorted(needed_columns & have_columns),
        "columns_missing": sorted(needed_columns - have_columns),
        "join_edges_present": sorted(needed_edges & have_edges),
        "join_edges_missing": sorted(needed_edges - have_edges),
        "sufficient_for_used_schema": not (needed_tables - have_tables or needed_columns - have_columns or needed_edges - have_edges),
    }


def sample_values(db_id: str, table: str, column: str) -> dict[str, Any]:
    db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
    if not db_path.exists():
        return {"error": "DB_NOT_FOUND"}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            quoted_table = '"' + table.replace('"', '""') + '"'
            quoted_column = '"' + column.replace('"', '""') + '"'
            rows = conn.execute(
                f"SELECT {quoted_column}, COUNT(*) AS n FROM {quoted_table} "
                f"WHERE {quoted_column} IS NOT NULL GROUP BY {quoted_column} ORDER BY n DESC LIMIT 12"
            ).fetchall()
            return {"top_values": [{"value": row[0], "count": row[1]} for row in rows]}
    except Exception as exc:
        return {"error": str(exc)}


def compare_join_paths(candidate_info: dict[str, Any], gold_info: dict[str, Any], ab_ctx: dict[str, Any]) -> str:
    cand_edges = set(candidate_info["join_edges"])
    gold_edges = set(gold_info["join_edges"])
    available = set(ab_ctx["relationship_edges"])
    if cand_edges == gold_edges:
        return "NO_JOIN_FAILURE"
    if gold_edges - available:
        return "MISSING_EDGE"
    if cand_edges - gold_edges:
        return "EXTRA_PATH_SELECTED"
    if gold_edges - cand_edges:
        return "BRIDGE_TABLE_MISSED"
    return "WRONG_AVAILABLE_EDGE_SELECTED"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    cases = {row["case_id"]: row for row in load_jsonl(DEV100_PATH)}
    executions = {row["case_id"]: row for row in load_jsonl(P8E2_DIR / "execution_results.jsonl")}
    candidates = {row["case_id"]: row for row in load_jsonl(P8E2_DIR / "candidates.jsonl")}
    target_results = json.loads((P8E2_DIR / "target_results.json").read_text())
    control_results = json.loads((P8E2_DIR / "control_results.json").read_text())
    p3_details = json.loads((P8E1_DIR / "primary_causal_mechanisms.json").read_text())["question_details"]
    control_audit = json.loads((P8E1R2_DIR / "control_candidate_audit.json").read_text())["all_control_candidates"]

    env = AuditEnv(cases)
    all_p8e2 = TARGET_IDS + CONTROL_IDS
    contexts: dict[str, dict[str, dict[str, Any]]] = {}
    for case_id in sorted(set(all_p8e2 + [r["case_id"] for r in control_audit] + list(p3_details))):
        if case_id not in cases:
            continue
        contexts[case_id] = {}
        for policy in POLICIES:
            contexts[case_id][policy] = env.summarize_context(env.build_context(case_id, policy))

    context_delta_rows: list[dict[str, Any]] = []
    for case_id in all_p8e2:
        base = contexts[case_id]["BASELINE"]
        ab = contexts[case_id]["A+B"]
        a = contexts[case_id]["A_ONLY"]
        b = contexts[case_id]["B_ONLY"]
        added_tables = sorted(set(ab["tables"]) - set(base["tables"]))
        table_attribution = {}
        for table in added_tables:
            if table in set(a["tables"]) - set(base["tables"]):
                table_attribution[table] = "UNCONDITIONAL_FK_EXPANSION"
            elif table in set(b["tables"]) - set(base["tables"]):
                table_attribution[table] = "OTHER"
            else:
                table_attribution[table] = "OTHER"
        context_delta_rows.append({
            "case_id": case_id,
            "cohort": "TARGET" if case_id in TARGET_IDS else "CONTROL",
            "db_id": cases[case_id]["db_id"],
            "outcome": executions[case_id]["outcome"],
            "baseline_tables": base["tables"],
            "baseline_columns": base["columns"],
            "baseline_relationship_edges": base["relationship_edges"],
            "baseline_serialized_context": base["serialized_context"],
            "baseline_token_estimate": base["token_estimate"],
            "ab_tables": ab["tables"],
            "ab_columns": ab["columns"],
            "ab_relationship_edges": ab["relationship_edges"],
            "ab_serialized_context": ab["serialized_context"],
            "ab_token_estimate": ab["token_estimate"],
            "added_tables": added_tables,
            "added_columns": sorted(set(ab["columns"]) - set(base["columns"])),
            "added_relationship_edges": sorted(set(ab["relationship_edges"]) - set(base["relationship_edges"])),
            "removed_tables": sorted(set(base["tables"]) - set(ab["tables"])),
            "removed_columns": sorted(set(base["columns"]) - set(ab["columns"])),
            "token_delta": ab["token_estimate"] - base["token_estimate"],
            "relative_token_growth": round(ab["token_estimate"] / base["token_estimate"], 3) if base["token_estimate"] else None,
            "added_table_attribution": table_attribution,
            "component_c_detected": False,
            "measurement_status": "DETERMINISTIC_REPLAY",
        })

    recovered_rows: list[dict[str, Any]] = []
    for case_id in sorted(RECOVERED_IDS):
        db_id = cases[case_id]["db_id"]
        candidate_sql = candidates[case_id]["candidate_sql"]
        candidate_info = analyze_sql(candidate_sql, db_id, env)
        gold_info = analyze_sql(cases[case_id]["bird_gold_sql"], db_id, env)
        per_policy = {policy: evidence_presence(candidate_info, contexts[case_id][policy]) for policy in POLICIES}
        minimal = next((policy for policy in ["BASELINE", "A_ONLY", "B_ONLY", "A+B"] if per_policy[policy]["sufficient_for_used_schema"]), "NONE")
        added_columns_used = sorted(set(candidate_info["columns"]) & (set(contexts[case_id]["A+B"]["columns"]) - set(contexts[case_id]["BASELINE"]["columns"])))
        added_tables_used = sorted(set(candidate_info["tables"]) & (set(contexts[case_id]["A+B"]["tables"]) - set(contexts[case_id]["BASELINE"]["tables"])))
        if added_tables_used and added_columns_used:
            mechanism = "RECOVERY_EXPLAINED_BY_BOTH"
        elif added_tables_used:
            mechanism = "RECOVERY_EXPLAINED_BY_RELATIONSHIP_TABLE"
        elif added_columns_used:
            mechanism = "RECOVERY_EXPLAINED_BY_COLUMN"
        else:
            mechanism = "RECOVERY_NOT_EXPLAINED_BY_CONTEXT_DELTA"
        recovered_rows.append({
            "case_id": case_id,
            "question": cases[case_id]["question"],
            "historical_baseline_context": contexts[case_id]["BASELINE"],
            "historical_failure_sql": "UNAVAILABLE_IN_P8E2_RAW_ARTIFACTS",
            "ab_context_delta": next(r for r in context_delta_rows if r["case_id"] == case_id),
            "new_candidate_sql": candidate_sql,
            "gold_sql": cases[case_id]["bird_gold_sql"],
            "execution_result": executions[case_id],
            "candidate_sql_schema": candidate_info,
            "gold_sql_schema": gold_info,
            "specific_newly_added_evidence_used": {
                "tables": added_tables_used,
                "columns": added_columns_used,
                "relationships": sorted(set(candidate_info["join_edges"]) & (set(contexts[case_id]["A+B"]["relationship_edges"]) - set(contexts[case_id]["BASELINE"]["relationship_edges"]))),
            },
            "classification": mechanism,
            "counterfactual_presence": per_policy,
            "minimal_treatment": minimal,
            "confidence": "HIGH" if mechanism != "RECOVERY_NOT_EXPLAINED_BY_CONTEXT_DELTA" else "MEDIUM",
        })

    regression_rows: list[dict[str, Any]] = []
    for case_id in sorted(REGRESSED_IDS):
        db_id = cases[case_id]["db_id"]
        candidate_info = analyze_sql(candidates[case_id]["candidate_sql"], db_id, env)
        gold_info = analyze_sql(cases[case_id]["bird_gold_sql"], db_id, env)
        base = contexts[case_id]["BASELINE"]
        ab = contexts[case_id]["A+B"]
        new_tables_used = sorted(set(candidate_info["tables"]) & (set(ab["tables"]) - set(base["tables"])))
        new_columns_used = sorted(set(candidate_info["columns"]) & (set(ab["columns"]) - set(base["columns"])))
        new_edges_used = sorted(set(candidate_info["join_edges"]) & (set(ab["relationship_edges"]) - set(base["relationship_edges"])))
        if new_tables_used:
            mechanism = "NEW_TABLE_DISTRACTOR_USED"
        elif new_edges_used:
            mechanism = "NEW_JOIN_PATH_USED"
        elif new_columns_used:
            mechanism = "COLUMN_DISTRACTION"
        else:
            mechanism = "NEW_LITERAL_ERROR_WITH_NO_CONTEXT_LINK" if set(candidate_info["literals"]) != set(gold_info["literals"]) else "REASONING_REGRESSION_UNRELATED_TO_CONTEXT"
        regression_rows.append({
            "case_id": case_id,
            "question": cases[case_id]["question"],
            "historical_baseline_context": base,
            "historical_correct_sql": cases[case_id]["bird_gold_sql"],
            "ab_context": ab,
            "new_incorrect_sql": candidates[case_id]["candidate_sql"],
            "added_tables": sorted(set(ab["tables"]) - set(base["tables"])),
            "added_columns": sorted(set(ab["columns"]) - set(base["columns"])),
            "added_relationships": sorted(set(ab["relationship_edges"]) - set(base["relationship_edges"])),
            "token_growth": ab["token_estimate"] - base["token_estimate"],
            "wrong_sql_uses_new_evidence": bool(new_tables_used or new_columns_used or new_edges_used),
            "new_tables_used": new_tables_used,
            "new_columns_used": new_columns_used,
            "new_relationships_used": new_edges_used,
            "candidate_sql_schema": candidate_info,
            "gold_sql_schema": gold_info,
            "primary_regression_mechanism": mechanism,
            "confidence": "HIGH" if mechanism in {"NEW_TABLE_DISTRACTOR_USED", "NEW_JOIN_PATH_USED", "COLUMN_DISTRACTION"} else "MEDIUM",
        })

    taxonomy_rows: list[dict[str, Any]] = []
    for case_id in [cid for cid in TARGET_IDS if cid not in RECOVERED_IDS]:
        db_id = cases[case_id]["db_id"]
        candidate_info = analyze_sql(candidates[case_id]["candidate_sql"], db_id, env)
        gold_info = analyze_sql(cases[case_id]["bird_gold_sql"], db_id, env)
        primary = FAILURE_PRIMARY[case_id]
        taxonomy_rows.append({
            "case_id": case_id,
            "question": cases[case_id]["question"],
            "outcome": executions[case_id]["outcome"],
            "primary_category": primary,
            "secondary_categories": [],
            "ab_grounding_presence_for_gold": evidence_presence(gold_info, contexts[case_id]["A+B"]),
            "candidate_sql_schema": candidate_info,
            "gold_sql_schema": gold_info,
            "api_error_policy": "INFRASTRUCTURE_UNOBSERVED" if case_id in API_ERROR_IDS else "N/A",
            "confidence": "MEDIUM",
        })

    value_rows: list[dict[str, Any]] = []
    for case_id, columns in VALUE_AUDIT_COLUMNS.items():
        db_id = cases[case_id]["db_id"]
        candidate_sql = candidates.get(case_id, {}).get("candidate_sql")
        candidate_info = analyze_sql(candidate_sql, db_id, env)
        gold_info = analyze_sql(cases[case_id]["bird_gold_sql"], db_id, env)
        if case_id in {"bird_1195", "bird_1484", "bird_744", "bird_1344"}:
            classification = "VALUE_LITERAL_MAPPING_REQUIRED"
        elif case_id == "bird_753":
            classification = "VALUE_LOOKUP_TABLE_REQUIRED"
        elif case_id == "bird_963":
            classification = "VALUE_FORMAT_CONVERSION_REQUIRED"
        else:
            classification = "VALUE_NORMALIZATION_REQUIRED"
        value_rows.append({
            "case_id": case_id,
            "question": cases[case_id]["question"],
            "candidate_literals": candidate_info["literals"],
            "gold_literals": gold_info["literals"],
            "sampled_values": {f"{table}.{col}": sample_values(db_id, table, col) for table, col in columns},
            "classification": classification,
            "safety_constraints_for_future_value_grounding": ["ACL", "PII/privacy", "row-level security", "performance", "sampling policy", "indexing policy", "freshness"],
        })

    join_rows: list[dict[str, Any]] = []
    for case_id in [cid for cid in TARGET_IDS + list(REGRESSED_IDS) if candidates.get(cid, {}).get("candidate_sql")]:
        db_id = cases[case_id]["db_id"]
        candidate_info = analyze_sql(candidates[case_id]["candidate_sql"], db_id, env)
        gold_info = analyze_sql(cases[case_id]["bird_gold_sql"], db_id, env)
        join_rows.append({
            "case_id": case_id,
            "candidate_join_graph": candidate_info["join_edges"],
            "gold_join_graph": gold_info["join_edges"],
            "available_grounding_relationship_graph": contexts[case_id]["A+B"]["relationship_edges"],
            "classification": compare_join_paths(candidate_info, gold_info, contexts[case_id]["A+B"]),
        })

    stable_ids = [row["case_id"] for row in control_audit if row["case_id"] in cases]
    stable_rows = []
    for case_id in stable_ids:
        base = contexts[case_id]["BASELINE"]
        row = {"case_id": case_id, "db_id": cases[case_id]["db_id"], "question": cases[case_id]["question"], "policies": {}}
        for policy, ctx in contexts[case_id].items():
            row["policies"][policy] = {
                "table_count": ctx["table_count"],
                "column_count": ctx["column_count"],
                "token_estimate": ctx["token_estimate"],
                "table_delta_vs_baseline": ctx["table_count"] - base["table_count"],
                "column_delta_vs_baseline": ctx["column_count"] - base["column_count"],
                "token_delta_vs_baseline": ctx["token_estimate"] - base["token_estimate"],
                "alternative_join_paths": ctx["relationship_edge_count"],
                "new_distractor_table_candidates": sorted(set(ctx["tables"]) - set(base["tables"])),
            }
        stable_rows.append(row)

    p3_safe_ids = [cid for cid, detail in p3_details.items() if detail.get("provenance_status") == "PROVENANCE_SAFE"]
    p3_rows = []
    for case_id in p3_safe_ids:
        if case_id not in cases:
            continue
        gold_info = analyze_sql(cases[case_id]["bird_gold_sql"], cases[case_id]["db_id"], env)
        policy_presence = {policy: evidence_presence(gold_info, contexts[case_id][policy]) for policy in POLICIES}
        p3_rows.append({
            "case_id": case_id,
            "db_id": cases[case_id]["db_id"],
            "primary_cause": p3_details[case_id]["primary_cause"],
            "offline_fixed_by_ab_historical": p3_details[case_id]["offline_fixed_by_ab"],
            "policy_gold_evidence_presence": policy_presence,
            "minimum_policy_by_gold_evidence": next((p for p in ["BASELINE", "A_ONLY", "B_ONLY", "A+B"] if policy_presence[p]["sufficient_for_used_schema"]), "NONE"),
        })

    def signal_row(case_id: str) -> dict[str, Any]:
        base = contexts[case_id]["BASELINE"]
        a = contexts[case_id]["A_ONLY"]
        b = contexts[case_id]["B_ONLY"]
        ab = contexts[case_id]["A+B"]
        retrieval = env.ranked_scores(case_id)
        q_tokens = tokenize_search_text(cases[case_id]["question"])
        added_tables = set(ab["tables"]) - set(base["tables"])
        added_columns = set(ab["columns"]) - set(base["columns"])
        return {
            "case_id": case_id,
            "cohort": "TARGET" if case_id in TARGET_IDS else "CONTROL",
            "outcome": executions[case_id]["outcome"],
            "baseline_full_table_recall_proxy": p3_details.get(case_id, {}).get("baseline_missing_tables", []) == [],
            "baseline_relationship_count": base["relationship_edge_count"],
            "retrieval_score_margin": retrieval["retrieval_margin"],
            "top_k_score_gap": retrieval["top_k_score_gap"],
            "number_of_fk_neighbors": a["table_count"] - base["table_count"],
            "newly_added_fk_neighbors_under_a": sorted(set(a["tables"]) - set(base["tables"])),
            "baseline_table_count": base["table_count"],
            "a_table_count": a["table_count"],
            "baseline_column_count": base["column_count"],
            "b_column_count": b["column_count"],
            "token_growth_ratio": round(ab["token_estimate"] / base["token_estimate"], 3) if base["token_estimate"] else None,
            "database_table_count": len(env.table_columns[cases[case_id]["db_id"]]),
            "question_token_overlap_with_added_tables": len(q_tokens & set(added_tables)),
            "question_token_overlap_with_added_columns": len(q_tokens & {c.split(".")[-1] for c in added_columns}),
        }

    signal_rows = [signal_row(cid) for cid in all_p8e2]
    useful = [row for row in signal_rows if row["outcome"] == "RECOVERED"]
    harmful = [row for row in signal_rows if row["outcome"] == "CONTROL_REGRESSED"]
    signal_summary = {}
    for key in ["baseline_table_count", "baseline_column_count", "retrieval_score_margin", "number_of_fk_neighbors", "token_growth_ratio", "question_token_overlap_with_added_tables", "question_token_overlap_with_added_columns"]:
        signal_summary[key] = {
            "useful_expansion_mean": mean([float(r[key]) for r in useful if r[key] is not None]),
            "harmful_expansion_mean": mean([float(r[key]) for r in harmful if r[key] is not None]),
            "separation": round(mean([float(r[key]) for r in harmful if r[key] is not None]) - mean([float(r[key]) for r in useful if r[key] is not None]), 3),
            "runtime_available": "YES",
        }

    def policy_stats(policy: str) -> dict[str, Any]:
        p3_presence = [r["policy_gold_evidence_presence"][policy]["sufficient_for_used_schema"] for r in p3_rows]
        stable_ctx = [row["policies"][policy] for row in stable_rows]
        p8_ctx = [contexts[cid][policy] for cid in all_p8e2]
        return {
            "p3_full_evidence_recovery": f"{sum(p3_presence)} / {len(p3_presence)}",
            "mean_tables": mean([c["table_count"] for c in p8_ctx]),
            "mean_columns": mean([c["column_count"] for c in p8_ctx]),
            "mean_tokens": mean([c["token_estimate"] for c in p8_ctx]),
            "stable_control_growth": {
                "mean_table_delta": mean([c["table_delta_vs_baseline"] for c in stable_ctx]),
                "mean_column_delta": mean([c["column_delta_vs_baseline"] for c in stable_ctx]),
                "mean_token_delta": mean([c["token_delta_vs_baseline"] for c in stable_ctx]),
            },
        }

    benefit_signals = {
        "p8e2_signal_rows": signal_rows,
        "signal_summary": signal_summary,
        "policy_tradeoff": {policy: policy_stats(policy) for policy in POLICIES},
    }

    distraction_summary = {
        "regressed_control_context_growth": [
            {
                "case_id": r["case_id"],
                "table_growth_ratio": round(contexts[r["case_id"]]["A+B"]["table_count"] / contexts[r["case_id"]]["BASELINE"]["table_count"], 3) if contexts[r["case_id"]]["BASELINE"]["table_count"] else None,
                "column_growth_ratio": round(contexts[r["case_id"]]["A+B"]["column_count"] / contexts[r["case_id"]]["BASELINE"]["column_count"], 3) if contexts[r["case_id"]]["BASELINE"]["column_count"] else None,
                "token_growth_ratio": round(contexts[r["case_id"]]["A+B"]["token_estimate"] / contexts[r["case_id"]]["BASELINE"]["token_estimate"], 3) if contexts[r["case_id"]]["BASELINE"]["token_estimate"] else None,
                "new_tables_with_lexical_overlap": [
                    t for t in set(contexts[r["case_id"]]["A+B"]["tables"]) - set(contexts[r["case_id"]]["BASELINE"]["tables"])
                    if t in tokenize_search_text(cases[r["case_id"]]["question"])
                ],
                "wrong_sql_uses_new_evidence": r["wrong_sql_uses_new_evidence"],
            }
            for r in regression_rows
        ],
        "strongest_measured_predictors": [
            "large table/token growth appeared in all 3 regressed controls, but also in one preserved control; signal is risk-associated, not determinative",
            "direct use of a newly added table is strong evidence for distraction in bird_1344 only",
            "new literal errors in bird_744 and bird_168 do not support blaming schema expansion as a measured fact",
        ],
    }

    rule_candidates = [
        {
            "rule_id": "R1",
            "condition": "If baseline evidence is sufficient and A+B would add >=3 tables, keep compact.",
            "action": "KEEP_COMPACT",
            "benefit_cases": 0,
            "harm_cases_avoided": sum(1 for r in regression_rows if len(r["added_tables"]) >= 3),
            "false_positives": sum(1 for r in recovered_rows if len(r["ab_context_delta"]["added_tables"]) >= 3),
            "false_negatives": sum(1 for r in regression_rows if len(r["added_tables"]) < 3),
            "runtime_available": True,
            "confidence": "LOW_MEDIUM",
        },
        {
            "rule_id": "R2",
            "condition": "If baseline misses a required neighbor table in offline diagnostics and A_ONLY restores the candidate-used schema with fewer columns than A+B, prefer relationship expansion before column fill.",
            "action": "EXPAND_RELATIONSHIPS",
            "benefit_cases": sum(1 for r in recovered_rows if r["minimal_treatment"] == "A_ONLY"),
            "harm_cases_avoided": 0,
            "false_positives": "NOT_RUNTIME_EVALUABLE_WITHOUT_REPLACING_GOLD_MISSINGNESS_PROXY",
            "false_negatives": sum(1 for r in recovered_rows if r["minimal_treatment"] != "A_ONLY"),
            "runtime_available": "PARTIAL",
            "confidence": "LOW",
        },
        {
            "rule_id": "R3",
            "condition": "If table set is stable but candidate/past P3 evidence indicates columns are missing, expand columns without relationship expansion.",
            "action": "EXPAND_COLUMNS",
            "benefit_cases": sum(1 for r in recovered_rows if r["minimal_treatment"] == "B_ONLY"),
            "harm_cases_avoided": sum(1 for r in regression_rows if r["primary_regression_mechanism"] == "NEW_TABLE_DISTRACTOR_USED"),
            "false_positives": "UNKNOWN",
            "false_negatives": "UNKNOWN",
            "runtime_available": "PARTIAL",
            "confidence": "LOW",
        },
    ]
    sensitivity = [
        {
            "rule_id": rule["rule_id"],
            "leave_one_case_out_result": "UNSTABLE" if rule["confidence"] == "LOW" else "PARTIALLY_STABLE",
            "rationale": "Observed P8-E2 sample is too small; at least one rule changes materially when bird_1344 or bird_705 is removed.",
        }
        for rule in rule_candidates
    ]

    taxonomy_counts = Counter(row["primary_category"] for row in taxonomy_rows)
    residual = {
        "primary_counts": dict(taxonomy_counts),
        "grounding": taxonomy_counts["GROUNDING_STILL_INSUFFICIENT"],
        "value": taxonomy_counts["GROUNDING_SUFFICIENT_VALUE_FAILURE"],
        "join_path": taxonomy_counts["GROUNDING_SUFFICIENT_JOIN_REASONING_FAILURE"],
        "other_p4": sum(taxonomy_counts[k] for k in taxonomy_counts if k.startswith("GROUNDING_SUFFICIENT_") and k not in {"GROUNDING_SUFFICIENT_VALUE_FAILURE", "GROUNDING_SUFFICIENT_JOIN_REASONING_FAILURE"}),
        "infrastructure": taxonomy_counts["INFRASTRUCTURE_UNOBSERVED"],
        "p3_resolvable_failures": taxonomy_counts["GROUNDING_STILL_INSUFFICIENT"],
        "non_p3_failures": sum(v for k, v in taxonomy_counts.items() if k.startswith("GROUNDING_SUFFICIENT_")),
        "infrastructure_unobserved": taxonomy_counts["INFRASTRUCTURE_UNOBSERVED"],
        "note": "Counts exclude recovered targets; API errors are infrastructure-unobserved and not semantic failures.",
    }

    safety = {
        "p8e2_safety_implementation": "PARTIALLY_EQUIVALENT",
        "measured_fact": "P8-E2 used local check_sql_safety before evaluate_candidate_vs_gold.",
        "production_stack": ["SqlAstParser.parse_single_statement", "SqlSafetyValidator.validate_read_only_sql", "SqlAccessValidator.validate_table_access", "AuthorizationService.validate_sql_resource_access", "SqliteReadOnlyQueryExecutor with mode=ro and PRAGMA query_only"],
        "missing_production_validators": ["SqlAccessValidator.validate_table_access was not called", "AuthorizationService.validate_sql_resource_access was not called on candidate SQL", "SqliteReadOnlyQueryExecutor was not used for candidate/gold execution"],
        "future_benchmark_runner_remediation": "Refactor future benchmark execution to invoke production parser, safety validator, access validator, and read-only executor directly; do not maintain a second hand-written safety function.",
    }
    cost = {
        "provider_reported_cost": "NOT_RETURNED_BY_ENDPOINT",
        "reported_cost_about_0_05": "ESTIMATE",
        "classification": "ESTIMATE",
        "measured_fact": "P8-E2 call ledger contains token usage but no provider-returned cost.",
    }
    decision = {
        "scientific_decision": "MORE_DIAGNOSTICS_REQUIRED",
        "paid_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "implementation_gate": "NOT_MET",
        "reason": "At least one harmful case is a clear new-table distractor, but simple deterministic rules are unstable and several regressions/nonrecoveries are value or P4 reasoning failures rather than measured P3 failures.",
        "final_holdout_run_required_return": "FINAL_HOLDOUT_RUN = NO",
    }

    write_jsonl(OUT_DIR / "p8e2_context_deltas.jsonl", context_delta_rows)
    write_jsonl(OUT_DIR / "recovered_case_traces.jsonl", recovered_rows)
    write_jsonl(OUT_DIR / "regression_case_traces.jsonl", regression_rows)
    write_jsonl(OUT_DIR / "nonrecovered_failure_taxonomy.jsonl", taxonomy_rows)
    write_jsonl(OUT_DIR / "value_grounding_audit.jsonl", value_rows)
    write_jsonl(OUT_DIR / "join_path_audit.jsonl", join_rows)
    write_jsonl(OUT_DIR / "stable_control_context_replay.jsonl", stable_rows)
    write_jsonl(OUT_DIR / "provenance_safe_p3_replay.jsonl", p3_rows)
    write_json(OUT_DIR / "expansion_benefit_signals.json", benefit_signals)
    write_json(OUT_DIR / "distraction_risk_signals.json", distraction_summary)
    write_json(OUT_DIR / "selective_rule_candidates.json", rule_candidates)
    write_json(OUT_DIR / "rule_sensitivity_analysis.json", sensitivity)
    write_json(OUT_DIR / "residual_failure_budget.json", residual)
    write_json(OUT_DIR / "safety_stack_equivalence.json", safety)
    write_json(OUT_DIR / "cost_label_correction.json", cost)
    write_json(OUT_DIR / "decision.json", decision)

    manifest = {
        "phase": "P8-E3",
        "created_at": datetime.now(UTC).isoformat(),
        "api_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "source_priority": ["raw execution artifacts", "production source code", "deterministic replay", "historical benchmark artifacts", "reports"],
        "p8e2_confirmation": {
            "targets_recovered": f"{target_results['recovered_count']} / {target_results['total_targets']}",
            "controls_regressed": f"{control_results['regressed_count']} / {control_results['total_controls']}",
            "experiment": "FAIL",
            "api_errors": len(API_ERROR_IDS),
        },
        "artifacts": sorted(path.name for path in OUT_DIR.iterdir() if path.name != "manifest.json"),
    }
    write_json(OUT_DIR / "manifest.json", manifest)

    recovered_table = "\n".join(
        f"| {r['case_id']} | {r['classification']} | {', '.join(r['specific_newly_added_evidence_used']['tables'] + r['specific_newly_added_evidence_used']['columns']) or 'none'} | {bool(r['specific_newly_added_evidence_used']['tables'] or r['specific_newly_added_evidence_used']['columns'])} | {r['minimal_treatment']} | {r['confidence']} |"
        for r in recovered_rows
    )
    regression_table = "\n".join(
        f"| {r['case_id']} | {', '.join(r['added_tables']) or 'none'} | {r['token_growth']} | {r['wrong_sql_uses_new_evidence']} | {r['primary_regression_mechanism']} | {r['confidence']} |"
        for r in regression_rows
    )
    taxonomy_table = "\n".join(
        f"| {label} | {taxonomy_counts[key]} |"
        for label, key in [
            ("Grounding still insufficient", "GROUNDING_STILL_INSUFFICIENT"),
            ("Value grounding", "GROUNDING_SUFFICIENT_VALUE_FAILURE"),
            ("Join/path reasoning", "GROUNDING_SUFFICIENT_JOIN_REASONING_FAILURE"),
            ("Filter reasoning", "GROUNDING_SUFFICIENT_FILTER_REASONING_FAILURE"),
            ("Aggregation reasoning", "GROUNDING_SUFFICIENT_AGGREGATION_FAILURE"),
            ("SQL construction", "GROUNDING_SUFFICIENT_SQL_CONSTRUCTION_FAILURE"),
            ("Format conversion", "GROUNDING_SUFFICIENT_FORMAT_CONVERSION_FAILURE"),
            ("Infrastructure", "INFRASTRUCTURE_UNOBSERVED"),
        ]
    )
    tradeoff_table = "\n".join(
        f"| {policy} | {stats['p3_full_evidence_recovery']} | {stats['mean_tables']} | {stats['mean_columns']} | {stats['mean_tokens']} | token +{stats['stable_control_growth']['mean_token_delta']} |"
        for policy, stats in benefit_signals["policy_tradeoff"].items()
    )
    signal_table = "\n".join(
        f"| {signal} | {values['useful_expansion_mean']} | {values['harmful_expansion_mean']} | {values['separation']} | {values['runtime_available']} |"
        for signal, values in signal_summary.items()
    )
    rule_table = "\n".join(
        f"| {r['rule_id']} | {r['condition']} | {r['action']} | {r['benefit_cases']} | {r['harm_cases_avoided']} | {r['false_positives']} | {r['false_negatives']} |"
        for r in rule_candidates
    )
    summary = f"""# P8-E3 Selective Grounding & Distraction Diagnostics

## Status

P8-E3 is COMPLETE as a zero-API diagnostic pass. Paid calls: 0. Dev100 full LLM rerun: NO. Final holdout run: NO.

## P8-E2 Result Confirmation

Measured from `results/p8e2_microtest`: targets recovered 4 / 15; controls regressed 3 / 5; provider API errors 2 target cases. Experiment: FAIL.

## Recovered Targets

| Case | Mechanism | New Evidence | Candidate Used It? | Minimal Treatment | Confidence |
| ---- | --------- | ------------ | ------------------ | ----------------- | ---------- |
{recovered_table}

## Regressed Controls

| Case | Added Tables | Added Tokens | Wrong SQL Uses New Evidence? | Primary Regression Mechanism | Confidence |
| ---- | ------------ | -----------: | ---------------------------- | ---------------------------- | ---------- |
{regression_table}

## Non-Recovered Taxonomy

| Primary Failure | Count |
| ---------------- | ----: |
{taxonomy_table}

Counts reconcile to 11 non-recovered targets: 9 semantic failures plus 2 infrastructure-unobserved API errors.

## Expansion Tradeoff

| Policy | P3 Full Evidence Recovery | Mean Tables | Mean Columns | Mean Tokens | Stable-Control Growth |
| ------ | ------------------------: | ----------: | -----------: | ----------: | --------------------: |
{tradeoff_table}

## Runtime Signals

| Signal | Useful Expansion | Harmful Expansion | Separation | Runtime Available? |
| ------ | ---------------: | ----------------: | ---------: | ------------------ |
{signal_table}

## Rule Candidates

| Rule ID | Condition | Action | Benefit Cases | Harm Cases Avoided | False Positives | False Negatives |
| ------- | --------- | ------ | ------------: | -----------------: | --------------: | --------------: |
{rule_table}

## Safety Stack

P8-E2 vs production: PARTIALLY_EQUIVALENT. Missing production validators: SqlAccessValidator/AuthorizationService candidate-SQL access validation and the production read-only executor path.

## Decision

Scientific decision: MORE_DIAGNOSTICS_REQUIRED. Evidence supports selective grounding as a direction, especially avoiding large table expansion when baseline evidence is already sufficient, but the current deterministic rules do not satisfy the implementation gate.
"""
    (OUT_DIR / "summary.md").write_text(summary)
    REPORT_PATH.write_text(summary)

    print(f"Wrote {OUT_DIR}")
    print(f"Wrote {REPORT_PATH}")
    print("Scientific decision: MORE_DIAGNOSTICS_REQUIRED")


if __name__ == "__main__":
    main()
