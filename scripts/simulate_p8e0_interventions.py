# ruff: noqa: E501
"""Simulate offline Level-0 grounding interventions on target failures and controls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.catalog import CatalogColumn, CatalogForeignKey, CatalogSearchDocumentBuilder, CatalogTable
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import GroundingContext, QueryRequest, TableContext
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.relationship_expander import RelationshipExpander, RelationshipExpansion
from t2s.grounding.retrieval_ranker import RankedTableCandidate
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
DEV100_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "results" / "p8e0_p3_causality_audit"

dev100_cases = {
    c["case_id"]: c
    for c in (json.loads(line_str) for line_str in DEV100_PATH.read_text().splitlines() if line_str.strip())
}
prompt_builder = DirectSqlPromptBuilder()


class AllTablesAccessPolicy:
    def __init__(self, auth_res: list[AuthorizedSqlResource]) -> None:
        self.auth_res = auth_res

    def get_authorized_resources(self, u: UserIdentity) -> list[AuthorizedSqlResource]:
        return list(self.auth_res)


# Target questions (19 missing-table + 1 missing-column)
TARGET_QIDS = [
    "bird_100", "bird_1096", "bird_1098", "bird_1139", "bird_1195",
    "bird_1247", "bird_1256", "bird_1270", "bird_1275", "bird_1281",
    "bird_137", "bird_1472", "bird_1490", "bird_206", "bird_723",
    "bird_740", "bird_792", "bird_93", "bird_933", "bird_753"
]

# Control questions (10 confirmed 3/3 correct questions)
CONTROL_QIDS = [
    "bird_12", "bird_1042", "bird_1344", "bird_1476", "bird_168",
    "bird_213", "bird_356", "bird_549", "bird_732", "bird_1146"
]

db_catalog_tables: dict[str, list[CatalogTable]] = {}
for db in set(c["db_id"] for c in dev100_cases.values()):
    db_catalog_tables[db] = load_bird_catalog_tables(db_id=db, tables_json_path=TABLES_JSON)


# --- Custom Components for Interventions ---


class UnconditionalRelationshipExpander(RelationshipExpander):
    """Expands 1-hop FK relationships without requiring question token match."""

    def expand_one_hop_relationships(
        self,
        question: str,
        ranked_table_candidates: list[RankedTableCandidate],
        allowed_table_fqns: set[str],
        max_hydrated_tables: int,
        max_relationships: int,
    ) -> RelationshipExpansion:
        selected_table_fqns = [candidate.table_fqn for candidate in ranked_table_candidates]
        selected_table_fqn_set = set(selected_table_fqns)
        candidate_table_fqns = selected_table_fqn_set
        relationships: list[CatalogForeignKey] = []
        relationship_keys: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()

        for table_fqn in list(selected_table_fqns):
            for foreign_key in self.catalog.get_relationships(table_fqn):
                if len(relationships) >= max_relationships:
                    break
                related_table_fqn = self._get_related_table_fqn(table_fqn, foreign_key)
                if related_table_fqn not in allowed_table_fqns:
                    continue
                relationship_key = (
                    foreign_key.from_table_fqn,
                    tuple(foreign_key.from_column_names),
                    foreign_key.to_table_fqn,
                    tuple(foreign_key.to_column_names),
                )
                if relationship_key not in relationship_keys:
                    relationship_keys.add(relationship_key)
                    relationships.append(foreign_key)
                if (
                    related_table_fqn not in candidate_table_fqns
                    and len(candidate_table_fqns) < max_hydrated_tables
                ):
                    selected_table_fqns.append(related_table_fqn)
                    candidate_table_fqns.add(related_table_fqn)

        return RelationshipExpansion(
            table_fqns=tuple(selected_table_fqns[:max_hydrated_tables]),
            relationships=tuple(relationships[:max_relationships]),
        )


class BudgetFillingContextBuilder(GroundingContextBuilder):
    """Fills columns up to max_columns_per_table instead of stopping at 3."""

    def _select_columns_for_table(
        self,
        catalog_table: CatalogTable,
        ranked_candidate: RankedTableCandidate | None,
        table_relationships: list[CatalogForeignKey],
        query_tokens: set[str],
        remaining_column_budget: int,
    ) -> list[CatalogColumn]:
        matched_column_names = (
            set(ranked_candidate.matched_column_names) if ranked_candidate else set()
        )
        required_column_names = {
            *catalog_table.primary_key_column_names,
            *[
                column_name
                for relationship in table_relationships
                for column_name in self._relationship_column_names(catalog_table, relationship)
            ],
        }
        scored_columns = [
            (
                self._score_column(
                    catalog_column,
                    query_tokens,
                    matched_column_names,
                    required_column_names,
                ),
                catalog_column.ordinal_position
                if catalog_column.ordinal_position is not None
                else len(catalog_table.columns),
                catalog_column,
            )
            for catalog_column in catalog_table.columns
        ]
        selected_columns: list[CatalogColumn] = []
        selected_column_names: set[str] = set()
        maximum_columns = min(self.grounding_budget.max_columns_per_table, remaining_column_budget)

        # 1. First pass: prioritize required/matched/query-relevant columns
        for _, _, catalog_column in sorted(
            scored_columns,
            key=lambda scored_column: (scored_column[0], -scored_column[1]),
            reverse=True,
        ):
            if len(selected_columns) >= maximum_columns:
                break
            if catalog_column.column_name in selected_column_names:
                continue
            if (
                catalog_column.column_name in required_column_names
                or catalog_column.column_name in matched_column_names
                or self._column_matches_query(catalog_column, query_tokens)
            ):
                selected_columns.append(catalog_column)
                selected_column_names.add(catalog_column.column_name)

        # 2. Second pass: fill remaining table columns up to maximum_columns
        for _, _, catalog_column in sorted(
            scored_columns,
            key=lambda scored_column: (scored_column[0], -scored_column[1]),
            reverse=True,
        ):
            if len(selected_columns) >= maximum_columns:
                break
            if catalog_column.column_name in selected_column_names:
                continue
            selected_columns.append(catalog_column)
            selected_column_names.add(catalog_column.column_name)

        return sorted(
            selected_columns,
            key=lambda column: column.ordinal_position
            if column.ordinal_position is not None
            else 0,
        )


def build_context(
    case: dict[str, Any],
    mode: str,
) -> GroundingContext:
    db_id = case["db_id"]
    cat_tables = db_catalog_tables[db_id]

    # Intervention B & D: Small-DB Full Schema Fallback
    if mode in ("small_db_fallback", "combined") and len(cat_tables) <= 5:
        # Include all tables and all columns for small DBs
        table_contexts: list[TableContext] = []
        for ct in cat_tables:
            from t2s.contracts import ColumnContext
            table_contexts.append(
                TableContext(
                    fqn=ct.table_fqn,
                    sql_identifier=ct.sql_identifier or ct.table_name,
                    description=ct.description,
                    columns=[
                        ColumnContext(
                            name=c.column_name,
                            data_type=c.data_type,
                            description=c.description,
                            is_nullable=c.is_nullable if c.is_nullable is not None else True,
                            is_primary_key=c.is_primary_key or c.column_name in ct.primary_key_column_names,
                        )
                        for c in ct.columns
                    ],
                    relationships=[],
                )
            )
        return GroundingContext(
            scope_id="fallback",
            tables=table_contexts,
            unresolved=[],
            evidence=[],
        )

    # Setup standard components
    catalog = InMemoryCatalog()
    catalog.upsert_tables(cat_tables)
    doc_builder = CatalogSearchDocumentBuilder()
    docs = [doc for t in cat_tables for doc in doc_builder.build_search_documents(t)]
    retriever = SchemaRetriever(InMemorySchemaSearch(docs))
    auth_res = [
        AuthorizedSqlResource(catalog_fqn=t.table_fqn, sql_identifier=t.sql_identifier)
        for t in cat_tables
        if t.sql_identifier
    ]
    auth_srv = AuthorizationService(AllTablesAccessPolicy(auth_res))

    expander: RelationshipExpander
    if mode in ("unconditional_fk", "combined"):
        expander = UnconditionalRelationshipExpander(catalog)
    else:
        expander = RelationshipExpander(catalog)

    builder_cls = BudgetFillingContextBuilder if mode in ("column_fill", "combined") else GroundingContextBuilder
    gb = builder_cls(
        catalog=catalog,
        schema_retriever=retriever,
        authorization_service=auth_srv,
        grounding_budget=GroundingBudget(),
        relationship_expander=expander,
    )

    q_req = QueryRequest(
        question=case["question"],
        target_hint=case.get("evidence") or "",
        database_dialect="sqlite",
    )
    return gb.build_grounding_context(q_req, UserIdentity(user_id="offline_audit"))


def extract_gold_requirements(gold_sql: str) -> tuple[set[str], set[str]]:
    try:
        parsed = sqlglot.parse_one(gold_sql, read="sqlite")
        tables = {t.name.lower() for t in parsed.find_all(exp.Table) if t.name}
        cols = {c.name.lower() for c in parsed.find_all(exp.Column) if c.name}
        return tables, cols
    except Exception:
        return set(), set()


def evaluate_intervention(mode: str) -> dict[str, Any]:
    print(f"\n================ Evaluating Mode: {mode} ================")
    
    # 1. Target questions
    target_results = []
    target_gold_tbl_total = 0
    target_gold_tbl_retrieved = 0
    target_gold_col_total = 0
    target_gold_col_retrieved = 0

    target_table_counts = []
    target_col_counts = []
    target_token_counts = []

    for qid in TARGET_QIDS:
        c = dev100_cases[qid]
        ctx = build_context(c, mode)
        ctx_tbls = {t.sql_identifier.lower() for t in ctx.tables if t.sql_identifier}
        ctx_cols = set()
        for t in ctx.tables:
            for col in t.columns:
                ctx_cols.add(col.name.lower())

        gold_sql = c.get("gold_sql") or c.get("bird_gold_sql") or c["gold"]["sql_original"]
        gold_tbls, gold_cols = extract_gold_requirements(gold_sql)
        
        target_gold_tbl_total += len(gold_tbls)
        target_gold_tbl_retrieved += len(gold_tbls & ctx_tbls)
        target_gold_col_total += len(gold_cols)
        target_gold_col_retrieved += len(gold_cols & ctx_cols)

        tbl_cnt = len(ctx.tables)
        col_cnt = sum(len(t.columns) for t in ctx.tables)
        prompt_str = prompt_builder._format_authorized_schema(ctx)
        est_tokens = len(prompt_str) // 4

        target_table_counts.append(tbl_cnt)
        target_col_counts.append(col_cnt)
        target_token_counts.append(est_tokens)

        target_results.append({
            "case_id": qid,
            "db_id": c["db_id"],
            "gold_tables": sorted(list(gold_tbls)),
            "retrieved_tables": sorted(list(ctx_tbls)),
            "missing_tables": sorted(list(gold_tbls - ctx_tbls)),
            "gold_cols": sorted(list(gold_cols)),
            "missing_cols": sorted(list(gold_cols - ctx_cols)),
            "table_count": tbl_cnt,
            "column_count": col_cnt,
            "est_tokens": est_tokens,
        })

    # 2. Control questions
    control_results = []
    control_table_counts = []
    control_col_counts = []
    control_token_counts = []
    control_regressions = 0

    # We also compare against baseline control context to ensure zero loss
    for qid in CONTROL_QIDS:
        c = dev100_cases[qid]
        ctx_base = build_context(c, "baseline")
        base_tbls = {t.sql_identifier.lower() for t in ctx_base.tables if t.sql_identifier}
        base_cols = {col.name.lower() for t in ctx_base.tables for col in t.columns}

        ctx = build_context(c, mode)
        ctx_tbls = {t.sql_identifier.lower() for t in ctx.tables if t.sql_identifier}
        ctx_cols = {col.name.lower() for t in ctx.tables for col in t.columns}

        gold_sql = c.get("gold_sql") or c.get("bird_gold_sql") or c["gold"]["sql_original"]
        gold_tbls, gold_cols = extract_gold_requirements(gold_sql)
        
        # Check regression: did it lose any gold table or column that baseline had?
        lost_gold_tbls = (gold_tbls & base_tbls) - ctx_tbls
        lost_gold_cols = (gold_cols & base_cols) - ctx_cols
        if lost_gold_tbls or lost_gold_cols:
            control_regressions += 1

        tbl_cnt = len(ctx.tables)
        col_cnt = sum(len(t.columns) for t in ctx.tables)
        prompt_str = prompt_builder._format_authorized_schema(ctx)
        est_tokens = len(prompt_str) // 4

        control_table_counts.append(tbl_cnt)
        control_col_counts.append(col_cnt)
        control_token_counts.append(est_tokens)

        control_results.append({
            "case_id": qid,
            "db_id": c["db_id"],
            "table_count": tbl_cnt,
            "column_count": col_cnt,
            "est_tokens": est_tokens,
            "lost_gold_tables": list(lost_gold_tbls),
            "lost_gold_cols": list(lost_gold_cols),
        })

    tbl_recall = target_gold_tbl_retrieved / target_gold_tbl_total if target_gold_tbl_total else 0.0
    col_recall = target_gold_col_retrieved / target_gold_col_total if target_gold_col_total else 0.0

    all_tbl_counts = target_table_counts + control_table_counts
    all_col_counts = target_col_counts + control_col_counts
    all_token_counts = target_token_counts + control_token_counts

    summary = {
        "mode": mode,
        "target_table_recall": round(tbl_recall, 4),
        "target_column_recall": round(col_recall, 4),
        "target_missing_tables_count": sum(len(r["missing_tables"]) for r in target_results),
        "target_missing_cols_count": sum(len(r["missing_cols"]) for r in target_results),
        "mean_tables": round(sum(all_tbl_counts) / len(all_tbl_counts), 2),
        "max_tables": max(all_tbl_counts),
        "mean_columns": round(sum(all_col_counts) / len(all_col_counts), 2),
        "max_columns": max(all_col_counts),
        "mean_tokens": round(sum(all_token_counts) / len(all_token_counts), 1),
        "max_tokens": max(all_token_counts),
        "control_regressions": control_regressions,
        "target_results": target_results,
        "control_results": control_results,
    }

    print(f"[{mode}] Target Table Recall: {tbl_recall*100:.2f}%, Column Recall: {col_recall*100:.2f}%")
    print(f"[{mode}] Mean Tables: {summary['mean_tables']}, Mean Columns: {summary['mean_columns']}, Mean Tokens: {summary['mean_tokens']}")
    print(f"[{mode}] Control Regressions: {control_regressions}")
    return summary


def main() -> None:
    modes = ["baseline", "unconditional_fk", "small_db_fallback", "column_fill", "combined"]
    results = {}
    for m in modes:
        results[m] = evaluate_intervention(m)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / "offline_intervention_replay.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved offline intervention results to {out_file}")


if __name__ == "__main__":
    main()
