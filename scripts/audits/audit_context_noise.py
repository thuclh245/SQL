"""Agent 02: Context Noise and Representation Auditor.

Audits whether Text-to-SQL performance is degraded because relevant evidence is buried
in excessive, redundant, poorly ranked, or badly serialized context.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlglot
from dotenv import load_dotenv
from sqlglot import exp

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.benchmark.runtime_factory import AllTablesBenchmarkAccessPolicy
from t2s.benchmark.scoring import score_execution_accuracy
from t2s.catalog import CatalogTable
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.catalog.metadata_document import CatalogSearchDocumentBuilder
from t2s.contracts import (
    ColumnContext,
    GroundingContext,
    QueryRequest,
    RelationshipEvidence,
    TableContext,
)
from t2s.grounding.grounding_budget import GroundingBudget
from t2s.grounding.grounding_context_builder import GroundingContextBuilder
from t2s.grounding.schema_retriever import InMemorySchemaSearch, SchemaRetriever
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver.direct_sql_solver import DirectSqlSolver
from t2s.solver.prompt_builder import DirectSqlPromptBuilder
from t2s.solver.solver_request import SolverGenerationSettings, SolverRequest

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
PILOT_DATASET_PATH = ROOT_DIR / "benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"
OFFICIAL_DB_ROOT = ROOT_DIR / "benchmarks/t2s/databases/official"
MINI_DEV_TABLES_PATH = ROOT_DIR / "data/bird_mini_dev/mini_dev_tables.json"
F0_CASES_PATH = ROOT_DIR / "results/causal_evaluation/arm_f0_planner_off/cases.jsonl"

RESULTS_DIR = ROOT_DIR / "results/audits/system_bottleneck/agent_02_context_noise"
OUTPUT_STATS_PATH = RESULTS_DIR / "context_statistics.jsonl"
OUTPUT_COUNTERFACTUAL_PATH = RESULTS_DIR / "counterfactual_metrics.json"
OUTPUT_MANIFEST_PATH = RESULTS_DIR / "manifest.json"


@dataclass
class CaseContextMetrics:
    case_id: str
    db_id: str
    stratum: str
    question: str
    execution_correct: bool | None
    execution_success: bool
    runtime_status: str
    error_code: str | None
    tables_available: int
    tables_sent: int
    gold_tables_count: int
    relevant_tables_sent: int
    irrelevant_tables_sent: int
    columns_sent: int
    gold_cols_count: int
    relevant_columns_sent: int
    irrelevant_columns_sent: int
    context_precision_tables: float
    context_recall_tables: float
    context_precision_columns: float
    context_recall_columns: float
    table_distractor_ratio: float
    column_distractor_ratio: float
    serialized_context_chars: int
    prompt_tokens: int | None
    schema_tokens_estimated: int
    schema_tokens_ratio: float | None
    duplicate_relationships: int
    total_relationships_rendered: int
    value_evidence_count: int
    relevant_evidence_rank: float | None
    fallback_sent_full_schema: bool
    gold_tables: list[str]
    gold_columns: list[str]
    sent_tables: list[str]
    sent_columns: list[str]


def get_git_info() -> tuple[str, str]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT_DIR, text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT_DIR, text=True
    ).strip()
    return commit, status


def get_file_sha256(path: Path) -> str:
    if not path.exists():
        return "NOT_FOUND"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_db_schemas() -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for db_dir in OFFICIAL_DB_ROOT.iterdir():
        if not db_dir.is_dir():
            continue
        sqlite_file = db_dir / f"{db_dir.name}.sqlite"
        if not sqlite_file.exists():
            continue
        db_id = db_dir.name
        conn = sqlite3.connect(sqlite_file)
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [r[0] for r in cur.fetchall()]
        cols_by_t: dict[str, dict[str, str]] = {}
        for t in tables:
            cur.execute(f'PRAGMA table_info("{t}")')
            cols_by_t[t.lower()] = {r[1].lower(): r[1] for r in cur.fetchall()}
        conn.close()
        schemas[db_id] = {
            "tables": {t.lower(): t for t in tables},
            "columns": cols_by_t,
        }
    return schemas


def extract_gold_schema(
    sql: str, db_id: str, db_schemas: dict[str, Any]
) -> tuple[set[str], set[str]]:
    schema = db_schemas[db_id]
    tree = sqlglot.parse_one(sql, read="sqlite")
    used_tables: set[str] = set()
    for t in tree.find_all(exp.Table):
        t_low = t.name.lower()
        if t_low in schema["tables"]:
            used_tables.add(schema["tables"][t_low])

    used_cols: set[str] = set()
    for col in tree.find_all(exp.Column):
        c_low = col.name.lower()
        t_qual = col.table.lower() if col.table else None
        if t_qual and t_qual in schema["tables"]:
            real_t = schema["tables"][t_qual]
            if c_low in schema["columns"].get(t_qual, {}):
                used_cols.add(f"{real_t}.{schema['columns'][t_qual][c_low]}")
        else:
            matching_tables = [
                schema["tables"][t.lower()]
                for t in used_tables
                if c_low in schema["columns"].get(t.lower(), {})
            ]
            if len(matching_tables) == 1:
                used_cols.add(
                    f"{matching_tables[0]}.{schema['columns'][matching_tables[0].lower()][c_low]}"
                )
            elif not matching_tables:
                all_matching = [
                    schema["tables"][t]
                    for t in schema["tables"]
                    if c_low in schema["columns"].get(t, {})
                ]
                if len(all_matching) == 1:
                    used_cols.add(
                        f"{all_matching[0]}.{schema['columns'][all_matching[0].lower()][c_low]}"
                    )
                    used_tables.add(all_matching[0])
    return used_tables, used_cols


def build_grounding_context_builders(db_ids: set[str]) -> dict[str, GroundingContextBuilder]:
    gcbs: dict[str, GroundingContextBuilder] = {}
    for db_id in db_ids:
        cat_tables = load_bird_catalog_tables(db_id=db_id, tables_json_path=MINI_DEV_TABLES_PATH)
        catalog = InMemoryCatalog()
        catalog.upsert_tables(cat_tables)
        doc_builder = CatalogSearchDocumentBuilder()
        docs = [doc for t in cat_tables for doc in doc_builder.build_search_documents(t)]
        retriever = SchemaRetriever(InMemorySchemaSearch(docs))
        authorized = [
            AuthorizedSqlResource(catalog_fqn=t.table_fqn, sql_identifier=t.sql_identifier)
            for t in cat_tables
            if t.sql_identifier
        ]
        auth_svc = AuthorizationService(AllTablesBenchmarkAccessPolicy(authorized))
        gcbs[db_id] = GroundingContextBuilder(catalog, retriever, auth_svc, GroundingBudget())
    return gcbs


def pearson_correlation(x: list[float], y: list[float]) -> tuple[float, float]:
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=True))
    var_x = sum((xi - mx) ** 2 for xi in x)
    var_y = sum((yi - my) ** 2 for yi in y)
    if var_x == 0 or var_y == 0:
        return 0.0, 1.0
    r = cov / math.sqrt(var_x * var_y)
    df = n - 2
    t = r * math.sqrt(df / max(1e-15, 1 - r**2))
    return r, t


def collect_context_statistics() -> list[CaseContextMetrics]:
    cases = [json.loads(line) for line in open(PILOT_DATASET_PATH)]
    sql_cases = {c["case_id"]: c for c in cases if c["gold"].get("sql_original")}
    f0_cases = {json.loads(line)["case_id"]: json.loads(line) for line in open(F0_CASES_PATH)}

    db_schemas = load_db_schemas()
    all_dbs = {c["inference"]["db_id"] for c in sql_cases.values()}
    gcbs = build_grounding_context_builders(all_dbs)
    pb = DirectSqlPromptBuilder(prompt_version="v002")

    metrics_list: list[CaseContextMetrics] = []

    for cid, f0_record in f0_cases.items():
        pilot_c = sql_cases[cid]
        db_id = pilot_c["inference"]["db_id"]
        question = pilot_c["inference"]["question"]
        stratum = pilot_c["gold"]["stratum"]
        gold_sql = pilot_c["gold"]["sql_original"]
        gold_tables, gold_cols = extract_gold_schema(gold_sql, db_id, db_schemas)

        gcb = gcbs[db_id]
        req = QueryRequest(question=question, database_dialect="sqlite")
        ctx = gcb.build_grounding_context(req, UserIdentity(user_id="test", tenant_id="t2s"))

        sent_tables = [t.sql_identifier for t in ctx.tables]
        sent_cols = [f"{t.sql_identifier}.{c.name}" for t in ctx.tables for c in t.columns]

        gold_tables_norm = {t.lower() for t in gold_tables}
        sent_tables_norm = {t.lower(): t for t in sent_tables}
        rel_tables_sent = [sent_tables_norm[t] for t in sent_tables_norm if t in gold_tables_norm]
        irrel_tables_sent = [
            sent_tables_norm[t] for t in sent_tables_norm if t not in gold_tables_norm
        ]

        gold_cols_norm = {c.lower() for c in gold_cols}
        sent_cols_norm = {c.lower(): c for c in sent_cols}
        rel_cols_sent = [sent_cols_norm[c] for c in sent_cols_norm if c in gold_cols_norm]
        irrel_cols_sent = [sent_cols_norm[c] for c in sent_cols_norm if c not in gold_cols_norm]

        schema_str = pb._format_authorized_schema(ctx)
        schema_tokens_est = len(schema_str) // 4

        rel_lines = [
            line.strip()
            for line in schema_str.splitlines()
            if line.strip().startswith("- type: many_to_one")
        ]
        dup_rels = len(rel_lines) - len(set(rel_lines))

        p_tab = len(rel_tables_sent) / len(sent_tables) if sent_tables else 0.0
        r_tab = len(rel_tables_sent) / len(gold_tables) if gold_tables else 0.0
        p_col = len(rel_cols_sent) / len(sent_cols) if sent_cols else 0.0
        r_col = len(rel_cols_sent) / len(gold_cols) if gold_cols else 0.0
        table_distractor_ratio = len(irrel_tables_sent) / len(sent_tables) if sent_tables else 0.0
        col_distractor_ratio = len(irrel_cols_sent) / len(sent_cols) if sent_cols else 0.0

        # Rank of relevant tables in prompt (1-indexed)
        table_order = [t.lower() for t in sent_tables]
        positions = [table_order.index(t) + 1 for t in gold_tables_norm if t in table_order]
        rel_evidence_rank = sum(positions) / len(positions) if positions else None

        avail_tables = len(db_schemas[db_id]["tables"])
        fallback_sent_full = len(sent_tables) >= avail_tables

        prompt_toks = f0_record.get("tokens_input")
        tok_ratio = schema_tokens_est / prompt_toks if prompt_toks and prompt_toks > 0 else None

        metrics_list.append(
            CaseContextMetrics(
                case_id=cid,
                db_id=db_id,
                stratum=stratum,
                question=question,
                execution_correct=f0_record.get("execution_correct"),
                execution_success=f0_record.get("execution_success", False),
                runtime_status=f0_record.get("runtime_status", "UNKNOWN"),
                error_code=f0_record.get("error_code"),
                tables_available=avail_tables,
                tables_sent=len(sent_tables),
                gold_tables_count=len(gold_tables),
                relevant_tables_sent=len(rel_tables_sent),
                irrelevant_tables_sent=len(irrel_tables_sent),
                columns_sent=len(sent_cols),
                gold_cols_count=len(gold_cols),
                relevant_columns_sent=len(rel_cols_sent),
                irrelevant_columns_sent=len(irrel_cols_sent),
                context_precision_tables=round(p_tab, 4),
                context_recall_tables=round(r_tab, 4),
                context_precision_columns=round(p_col, 4),
                context_recall_columns=round(r_col, 4),
                table_distractor_ratio=round(table_distractor_ratio, 4),
                column_distractor_ratio=round(col_distractor_ratio, 4),
                serialized_context_chars=len(schema_str),
                prompt_tokens=prompt_toks,
                schema_tokens_estimated=schema_tokens_est,
                schema_tokens_ratio=round(tok_ratio, 4) if tok_ratio is not None else None,
                duplicate_relationships=dup_rels,
                total_relationships_rendered=len(rel_lines),
                value_evidence_count=f0_record.get("value_binding_count", 0),
                relevant_evidence_rank=(
                    round(rel_evidence_rank, 2) if rel_evidence_rank is not None else None
                ),
                fallback_sent_full_schema=fallback_sent_full,
                gold_tables=sorted(list(gold_tables)),
                gold_columns=sorted(list(gold_cols)),
                sent_tables=sent_tables,
                sent_columns=sent_cols,
            )
        )

    return metrics_list


def build_c1_context(
    db_id: str,
    gold_tables: set[str],
    gold_cols: set[str],
    catalog_tables: list[CatalogTable],
) -> GroundingContext:
    """Mechanically construct minimal structurally sufficient context C1."""
    gold_tables_lower = {t.lower() for t in gold_tables}
    gold_cols_lower = {c.lower() for c in gold_cols}

    selected_catalog_tables = [
        ct
        for ct in catalog_tables
        if ct.sql_identifier and ct.sql_identifier.lower() in gold_tables_lower
    ]

    table_contexts: list[TableContext] = []
    for ct in selected_catalog_tables:
        t_id = ct.sql_identifier
        selected_cols: list[ColumnContext] = []
        for col in ct.columns:
            fq_col = f"{t_id}.{col.column_name}".lower()
            is_pk = col.is_primary_key or col.column_name in ct.primary_key_column_names
            is_fk = False
            for fk in ct.foreign_keys:
                related_t = fk.to_table_fqn.split(".")[-1].lower()
                if related_t in gold_tables_lower and col.column_name in fk.from_column_names:
                    is_fk = True
            if (
                is_pk
                or is_fk
                or fq_col in gold_cols_lower
                or col.column_name.lower() in gold_cols_lower
            ):
                selected_cols.append(
                    ColumnContext(
                        name=col.column_name,
                        data_type=col.data_type,
                        description=col.description,
                        is_nullable=col.is_nullable if col.is_nullable is not None else True,
                        is_primary_key=is_pk,
                    )
                )

        relevant_rels: list[RelationshipEvidence] = []
        for fk in ct.foreign_keys:
            related_t = fk.to_table_fqn.split(".")[-1].lower()
            if related_t in gold_tables_lower:
                relevant_rels.append(
                    RelationshipEvidence(
                        from_table_fqn=fk.from_table_fqn,
                        from_columns=fk.from_column_names,
                        to_table_fqn=fk.to_table_fqn,
                        to_columns=fk.to_column_names,
                        relationship_type="many_to_one",
                        evidence_summary=fk.relationship_name or fk.provenance,
                    )
                )

        table_contexts.append(
            TableContext(
                fqn=ct.table_fqn,
                sql_identifier=t_id,
                description=ct.description,
                columns=selected_cols,
                relationships=relevant_rels,
            )
        )

    return GroundingContext(
        scope_id="counterfactual_c1",
        tables=table_contexts,
    )


def build_c2_context(
    db_id: str,
    catalog_tables: list[CatalogTable],
) -> GroundingContext:
    """Mechanically construct full schema / maximal context C2."""
    table_contexts: list[TableContext] = []
    for ct in catalog_tables:
        if not ct.sql_identifier:
            continue
        selected_cols = [
            ColumnContext(
                name=col.column_name,
                data_type=col.data_type,
                description=col.description,
                is_nullable=col.is_nullable if col.is_nullable is not None else True,
                is_primary_key=col.is_primary_key or col.column_name in ct.primary_key_column_names,
            )
            for col in ct.columns
        ]
        rels = [
            RelationshipEvidence(
                from_table_fqn=fk.from_table_fqn,
                from_columns=fk.from_column_names,
                to_table_fqn=fk.to_table_fqn,
                to_columns=fk.to_column_names,
                relationship_type="many_to_one",
                evidence_summary=fk.relationship_name or fk.provenance,
            )
            for fk in ct.foreign_keys
        ]
        table_contexts.append(
            TableContext(
                fqn=ct.table_fqn,
                sql_identifier=ct.sql_identifier,
                description=ct.description,
                columns=selected_cols,
                relationships=rels,
            )
        )
    return GroundingContext(
        scope_id="counterfactual_c2",
        tables=table_contexts,
    )


async def run_counterfactual_test(
    sample_cases: list[dict[str, Any]],
    f0_cases_by_id: dict[str, Any],
    db_schemas: dict[str, Any],
) -> dict[str, Any]:
    """Execute C0 vs C1 vs C2 controlled counterfactual comparison."""
    client = OpenAICompatibleChatClient(
        base_url=os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        request_timeout_seconds=60,
        temperature=0.0,
    )
    solver = DirectSqlSolver(
        chat_client=client,
        prompt_builder=DirectSqlPromptBuilder(prompt_version="v002"),
        model_name="openai/gpt-oss-120b",
    )

    all_dbs = {c["inference"]["db_id"] for c in sample_cases}
    catalog_tables_by_db = {
        db_id: load_bird_catalog_tables(db_id=db_id, tables_json_path=MINI_DEV_TABLES_PATH)
        for db_id in all_dbs
    }

    pb = DirectSqlPromptBuilder(prompt_version="v002")
    trials: list[dict[str, Any]] = []

    for idx, c in enumerate(sample_cases, 1):
        cid = c["case_id"]
        db_id = c["inference"]["db_id"]
        question = c["inference"]["question"]
        gold_sql = c["gold"]["sql_original"]
        db_path = OFFICIAL_DB_ROOT / db_id / f"{db_id}.sqlite"
        print(f"  Running counterfactual case {idx}/{len(sample_cases)}: {cid} ({db_id})...")

        gold_tables, gold_cols = extract_gold_schema(gold_sql, db_id, db_schemas)

        c0_record = f0_cases_by_id[cid]
        c0_correct = c0_record.get("execution_correct")
        c0_sql = c0_record.get("generated_sql")

        c1_context = build_c1_context(
            db_id=db_id,
            gold_tables=gold_tables,
            gold_cols=gold_cols,
            catalog_tables=catalog_tables_by_db[db_id],
        )
        c1_schema_str = pb._format_authorized_schema(c1_context)

        c2_context = build_c2_context(
            db_id=db_id,
            catalog_tables=catalog_tables_by_db[db_id],
        )
        c2_schema_str = pb._format_authorized_schema(c2_context)

        # C1 minimal context execution
        c1_req = SolverRequest(
            run_id=f"counterfactual_c1_{cid}",
            query_request=QueryRequest(question=question, database_dialect="sqlite"),
            target_dialect="sqlite",
            grounding_context=c1_context,
            generation_settings=SolverGenerationSettings(max_output_tokens=1024),
        )
        t0 = time.perf_counter()
        try:
            c1_cand = await solver.generate_sql_candidate(c1_req)
            c1_sql = c1_cand.sql
            c1_time_ms = round((time.perf_counter() - t0) * 1000, 1)
            c1_correct = score_query_against_db(c1_sql, gold_sql, db_path)
            c1_status = "SUCCESS"
        except Exception as e:
            c1_sql = None
            c1_time_ms = round((time.perf_counter() - t0) * 1000, 1)
            c1_correct = False
            c1_status = f"ERROR: {type(e).__name__}"

        # C2 maximal context execution
        c2_req = SolverRequest(
            run_id=f"counterfactual_c2_{cid}",
            query_request=QueryRequest(question=question, database_dialect="sqlite"),
            target_dialect="sqlite",
            grounding_context=c2_context,
            generation_settings=SolverGenerationSettings(max_output_tokens=1024),
        )
        t0 = time.perf_counter()
        try:
            c2_cand = await solver.generate_sql_candidate(c2_req)
            c2_sql = c2_cand.sql
            c2_time_ms = round((time.perf_counter() - t0) * 1000, 1)
            c2_correct = score_query_against_db(c2_sql, gold_sql, db_path)
            c2_status = "SUCCESS"
        except Exception as e:
            c2_sql = None
            c2_time_ms = round((time.perf_counter() - t0) * 1000, 1)
            c2_correct = False
            c2_status = f"ERROR: {type(e).__name__}"

        trial = {
            "case_id": cid,
            "db_id": db_id,
            "stratum": c["gold"]["stratum"],
            "question": question,
            "gold_sql": gold_sql,
            "c0_current": {
                "tables_count": len(c0_record.get("baseline_tables", [])),
                "correct": c0_correct is True,
                "status": c0_record.get("runtime_status"),
                "sql": c0_sql,
            },
            "c1_minimal": {
                "tables_count": len(c1_context.tables),
                "columns_count": sum(len(t.columns) for t in c1_context.tables),
                "schema_chars": len(c1_schema_str),
                "correct": c1_correct is True,
                "status": c1_status,
                "latency_ms": c1_time_ms,
                "sql": c1_sql,
            },
            "c2_maximal": {
                "tables_count": len(c2_context.tables),
                "columns_count": sum(len(t.columns) for t in c2_context.tables),
                "schema_chars": len(c2_schema_str),
                "correct": c2_correct is True,
                "status": c2_status,
                "latency_ms": c2_time_ms,
                "sql": c2_sql,
            },
        }
        trials.append(trial)

    c0_correct_cnt = sum(1 for t in trials if t["c0_current"]["correct"])
    c1_correct_cnt = sum(1 for t in trials if t["c1_minimal"]["correct"])
    c2_correct_cnt = sum(1 for t in trials if t["c2_maximal"]["correct"])
    n = len(trials)

    return {
        "governed_sample_size": n,
        "selection_rule": (
            "Stratified sample: lowest-numbered case_id per stratum S1-S4 "
            "across distinct databases"
        ),
        "c0_current_accuracy": round(c0_correct_cnt / n, 4),
        "c1_minimal_accuracy": round(c1_correct_cnt / n, 4),
        "c2_maximal_accuracy": round(c2_correct_cnt / n, 4),
        "counts": {
            "c0_correct": c0_correct_cnt,
            "c1_correct": c1_correct_cnt,
            "c2_correct": c2_correct_cnt,
            "total": n,
        },
        "pairwise_transitions": {
            "c0_false_to_c1_true_recoveries": [
                t["case_id"]
                for t in trials
                if not t["c0_current"]["correct"] and t["c1_minimal"]["correct"]
            ],
            "c1_true_to_c2_false_regressions": [
                t["case_id"]
                for t in trials
                if t["c1_minimal"]["correct"] and not t["c2_maximal"]["correct"]
            ],
            "c0_true_to_c1_false_regressions": [
                t["case_id"]
                for t in trials
                if t["c0_current"]["correct"] and not t["c1_minimal"]["correct"]
            ],
        },
        "trials": trials,
    }


def score_query_against_db(candidate_sql: str | None, gold_sql: str, db_path: Path) -> bool:
    if not candidate_sql or not candidate_sql.strip():
        return False
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(gold_sql)
        gold_rows = cur.fetchall()
        cur.execute(candidate_sql)
        cand_rows = cur.fetchall()
        return score_execution_accuracy(
            generated_rows=cand_rows,
            gold_rows=gold_rows,
            gold_sql=gold_sql,
        )
    except Exception:
        return False
    finally:
        conn.close()


def run_full_audit():
    print("=== Agent 02: Context Noise & Representation Audit Started ===")
    git_commit, git_status = get_git_info()
    print(f"Git commit: {git_commit}")
    print(f"Git status dirty files: {len(git_status.splitlines()) if git_status else 0}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Step 1: Collecting context statistics across all 85 benchmark cases...")
    metrics_list = collect_context_statistics()

    with open(OUTPUT_STATS_PATH, "w") as f:
        for m in metrics_list:
            f.write(json.dumps(asdict(m)) + "\n")
    print(f"Wrote {len(metrics_list)} case context records to {OUTPUT_STATS_PATH}")

    n = len(metrics_list)
    correct_cases = [m for m in metrics_list if m.execution_correct is True]
    failed_cases = [m for m in metrics_list if m.execution_correct is not True]

    avg_tables_sent = sum(m.tables_sent for m in metrics_list) / n
    avg_tables_req = sum(m.gold_tables_count for m in metrics_list) / n
    avg_cols_sent = sum(m.columns_sent for m in metrics_list) / n
    avg_cols_req = sum(m.gold_cols_count for m in metrics_list) / n
    avg_prec_tab = sum(m.context_precision_tables for m in metrics_list) / n
    avg_rec_tab = sum(m.context_recall_tables for m in metrics_list) / n
    avg_prec_col = sum(m.context_precision_columns for m in metrics_list) / n
    avg_rec_col = sum(m.context_recall_columns for m in metrics_list) / n
    avg_tab_dist = sum(m.table_distractor_ratio for m in metrics_list) / n
    avg_col_dist = sum(m.column_distractor_ratio for m in metrics_list) / n
    avg_schema_chars = sum(m.serialized_context_chars for m in metrics_list) / n
    avg_dup_rels = sum(m.duplicate_relationships for m in metrics_list) / n

    y_corr = [1.0 if m.execution_correct is True else 0.0 for m in metrics_list]
    x_col_dist = [m.column_distractor_ratio for m in metrics_list]
    x_tab_dist = [m.table_distractor_ratio for m in metrics_list]
    x_cols_sent = [float(m.columns_sent) for m in metrics_list]
    x_schema_chars = [float(m.serialized_context_chars) for m in metrics_list]

    r_col_dist, t_col_dist = pearson_correlation(x_col_dist, y_corr)
    r_tab_dist, t_tab_dist = pearson_correlation(x_tab_dist, y_corr)
    r_cols_sent, t_cols_sent = pearson_correlation(x_cols_sent, y_corr)
    r_schema_chars, t_schema_chars = pearson_correlation(x_schema_chars, y_corr)

    print("Step 2: Selecting mechanically governed sample for counterfactual test...")
    cases = [json.loads(line) for line in open(PILOT_DATASET_PATH)]
    sql_cases = [c for c in cases if c["gold"].get("sql_original")]
    f0_cases_by_id = {json.loads(line)["case_id"]: json.loads(line) for line in open(F0_CASES_PATH)}
    db_schemas = load_db_schemas()

    by_stratum = defaultdict(list)
    for c in sql_cases:
        by_stratum[c["gold"]["stratum"]].append(c)

    sample_cases = []
    for s in ["S1", "S2", "S3", "S4"]:
        used_dbs: set[str] = set()
        for c in by_stratum[s]:
            db = c["inference"]["db_id"]
            if (
                db not in used_dbs
                and len([x for x in sample_cases if x["gold"]["stratum"] == s]) < 3
            ):
                used_dbs.add(db)
                sample_cases.append(c)

    print(f"Sample size: {len(sample_cases)} cases across strata S1-S4")

    print("Step 3: Running Controlled Counterfactual Test (C0 vs C1 vs C2)...")
    counterfactual_results = asyncio.run(
        run_counterfactual_test(sample_cases, f0_cases_by_id, db_schemas)
    )

    with open(OUTPUT_COUNTERFACTUAL_PATH, "w") as f:
        json.dump(counterfactual_results, f, indent=2)
    print(f"Wrote counterfactual metrics to {OUTPUT_COUNTERFACTUAL_PATH}")

    # Build manifest
    manifest = {
        "audit_name": "agent_02_context_noise_and_representation",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "git_dirty": bool(git_status),
        "prompt_hashes": {
            "v001_system.md": get_file_sha256(ROOT_DIR / "prompts/direct_sql/v001_system.md"),
            "v001_user_template.md": get_file_sha256(
                ROOT_DIR / "prompts/direct_sql/v001_user_template.md"
            ),
            "v002_system.md": get_file_sha256(ROOT_DIR / "prompts/direct_sql/v002_system.md"),
            "v002_user_template.md": get_file_sha256(
                ROOT_DIR / "prompts/direct_sql/v002_user_template.md"
            ),
            "v003_system.md": get_file_sha256(ROOT_DIR / "prompts/direct_sql/v003_system.md"),
            "v003_user_template.md": get_file_sha256(
                ROOT_DIR / "prompts/direct_sql/v003_user_template.md"
            ),
        },
        "dataset": {
            "path": str(PILOT_DATASET_PATH.relative_to(ROOT_DIR)),
            "sha256": get_file_sha256(PILOT_DATASET_PATH),
            "total_cases_analyzed": n,
        },
        "solver": {
            "model": "openai/gpt-oss-120b",
            "provider": "openai_compatible",
            "temperature": 0.0,
            "max_output_tokens": 1024,
            "prompt_version": "v002",
        },
        "aggregate_metrics": {
            "avg_tables_available": round(sum(m.tables_available for m in metrics_list) / n, 2),
            "avg_tables_sent": round(avg_tables_sent, 2),
            "avg_tables_required": round(avg_tables_req, 2),
            "avg_columns_sent": round(avg_cols_sent, 2),
            "avg_columns_required": round(avg_cols_req, 2),
            "context_precision_tables": round(avg_prec_tab, 4),
            "context_recall_tables": round(avg_rec_tab, 4),
            "context_precision_columns": round(avg_prec_col, 4),
            "context_recall_columns": round(avg_rec_col, 4),
            "table_distractor_ratio": round(avg_tab_dist, 4),
            "column_distractor_ratio": round(avg_col_dist, 4),
            "avg_schema_chars": round(avg_schema_chars, 1),
            "avg_duplicate_relationships": round(avg_dup_rels, 2),
            "full_database_tables_sent_count": sum(
                1 for m in metrics_list if m.fallback_sent_full_schema
            ),
            "full_database_tables_sent_pct": round(
                sum(1 for m in metrics_list if m.fallback_sent_full_schema) / n * 100, 2
            ),
            "correlations_with_execution_correctness": {
                "column_distractor_ratio": {"r": round(r_col_dist, 4), "t": round(t_col_dist, 2)},
                "table_distractor_ratio": {"r": round(r_tab_dist, 4), "t": round(t_tab_dist, 2)},
                "columns_sent": {"r": round(r_cols_sent, 4), "t": round(t_cols_sent, 2)},
                "schema_chars": {"r": round(r_schema_chars, 4), "t": round(t_schema_chars, 2)},
            },
            "subgroups": {
                "correct_cases": {
                    "count": len(correct_cases),
                    "avg_columns_sent": round(
                        sum(m.columns_sent for m in correct_cases) / len(correct_cases), 1
                    ),
                    "avg_column_precision": round(
                        sum(m.context_precision_columns for m in correct_cases)
                        / len(correct_cases),
                        4,
                    ),
                    "avg_column_distractor_ratio": round(
                        sum(m.column_distractor_ratio for m in correct_cases) / len(correct_cases),
                        4,
                    ),
                    "avg_relevant_evidence_rank": round(
                        sum(
                            m.relevant_evidence_rank
                            for m in correct_cases
                            if m.relevant_evidence_rank
                        )
                        / len([m for m in correct_cases if m.relevant_evidence_rank]),
                        2,
                    ),
                },
                "failed_cases": {
                    "count": len(failed_cases),
                    "avg_columns_sent": round(
                        sum(m.columns_sent for m in failed_cases) / len(failed_cases), 1
                    ),
                    "avg_column_precision": round(
                        sum(m.context_precision_columns for m in failed_cases) / len(failed_cases),
                        4,
                    ),
                    "avg_column_distractor_ratio": round(
                        sum(m.column_distractor_ratio for m in failed_cases) / len(failed_cases), 4
                    ),
                    "avg_relevant_evidence_rank": round(
                        sum(
                            m.relevant_evidence_rank
                            for m in failed_cases
                            if m.relevant_evidence_rank
                        )
                        / len([m for m in failed_cases if m.relevant_evidence_rank]),
                        2,
                    ),
                },
            },
        },
        "counterfactual_summary": {
            "c0_accuracy": counterfactual_results["c0_current_accuracy"],
            "c1_accuracy": counterfactual_results["c1_minimal_accuracy"],
            "c2_accuracy": counterfactual_results["c2_maximal_accuracy"],
            "ordering": (
                "C1 > C0 > C2"
                if counterfactual_results["c1_minimal_accuracy"]
                > counterfactual_results["c0_current_accuracy"]
                >= counterfactual_results["c2_maximal_accuracy"]
                else (
                    f"C1={counterfactual_results['c1_minimal_accuracy']}, "
                    f"C0={counterfactual_results['c0_current_accuracy']}, "
                    f"C2={counterfactual_results['c2_maximal_accuracy']}"
                )
            ),
        },
    }

    with open(OUTPUT_MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote audit manifest to {OUTPUT_MANIFEST_PATH}")
    print("=== Agent 02 Audit Complete ===")


if __name__ == "__main__":
    run_full_audit()
