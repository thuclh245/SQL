"""Agent 01 — Context Sufficiency Auditor Script.

Determines whether SQL failures are caused upstream because the solver
never received sufficient schema/context evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import build_scope, traverse_scope

from t2s.benchmark.case_loader import BenchmarkCaseBundle, BenchmarkCaseFilter, load_benchmark_cases
from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.benchmark.runtime_factory import (
    AllTablesBenchmarkAccessPolicy,
    build_query_request_from_benchmark_case,
)
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import GroundingContext
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver.prompt_builder import DirectSqlPromptBuilder


def get_git_info() -> tuple[str, str]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--short"], text=True
        ).strip()
        return commit, status
    except Exception:
        return "unknown", "unknown"


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class ContextSufficiencyAuditor:
    def __init__(
        self,
        tables_json_path: Path,
        database_root: Path,
        grounding_budget: GroundingBudget | None = None,
    ) -> None:
        self.tables_json_path = tables_json_path
        self.database_root = database_root
        self.grounding_budget = grounding_budget or GroundingBudget()
        self.prompt_builder = DirectSqlPromptBuilder(prompt_version="v002")

        # Database cache
        self.db_catalogs: dict[str, InMemoryCatalog] = {}
        self.db_table_cols: dict[str, dict[str, set[str]]] = {}
        self.db_declared_fks: dict[str, set[tuple[tuple[str, str], tuple[str, str]]]] = {}
        self.db_retrievers: dict[str, SchemaRetriever] = {}
        self.db_auth_services: dict[str, AuthorizationService] = {}

    def _ensure_db_loaded(self, db_id: str) -> None:
        if db_id in self.db_catalogs:
            return

        cat_tables = load_bird_catalog_tables(
            db_id=db_id, tables_json_path=self.tables_json_path
        )
        catalog = InMemoryCatalog()
        catalog.upsert_tables(cat_tables)

        doc_builder = CatalogSearchDocumentBuilder()
        docs = [
            doc
            for table in cat_tables
            for doc in doc_builder.build_search_documents(table)
        ]
        retriever = SchemaRetriever(InMemorySchemaSearch(docs))

        auth_res = [
            AuthorizedSqlResource(
                catalog_fqn=table.table_fqn,
                sql_identifier=table.sql_identifier,
            )
            for table in cat_tables
            if table.sql_identifier
        ]
        auth_service = AuthorizationService(AllTablesBenchmarkAccessPolicy(auth_res))

        table_cols: dict[str, set[str]] = {}
        for table in cat_tables:
            if table.sql_identifier:
                table_cols[table.sql_identifier.lower()] = {
                    c.column_name.lower() for c in table.columns
                }

        declared_fks: set[tuple[tuple[str, str], tuple[str, str]]] = set()
        for table in cat_tables:
            for rel in catalog.get_relationships(table.table_fqn):
                from_t = rel.from_table_fqn.split(".")[-1].lower()
                to_t = rel.to_table_fqn.split(".")[-1].lower()
                for fc, tc in zip(rel.from_column_names, rel.to_column_names, strict=False):
                    edge = tuple(sorted([(from_t, fc.lower()), (to_t, tc.lower())]))
                    declared_fks.add(edge)  # type: ignore[arg-type]

        self.db_catalogs[db_id] = catalog
        self.db_table_cols[db_id] = table_cols
        self.db_declared_fks[db_id] = declared_fks
        self.db_retrievers[db_id] = retriever
        self.db_auth_services[db_id] = auth_service

    def resolve_gold_elements(
        self, sql: str, db_id: str
    ) -> tuple[
        set[str],
        set[str],
        set[tuple[tuple[str, str], tuple[str, str]]],
        set[str],
    ]:
        self._ensure_db_loaded(db_id)
        cat = self.db_table_cols[db_id]
        parsed = sqlglot.parse_one(sql, read="sqlite")
        root_scope = build_scope(parsed)

        req_tables: set[str] = set()
        req_cols: set[str] = set()
        req_join_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()
        req_literals: set[str] = set()

        if root_scope is None:
            return req_tables, req_cols, req_join_edges, req_literals

        def get_scope_alias_map(scope: Any) -> dict[str, str]:
            alias_map: dict[str, str] = {}
            for k, src in scope.sources.items():
                k_lower = k.lower()
                if isinstance(src, exp.Table):
                    t_name = src.name.lower()
                    if t_name in cat:
                        alias_map[k_lower] = t_name
                elif hasattr(src, "sources"):
                    sub_tables: set[str] = set()
                    for _, sub_src in src.sources.items():
                        if isinstance(sub_src, exp.Table) and sub_src.name.lower() in cat:
                            sub_tables.add(sub_src.name.lower())
                    if len(sub_tables) == 1:
                        alias_map[k_lower] = list(sub_tables)[0]
            return alias_map

        for tbl in parsed.find_all(exp.Table):
            if tbl.name and tbl.name.lower() in cat:
                req_tables.add(tbl.name.lower())

        # Collect SELECT expression aliases to avoid treating them as physical columns
        select_aliases: set[str] = set()
        for scope in traverse_scope(parsed):
            for s in scope.expression.find_all(exp.Select):
                for expr in s.expressions:
                    if expr.alias:
                        select_aliases.add(expr.alias.lower())

        def resolve_col(
            col: exp.Column, scope: Any, imm_alias_map: dict[str, str]
        ) -> tuple[str, str] | None:
            c_name = col.name.lower()
            if not c_name or c_name == "*" or c_name in select_aliases:
                return None
            table_qual = col.table.lower() if col.table else None
            if table_qual:
                curr = scope
                while curr:
                    cmap = get_scope_alias_map(curr)
                    if table_qual in cmap:
                        phys_table = cmap[table_qual]
                        if c_name in cat.get(phys_table, set()):
                            return (phys_table, c_name)
                    elif table_qual in cat:
                        if c_name in cat.get(table_qual, set()):
                            return (table_qual, c_name)
                    curr = curr.parent
            else:
                imm_cands = [t for t in set(imm_alias_map.values()) if c_name in cat.get(t, set())]
                if len(imm_cands) == 1:
                    return (imm_cands[0], c_name)
                curr = scope.parent
                while curr:
                    cmap = get_scope_alias_map(curr)
                    cands = [t for t in set(cmap.values()) if c_name in cat.get(t, set())]
                    if len(cands) == 1:
                        return (cands[0], c_name)
                    curr = curr.parent
                # Fallback to catalog tables referenced in query
                cat_cands = [t for t, cols in cat.items() if c_name in cols and t in req_tables]
                if len(cat_cands) == 1:
                    return (cat_cands[0], c_name)
            return None

        # Resolve columns
        for scope in traverse_scope(parsed):
            imm_alias_map = get_scope_alias_map(scope)
            for col in scope.columns:
                if col.find_ancestor(exp.Select) != scope.expression:
                    continue
                resolved = resolve_col(col, scope, imm_alias_map)
                if resolved:
                    req_cols.add(f"{resolved[0]}.{resolved[1]}")

        # Resolve join edges from JOIN ON
        for scope in traverse_scope(parsed):
            imm_alias_map = get_scope_alias_map(scope)
            for join in scope.expression.find_all(exp.Join):
                on_clause = join.args.get("on")
                if not on_clause:
                    continue
                for eq in on_clause.find_all(exp.EQ):
                    left_cols = list(eq.left.find_all(exp.Column))
                    right_cols = list(eq.right.find_all(exp.Column))
                    if len(left_cols) == 1 and len(right_cols) == 1:
                        lres = resolve_col(left_cols[0], scope, imm_alias_map)
                        rres = resolve_col(right_cols[0], scope, imm_alias_map)
                        if lres and rres and lres[0] != rres[0]:
                            edge = tuple(sorted([lres, rres]))
                            req_join_edges.add(edge)  # type: ignore[arg-type]

            # Resolve join edges from WHERE
            where_clause = scope.expression.args.get("where")
            if where_clause:
                for eq in where_clause.find_all(exp.EQ):
                    left_cols = list(eq.left.find_all(exp.Column))
                    right_cols = list(eq.right.find_all(exp.Column))
                    if len(left_cols) == 1 and len(right_cols) == 1:
                        lres = resolve_col(left_cols[0], scope, imm_alias_map)
                        rres = resolve_col(right_cols[0], scope, imm_alias_map)
                        if lres and rres and lres[0] != rres[0]:
                            edge = tuple(sorted([lres, rres]))
                            req_join_edges.add(edge)  # type: ignore[arg-type]

        # Literals
        for lit in parsed.find_all(exp.Literal):
            val = str(lit.this).strip()
            if val:
                req_literals.add(val)

        return req_tables, req_cols, req_join_edges, req_literals

    def audit_case(
        self,
        case_bundle: BenchmarkCaseBundle,
        eval_result: dict[str, Any],
    ) -> dict[str, Any]:
        cid = case_bundle.inference_case.case_id
        db_id = case_bundle.inference_case.db_id
        q = case_bundle.inference_case.question
        evidence = case_bundle.inference_case.evidence
        gold_sql = case_bundle.scoring_gold.official_sql

        if not gold_sql:
            raise ValueError(f"Gold SQL missing for case {cid}")

        self._ensure_db_loaded(db_id)
        catalog = self.db_catalogs[db_id]
        retriever = self.db_retrievers[db_id]
        auth_service = self.db_auth_services[db_id]

        req_tables, req_cols, req_join_edges, req_literals = self.resolve_gold_elements(
            gold_sql, db_id
        )

        # 1. Source Metadata Check
        cat_tables_map = self.db_table_cols[db_id]
        declared_fks = self.db_declared_fks[db_id]

        source_missing_tables = [t for t in req_tables if t not in cat_tables_map]
        source_missing_cols = [
            c for c in req_cols if c.split(".")[1] not in cat_tables_map.get(c.split(".")[0], set())
        ]
        source_undeclared_fks = [
            list(edge) for edge in req_join_edges if edge not in declared_fks
        ]

        # 2. Replay Grounding Pipeline
        builder = GroundingContextBuilder(
            catalog=catalog,
            schema_retriever=retriever,
            authorization_service=auth_service,
            grounding_budget=self.grounding_budget,
        )
        req = build_query_request_from_benchmark_case(
            question=q, evidence=evidence, evidence_mode="inline"
        )
        user = UserIdentity(user_id="benchmark-runner", tenant_id="t2s")
        ctx: GroundingContext = builder.build_grounding_context(req, user)

        # Traced objects
        authorized_fqns = {
            r.catalog_fqn for r in auth_service.get_authorized_resources(user)
        }
        retrieved_candidates = retriever.retrieve_schema_candidates(
            question=req.question,
            allowed_table_fqns=authorized_fqns,
            limit=self.grounding_budget.max_candidate_tables,
        )
        retrieved_candidate_fqns = {c.table_fqn for c in retrieved_candidates}

        hydrated_tables = [t.sql_identifier.lower() for t in ctx.tables]
        hydrated_cols = [
            f"{t.sql_identifier.lower()}.{c.name.lower()}"
            for t in ctx.tables
            for c in t.columns
        ]

        hydrated_join_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()
        for t in ctx.tables:
            for rel in t.relationships:
                from_t = rel.from_table_fqn.split(".")[-1].lower()
                to_t = rel.to_table_fqn.split(".")[-1].lower()
                for fc, tc in zip(rel.from_columns, rel.to_columns, strict=False):
                    edge = tuple(sorted([(from_t, fc.lower()), (to_t, tc.lower())]))
                    hydrated_join_edges.add(edge)  # type: ignore[arg-type]

        # Check serialized prompt
        serialized_schema = self.prompt_builder._format_authorized_schema(ctx)

        # Deficit identification
        missing_tables = [t for t in req_tables if t not in hydrated_tables]
        missing_cols = [c for c in req_cols if c not in hydrated_cols]
        missing_joins = [list(edge) for edge in req_join_edges if edge not in hydrated_join_edges]

        # Recalls
        table_recall = (
            (len(req_tables) - len(missing_tables)) / len(req_tables)
            if req_tables
            else 1.0
        )
        column_recall = (
            (len(req_cols) - len(missing_cols)) / len(req_cols)
            if req_cols
            else 1.0
        )
        rel_recall = (
            (len(req_join_edges) - len(missing_joins)) / len(req_join_edges)
            if req_join_edges
            else 1.0
        )

        # First divergence point and primary cause classification
        first_divergence_point = "NONE"
        primary_cause = "CONTEXT_SUFFICIENT"
        secondary_causes: list[str] = []

        if source_missing_tables or source_missing_cols:
            first_divergence_point = "SOURCE_METADATA"
            primary_cause = "SOURCE_METADATA_MISSING"
        elif missing_tables:
            # Trace where the table was dropped
            for mt in missing_tables:
                mt_fqn = f"{db_id}.main.{mt}"
                if mt_fqn not in authorized_fqns:
                    first_divergence_point = "AUTHORIZATION"
                    primary_cause = "AUTHORIZATION_REMOVED_REQUIRED_EVIDENCE"
                    break
                elif mt_fqn not in retrieved_candidate_fqns:
                    first_divergence_point = "RETRIEVAL"
                    primary_cause = "RETRIEVAL_MISSED_REQUIRED_TABLE"
                    break
                else:
                    first_divergence_point = "RETRIEVAL"
                    primary_cause = "RETRIEVAL_MISSED_REQUIRED_TABLE"
                    secondary_causes.append("CONTEXT_BUDGET_DROPPED_REQUIRED_EVIDENCE")
                    break
        elif missing_cols:
            # Required tables are hydrated, but required columns were dropped
            budget_hit = False
            for t in ctx.tables:
                if len(t.columns) >= self.grounding_budget.max_columns_per_table:
                    budget_hit = True
            if len(hydrated_cols) >= self.grounding_budget.max_total_columns:
                budget_hit = True

            if budget_hit:
                first_divergence_point = "CONTEXT_BUDGET"
                primary_cause = "CONTEXT_BUDGET_DROPPED_REQUIRED_EVIDENCE"
            else:
                first_divergence_point = "RETRIEVAL"
                primary_cause = "RETRIEVAL_MISSED_REQUIRED_COLUMN"
        elif missing_joins:
            # Check if undeclared in catalog
            if source_undeclared_fks:
                first_divergence_point = "SOURCE_METADATA"
                primary_cause = "RELATIONSHIP_EVIDENCE_MISSING"
                secondary_causes.append("SOURCE_METADATA_MISSING")
            elif len(ctx.tables) > 0 and any(
                len(t.relationships) >= self.grounding_budget.max_relationships
                for t in ctx.tables
            ):
                first_divergence_point = "CONTEXT_BUDGET"
                primary_cause = "CONTEXT_BUDGET_DROPPED_REQUIRED_EVIDENCE"
                secondary_causes.append("RELATIONSHIP_EVIDENCE_MISSING")
            else:
                first_divergence_point = "RETRIEVAL"
                primary_cause = "RELATIONSHIP_EVIDENCE_MISSING"
        else:
            # Check serialization
            all_serialized = True
            for tbl in hydrated_tables:
                if tbl not in serialized_schema.lower():
                    all_serialized = False
            for col in hydrated_cols:
                col_name = col.split(".")[1]
                if col_name not in serialized_schema.lower():
                    all_serialized = False

            if not all_serialized:
                first_divergence_point = "SERIALIZATION"
                primary_cause = "SERIALIZATION_DROPPED_REQUIRED_EVIDENCE"
            else:
                first_divergence_point = "NONE"
                primary_cause = "CONTEXT_SUFFICIENT"

        return {
            "case_id": cid,
            "question_id": case_bundle.inference_case.question_id,
            "db_id": db_id,
            "bird_difficulty": case_bundle.inference_case.bird_difficulty,
            "execution_correct": eval_result.get("execution_correct", False),
            "required_tables_count": len(req_tables),
            "required_columns_count": len(req_cols),
            "required_relationships_count": len(req_join_edges),
            "table_recall": round(table_recall, 4),
            "column_recall": round(column_recall, 4),
            "relationship_recall": round(rel_recall, 4),
            "required_schema_available": not (source_missing_tables or source_missing_cols),
            "required_schema_retrieved": len(missing_tables) == 0,
            "first_divergence_point": first_divergence_point,
            "primary_cause": primary_cause,
            "secondary_causes": secondary_causes,
            "missing_tables": sorted(list(missing_tables)),
            "missing_columns": sorted(list(missing_cols)),
            "missing_relationships": missing_joins,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Text-to-SQL Context Sufficiency")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"),
        help="Path to evaluation dataset",
    )
    parser.add_argument(
        "--eval-cases",
        type=Path,
        default=Path("results/causal_evaluation/arm_f0_planner_off/cases.jsonl"),
        help="Path to evaluated cases.jsonl",
    )
    parser.add_argument(
        "--tables-json",
        type=Path,
        default=Path("data/bird_mini_dev/mini_dev_tables.json"),
        help="Path to tables.json",
    )
    parser.add_argument(
        "--database-root",
        type=Path,
        default=Path("benchmarks/t2s/databases/official"),
        help="Path to SQLite databases directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/audits/system_bottleneck/agent_01_context_sufficiency"),
        help="Directory to save audit artifacts",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    case_filter = BenchmarkCaseFilter(executable_only=True)
    cases = load_benchmark_cases(args.dataset, case_filter)

    with args.eval_cases.open("r", encoding="utf-8") as f:
        eval_cases = {row["case_id"]: row for row in (json.loads(line) for line in f)}

    auditor = ContextSufficiencyAuditor(
        tables_json_path=args.tables_json,
        database_root=args.database_root,
    )

    classifications: list[dict[str, Any]] = []
    failed_classifications: list[dict[str, Any]] = []

    for bundle in cases:
        cid = bundle.inference_case.case_id
        if cid not in eval_cases:
            continue
        eval_res = eval_cases[cid]
        record = auditor.audit_case(bundle, eval_res)
        classifications.append(record)
        if not eval_res.get("execution_correct", False):
            failed_classifications.append(record)

    # Write case_classification.jsonl (persisting structural summaries for failed cases)
    case_class_path = args.output_dir / "case_classification.jsonl"
    with case_class_path.open("w", encoding="utf-8") as f:
        for r in failed_classifications:
            summary_record = {
                "case_id": r["case_id"],
                "question_id": r["question_id"],
                "db_id": r["db_id"],
                "bird_difficulty": r["bird_difficulty"],
                "required_tables_count": r["required_tables_count"],
                "required_columns_count": r["required_columns_count"],
                "required_relationships_count": r["required_relationships_count"],
                "table_recall": r["table_recall"],
                "column_recall": r["column_recall"],
                "relationship_recall": r["relationship_recall"],
                "required_schema_available": r["required_schema_available"],
                "required_schema_retrieved": r["required_schema_retrieved"],
                "first_divergence_point": r["first_divergence_point"],
                "primary_cause": r["primary_cause"],
                "secondary_causes": r["secondary_causes"],
                "missing_tables": r["missing_tables"],
                "missing_columns": r["missing_columns"],
            }
            f.write(json.dumps(summary_record) + "\n")

    # Metrics computation
    total_failed = len(failed_classifications)
    mean_table_recall = (
        sum(r["table_recall"] for r in failed_classifications) / total_failed
        if total_failed
        else 1.0
    )
    mean_col_recall = (
        sum(r["column_recall"] for r in failed_classifications) / total_failed
        if total_failed
        else 1.0
    )
    mean_rel_recall = (
        sum(r["relationship_recall"] for r in failed_classifications) / total_failed
        if total_failed
        else 1.0
    )

    first_div_dist: dict[str, int] = {}
    primary_cause_dist: dict[str, int] = {}
    for r in failed_classifications:
        fdp = r["first_divergence_point"]
        first_div_dist[fdp] = first_div_dist.get(fdp, 0) + 1
        pc = r["primary_cause"]
        primary_cause_dist[pc] = primary_cause_dist.get(pc, 0) + 1

    sufficient_count = sum(
        1 for r in failed_classifications if r["primary_cause"] == "CONTEXT_SUFFICIENT"
    )
    insufficient_count = total_failed - sufficient_count

    deficit_breakdown = {
        "source_metadata_absent": primary_cause_dist.get("SOURCE_METADATA_MISSING", 0),
        "authorization_loss": primary_cause_dist.get("AUTHORIZATION_REMOVED_REQUIRED_EVIDENCE", 0),
        "retrieval_failure": (
            primary_cause_dist.get("RETRIEVAL_MISSED_REQUIRED_TABLE", 0)
            + primary_cause_dist.get("RETRIEVAL_MISSED_REQUIRED_COLUMN", 0)
            + primary_cause_dist.get("RELATIONSHIP_EVIDENCE_MISSING", 0)
        ),
        "budget_loss": primary_cause_dist.get("CONTEXT_BUDGET_DROPPED_REQUIRED_EVIDENCE", 0),
        "serialization_loss": primary_cause_dist.get("SERIALIZATION_DROPPED_REQUIRED_EVIDENCE", 0),
    }

    metrics = {
        "total_evaluated_cases": len(classifications),
        "total_failed_cases_analyzed": total_failed,
        "mean_required_table_recall": round(mean_table_recall, 4),
        "mean_required_column_recall": round(mean_col_recall, 4),
        "mean_relationship_evidence_recall": round(mean_rel_recall, 4),
        "failures_with_insufficient_context_count": insufficient_count,
        "failures_with_insufficient_context_pct": round(
            insufficient_count / total_failed, 4
        )
        if total_failed
        else 0.0,
        "failures_with_sufficient_context_count": sufficient_count,
        "failures_with_sufficient_context_pct": round(
            sufficient_count / total_failed, 4
        )
        if total_failed
        else 0.0,
        "first_divergence_point_distribution": first_div_dist,
        "primary_cause_distribution": primary_cause_dist,
        "deficit_breakdown": deficit_breakdown,
        "fraction_explained_before_reasoning": round(
            insufficient_count / total_failed, 4
        )
        if total_failed
        else 0.0,
    }

    metrics_path = args.output_dir / "metrics.json"
    with metrics_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # Manifest
    git_commit, git_dirty = get_git_info()
    manifest = {
        "audit_name": "agent_01_context_sufficiency",
        "timestamp_utc": subprocess.check_output(
            ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True
        ).strip(),
        "git_commit": git_commit,
        "git_dirty_status": git_dirty,
        "dataset_path": str(args.dataset),
        "dataset_sha256": compute_file_sha256(args.dataset),
        "eval_cases_path": str(args.eval_cases),
        "database_root": str(args.database_root),
        "target_model": "openai/gpt-oss-120b",
        "audited_failed_cases_count": total_failed,
        "total_evaluated_cases_count": len(classifications),
        "produced_artifacts": [
            "case_classification.jsonl",
            "metrics.json",
            "manifest.json",
        ],
    }

    manifest_path = args.output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Audit completed successfully across {total_failed} failed cases.")
    print(f"Results written to: {args.output_dir}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
