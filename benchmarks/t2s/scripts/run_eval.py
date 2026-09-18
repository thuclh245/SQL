#!/usr/bin/env python3
"""T2S Evaluation Runner — baseline evaluation against t2s_eval_v1.jsonl.

Usage:
    .venv/bin/python benchmarks/t2s/scripts/run_eval.py [options]

Environment variables (required):
    OPENAI_API_KEY or LLM_API_KEY — API key for the Chat completion backend.

Optional environment variables:
    LLM_BASE_URL  — defaults to https://api.openai.com/v1
    LLM_MODEL     — defaults to gpt-4o-mini

Output:
    benchmarks/t2s/runs/<run_id>/results.jsonl   — per-case raw results
    benchmarks/t2s/runs/<run_id>/report.json     — aggregate and slice metrics
    Printed to terminal: slice report table
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# Sys-path bootstrap so we can run as a script without installing the package
# ---------------------------------------------------------------------------
_repo_src = Path(__file__).resolve().parents[3] / "src"
if str(_repo_src) not in sys.path:
    sys.path.insert(0, str(_repo_src))

from t2s.catalog import (  # noqa: E402
    CatalogColumn,
    CatalogForeignKey,
    CatalogSearchDocumentBuilder,
    CatalogTable,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog  # noqa: E402
from t2s.contracts import QueryRequest  # noqa: E402
from t2s.database import QueryExecutionPolicy  # noqa: E402
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor  # noqa: E402
from t2s.grounding import (  # noqa: E402
    GroundingBudget,
    GroundingContextBuilder,
    SchemaRetriever,
)
from t2s.grounding.schema_retriever import InMemorySchemaSearch  # noqa: E402

# ---------------------------------------------------------------------------
# LLM client: reuse VllmChatClient pointing at OpenAI API
# ---------------------------------------------------------------------------
from t2s.integrations.vllm import VllmChatClient  # noqa: E402
from t2s.orchestration import (  # noqa: E402
    AdaptiveOrchestrator,
    EscalationBudget,
    EscalationPolicy,
)
from t2s.runtime import RuntimeStatus, TextToSqlRuntime  # noqa: E402
from t2s.security import (  # noqa: E402
    AuthorizationService,
    AuthorizedSqlResource,
    UserIdentity,
)
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver  # noqa: E402
from t2s.verification import SqlAccessValidator, SqlAstParser, SqlSafetyValidator  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_BENCHMARKS_T2S = Path(__file__).resolve().parents[1]  # benchmarks/t2s/
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # /home/.../SQL/

OFFICIAL_DB_ROOT = _BENCHMARKS_T2S / "databases" / "official"
TABLES_JSON = _PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
EVAL_DATASET = _BENCHMARKS_T2S / "datasets" / "t2s_eval_v1.jsonl"
RUNS_DIR = _BENCHMARKS_T2S / "runs"
PROMPTS_DIR = _PROJECT_ROOT / "prompts" / "direct_sql"

BENCHMARK_IDENTITY = "t2s_eval_v1"
BENCHMARK_SOURCE_SHA256 = "4ba5fa8de55856222f484d380d2ba872b380bf79d825de70478e2120cb0fc43b"


# ---------------------------------------------------------------------------
# Open-access policy: for benchmark mode allow all tables in the target DB.
# This avoids needing per-case authorization configuration while keeping
# the safety (P1 SQL AST verification) and execution layers fully active.
# ---------------------------------------------------------------------------
class AllTablesAccessPolicy:
    """Grants access to all known tables in the current catalog.

    Registers both the short sql_identifier (e.g. 'schools') and the
    dot-separated FQN tail (e.g. 'california_schools.main.schools') so that
    SQL generated with either form passes the authorization check.
    """

    def __init__(self, catalog: InMemoryCatalog) -> None:
        self._catalog = catalog

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        resources = []
        for fqn in self._catalog.list_table_fqns():
            table = self._catalog.get_table_by_fqn(fqn)
            if table.sql_identifier:
                # Short form: 'schools'
                resources.append(
                    AuthorizedSqlResource(
                        catalog_fqn=fqn,
                        sql_identifier=table.sql_identifier,
                    )
                )
                # FQN form: 'california_schools.main.schools' — model may generate this
                resources.append(
                    AuthorizedSqlResource(
                        catalog_fqn=fqn,
                        sql_identifier=fqn,
                    )
                )
        return resources


# ---------------------------------------------------------------------------
# Schema loader: build CatalogTable objects from mini_dev_tables.json
# ---------------------------------------------------------------------------


def _load_catalog_tables(db_id: str, tables_json_path: Path) -> list[CatalogTable]:
    """Parse BIRD mini_dev_tables.json and return CatalogTable list for db_id."""
    all_dbs = json.loads(tables_json_path.read_text(encoding="utf-8"))
    db_entry = next((d for d in all_dbs if d["db_id"] == db_id), None)
    if db_entry is None:
        raise ValueError(f"Database '{db_id}' not found in {tables_json_path}")

    table_names_orig: list[str] = db_entry["table_names_original"]
    table_names_clean: list[str] = db_entry.get("table_names", table_names_orig)
    col_names_orig: list[list[Any]] = db_entry["column_names_original"]
    col_names_clean: list[list[Any]] = db_entry.get("column_names", col_names_orig)
    col_types: list[str] = db_entry["column_types"]
    primary_keys: list[Any] = db_entry.get("primary_keys", [])
    foreign_keys: list[list[int]] = db_entry.get("foreign_keys", [])

    # Build pk set (flat, handles both int and list-of-int entries)
    pk_col_indices: set[int] = set()
    for pk in primary_keys:
        if isinstance(pk, int):
            pk_col_indices.add(pk)
        elif isinstance(pk, list):
            for p in pk:
                pk_col_indices.add(p)

    # Group columns by table index (skip index 0 = '*' sentinel)
    table_cols: dict[int, list[CatalogColumn]] = {i: [] for i in range(len(table_names_orig))}
    col_idx_to_table_col: dict[int, tuple[int, str]] = {}  # col_global_idx -> (table_idx, col_name)

    for global_idx, (table_idx, col_name) in enumerate(col_names_orig):
        if table_idx == -1:  # '*' sentinel
            continue
        data_type = col_types[global_idx] if global_idx < len(col_types) else "text"
        is_pk = global_idx in pk_col_indices
        fqn = f"{db_id}.main.{table_names_orig[table_idx]}.{col_name}"
        desc = (
            col_names_clean[global_idx][1]
            if global_idx < len(col_names_clean) and col_names_clean[global_idx][1] != col_name
            else None
        )
        cat_col = CatalogColumn(
            column_fqn=fqn,
            column_name=col_name,
            data_type=data_type,
            is_primary_key=is_pk,
            description=desc,
        )
        table_cols[table_idx].append(cat_col)
        col_idx_to_table_col[global_idx] = (table_idx, col_name)

    # Build FK -> CatalogForeignKey mapping, keyed by from_table_idx -> list
    table_fks: dict[int, list[CatalogForeignKey]] = defaultdict(list)
    for fk_from_idx, fk_to_idx in foreign_keys:
        from_info = col_idx_to_table_col.get(fk_from_idx)
        to_info = col_idx_to_table_col.get(fk_to_idx)
        if from_info is None or to_info is None:
            continue
        from_table_idx, from_col_name = from_info
        to_table_idx, to_col_name = to_info
        from_table_name = table_names_orig[from_table_idx]
        to_table_name = table_names_orig[to_table_idx]
        cat_fk = CatalogForeignKey(
            from_table_fqn=f"{db_id}.main.{from_table_name}",
            from_column_names=[from_col_name],
            to_table_fqn=f"{db_id}.main.{to_table_name}",
            to_column_names=[to_col_name],
            provenance="declared_foreign_key",
        )
        table_fks[from_table_idx].append(cat_fk)

    # Assemble CatalogTable objects
    catalog_tables = []
    for table_idx, table_name in enumerate(table_names_orig):
        fqn = f"{db_id}.main.{table_name}"
        t_desc = (
            table_names_clean[table_idx]
            if table_idx < len(table_names_clean) and table_names_clean[table_idx] != table_name
            else None
        )
        cat_table = CatalogTable(
            table_fqn=fqn,
            service_name=db_id,
            database_name=db_id,
            schema_name="main",
            table_name=table_name,
            sql_identifier=table_name,
            sql_identifier_source="explicit",
            description=t_desc,
            columns=table_cols[table_idx],
            foreign_keys=table_fks.get(table_idx, []),
        )
        catalog_tables.append(cat_table)

    return catalog_tables


# ---------------------------------------------------------------------------
# Runtime factory — built once per database to avoid re-building the catalog
# ---------------------------------------------------------------------------


def _build_runtime_for_db(
    db_id: str,
    db_path: Path,
    tables_json_path: Path,
    llm_client: VllmChatClient,
    model_name: str,
    prompts_dir: Path,
) -> TextToSqlRuntime:
    catalog_tables = _load_catalog_tables(db_id, tables_json_path)

    catalog = InMemoryCatalog()
    catalog.upsert_tables(catalog_tables)

    doc_builder = CatalogSearchDocumentBuilder()
    search_docs = [
        doc for table in catalog_tables for doc in doc_builder.build_search_documents(table)
    ]
    search_index = InMemorySchemaSearch(search_docs)
    schema_retriever = SchemaRetriever(search_index)

    access_policy = AllTablesAccessPolicy(catalog)
    auth_service = AuthorizationService(access_policy)

    grounding_builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=schema_retriever,
        authorization_service=auth_service,
        grounding_budget=GroundingBudget(
            max_candidate_tables=50,
            max_hydrated_tables=10,
            max_columns_per_table=50,
            max_total_columns=200,
        ),
    )

    solver = DirectSqlSolver(
        chat_client=llm_client,
        prompt_builder=DirectSqlPromptBuilder(prompt_directory=prompts_dir),
        model_name=model_name,
    )

    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=grounding_builder,
        solver=solver,
        escalation_policy=EscalationPolicy(),
        escalation_budget=EscalationBudget(max_escalations=1),
    )

    executor = SqliteReadOnlyQueryExecutor(db_path)

    return TextToSqlRuntime(
        adaptive_orchestrator=orchestrator,
        sql_ast_parser=SqlAstParser(),
        sql_safety_validator=SqlSafetyValidator(),
        sql_access_validator=SqlAccessValidator(auth_service),
        query_executor=executor,
        execution_policy=QueryExecutionPolicy(
            read_only_required=True,
            maximum_result_rows=1000,
        ),
        default_dialect="sqlite",
    )


# ---------------------------------------------------------------------------
# Execution Accuracy scorer
# ---------------------------------------------------------------------------


def _normalize_result(rows: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    """Sort rows by their string representation for order-insensitive comparison."""
    return sorted([tuple(str(v) for v in row.values()) for row in rows])


def _execute_gold_sql(gold_sql: str, db_path: Path) -> list[tuple[Any, ...]] | None:
    """Execute gold SQL in read-only mode, return rows or None on error."""
    uri = f"file:{db_path.resolve()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            con.execute("PRAGMA query_only = ON")
            rows = con.execute(gold_sql).fetchall()
            return rows
        finally:
            con.close()
    except Exception:
        return None


def _score_execution_accuracy(
    predicted_rows: list[dict[str, Any]],
    gold_rows: list[tuple[Any, ...]],
) -> bool:
    """Return True when predicted results match gold (order-insensitive, type-coerced)."""
    pred_normalized = sorted([tuple(str(v) for v in row.values()) for row in predicted_rows])
    gold_normalized = sorted([tuple(str(v) for v in row) for row in gold_rows])
    return pred_normalized == gold_normalized


# ---------------------------------------------------------------------------
# Per-case runner
# ---------------------------------------------------------------------------


async def _run_single_case(
    case: dict[str, Any],
    runtime: TextToSqlRuntime,
    gold_rows: list[tuple[Any, ...]] | None,
    run_id_prefix: str,
) -> dict[str, Any]:
    case_id = case["case_id"]
    question = case["inference"]["question"]
    db_id = case["inference"]["db_id"]
    evidence = case["inference"].get("evidence", "")
    t2s_stratum = case.get("t2s_stratum") or case.get("gold", {}).get("stratum", "?")
    bird_difficulty = case.get("bird_difficulty") or case.get("gold", {}).get(
        "bird_difficulty", "?"
    )

    # Compose question with evidence if available
    full_question = question
    if evidence and evidence.strip():
        full_question = f"{question}\n\nNote: {evidence.strip()}"

    target_hint = (
        "In SQLite, write table names exactly as given by sql_identifier without catalog "
        "or schema prefixes (e.g., use table_name, not db.schema.table_name). "
        "Always enclose column names containing spaces or special characters in double quotes."
    )

    query_req = QueryRequest(
        question=full_question,
        database_dialect="sqlite",
        target_hint=target_hint,
        client_request_id=case_id,
    )

    user_identity = UserIdentity(user_id="benchmark-runner", tenant_id="eval-v1")
    case_run_id = f"{run_id_prefix}_{case_id}"

    t_start = time.perf_counter()
    try:
        result = await runtime.execute_query_pipeline(
            query_request=query_req,
            user_identity=user_identity,
            run_id=case_run_id,
        )
        latency_ms = round((time.perf_counter() - t_start) * 1000, 1)

        # Compute EX_official
        ex_official: bool | None = None
        if result.status == RuntimeStatus.COMPLETED and gold_rows is not None:
            ex_official = _score_execution_accuracy(result.rows, gold_rows)
        elif result.status == RuntimeStatus.COMPLETED and gold_rows is None:
            ex_official = None  # gold execution failed

        return {
            "case_id": case_id,
            "db_id": db_id,
            "t2s_stratum": t2s_stratum,
            "bird_difficulty": bird_difficulty,
            "runtime_status": result.status.value,
            "sql_generated": result.sql,
            "row_count": result.row_count,
            "ex_official": ex_official,
            "orchestration_outcome": (
                result.orchestration_outcome.value if result.orchestration_outcome else None
            ),
            "escalation_triggered": (
                len(result.trace.orchestration_trace.escalation_records) > 0
                if result.trace.orchestration_trace
                else False
            ),
            "safety_check_passed": result.trace.safety_check_passed,
            "access_check_passed": result.trace.access_check_passed,
            "execution_passed": result.trace.execution_passed,
            "latency_ms": latency_ms,
            "error_message": result.error_message,
            "warnings": result.warnings,
            "gold_sql": case.get("bird_gold_sql") or case.get("gold", {}).get("sql_original"),
        }

    except Exception as exc:
        latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return {
            "case_id": case_id,
            "db_id": db_id,
            "t2s_stratum": t2s_stratum,
            "bird_difficulty": bird_difficulty,
            "runtime_status": "runner_exception",
            "sql_generated": None,
            "row_count": 0,
            "ex_official": False,
            "orchestration_outcome": None,
            "escalation_triggered": False,
            "safety_check_passed": False,
            "access_check_passed": False,
            "execution_passed": False,
            "latency_ms": latency_ms,
            "error_message": f"{type(exc).__name__}: {exc}",
            "warnings": [],
            "gold_sql": case.get("bird_gold_sql") or case.get("gold", {}).get("sql_original"),
        }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def _build_report(
    results: list[dict[str, Any]],
    run_id: str,
    args: argparse.Namespace,
    model_name: str,
) -> dict[str, Any]:
    total = len(results)
    completed = [r for r in results if r["runtime_status"] == "completed"]
    answered = len(completed)

    ex_candidates = [r for r in results if r["ex_official"] is not None]
    ex_correct = sum(1 for r in ex_candidates if r["ex_official"] is True)

    def ex_pct(correct: int, total_n: int) -> float:
        return round(correct / total_n * 100, 1) if total_n else 0.0

    # Slices by stratum
    strata = ["S1", "S2", "S3", "S4"]
    by_stratum: dict[str, Any] = {}
    for s in strata:
        s_results = [r for r in results if r["t2s_stratum"] == s]
        s_candidates = [r for r in s_results if r["ex_official"] is not None]
        s_correct = sum(1 for r in s_candidates if r["ex_official"] is True)
        by_stratum[s] = {
            "count": len(s_results),
            "ex_correct": s_correct,
            "ex_total": len(s_candidates),
            "ex_pct": ex_pct(s_correct, len(s_candidates)),
        }

    # Slices by BIRD difficulty
    diffs = ["simple", "moderate", "challenging"]
    by_difficulty: dict[str, Any] = {}
    for d in diffs:
        d_results = [r for r in results if r["bird_difficulty"] == d]
        d_candidates = [r for r in d_results if r["ex_official"] is not None]
        d_correct = sum(1 for r in d_candidates if r["ex_official"] is True)
        by_difficulty[d] = {
            "count": len(d_results),
            "ex_correct": d_correct,
            "ex_total": len(d_candidates),
            "ex_pct": ex_pct(d_correct, len(d_candidates)),
        }

    # Slices by database
    db_results_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        db_results_map[r["db_id"]].append(r)
    by_database: dict[str, Any] = {}
    for db_id, db_res in sorted(db_results_map.items()):
        db_candidates = [r for r in db_res if r["ex_official"] is not None]
        db_correct = sum(1 for r in db_candidates if r["ex_official"] is True)
        by_database[db_id] = {
            "count": len(db_res),
            "ex_correct": db_correct,
            "ex_total": len(db_candidates),
            "ex_pct": ex_pct(db_correct, len(db_candidates)),
        }

    # Runtime status taxonomy
    status_counter = dict(Counter(r["runtime_status"] for r in results))

    # Orchestration
    escalated = sum(1 for r in results if r["escalation_triggered"])
    escalated_success = sum(
        1 for r in results if r["escalation_triggered"] and r["ex_official"] is True
    )

    # Latency
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] is not None]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    min_latency = min(latencies) if latencies else 0.0

    return {
        "run_id": run_id,
        "benchmark": BENCHMARK_IDENTITY,
        "benchmark_source_sha256": BENCHMARK_SOURCE_SHA256,
        "model": model_name,
        "llm_base_url": args.llm_base_url,
        "timestamp": datetime.now(UTC).isoformat(),
        "dataset": str(args.eval_dataset),
        "total_cases": total,
        "overall": {
            "answered_count": answered,
            "ex_correct": ex_correct,
            "ex_total": len(ex_candidates),
            "ex_pct": ex_pct(ex_correct, len(ex_candidates)),
            "abstain_count": total - answered,
        },
        "by_stratum": by_stratum,
        "by_difficulty": by_difficulty,
        "by_database": by_database,
        "runtime_failures": {
            "status_breakdown": status_counter,
            "safety_rejections": sum(
                1 for r in results if r["runtime_status"] == "safety_rejected"
            ),
            "access_denied": sum(1 for r in results if r["runtime_status"] == "access_denied"),
            "execution_failed": sum(
                1 for r in results if r["runtime_status"] == "execution_failed"
            ),
            "unresolved": sum(1 for r in results if r["runtime_status"] == "unresolved"),
            "generation_failed": sum(
                1 for r in results if r["runtime_status"] == "generation_failed"
            ),
        },
        "orchestration": {
            "escalation_count": escalated,
            "escalation_rate_pct": ex_pct(escalated, total),
            "success_after_escalation_count": escalated_success,
            "success_after_escalation_rate_pct": (
                ex_pct(escalated_success, escalated) if escalated else 0.0
            ),
        },
        "latency_ms": {
            "average": avg_latency,
            "min": min_latency,
            "max": max_latency,
        },
    }


def _print_slice_report(report: dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print(f"T2S Baseline Evaluation — {report['benchmark']}")
    print(f"Model: {report['model']}")
    print(f"Run ID: {report['run_id']}")
    print(f"Timestamp: {report['timestamp']}")
    print("=" * 70)

    ov = report["overall"]
    print(f"\nOverall EX: {ov['ex_correct']}/{ov['ex_total']} = {ov['ex_pct']}%")
    print(
        f"Answered: {ov['answered_count']}/{report['total_cases']}  "
        f"Abstained: {ov['abstain_count']}"
    )

    print("\n--- By T2S Stratum ---")
    for s, v in report["by_stratum"].items():
        print(f"  {s}: {v['ex_correct']}/{v['ex_total']} = {v['ex_pct']}%  (N={v['count']})")

    print("\n--- By BIRD Difficulty ---")
    for d, v in report["by_difficulty"].items():
        print(f"  {d:12s}: {v['ex_correct']}/{v['ex_total']} = {v['ex_pct']}%  (N={v['count']})")

    print("\n--- By Database ---")
    for db, v in sorted(report["by_database"].items()):
        print(f"  {db:30s}: {v['ex_correct']}/{v['ex_total']} = {v['ex_pct']}%")

    orch = report["orchestration"]
    print("\n--- Orchestration ---")
    print(f"  Escalations: {orch['escalation_count']} ({orch['escalation_rate_pct']}%)")
    print(
        f"  Success after escalation: {orch['success_after_escalation_count']} "
        f"({orch['success_after_escalation_rate_pct']}%)"
    )

    lat = report["latency_ms"]
    print("\n--- Latency ---")
    print(f"  avg={lat['average']}ms  min={lat['min']}ms  max={lat['max']}ms")

    rf = report["runtime_failures"]
    print("\n--- Runtime Status Breakdown ---")
    for status, count in sorted(rf["status_breakdown"].items()):
        print(f"  {status:25s}: {count}")

    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def _async_main(args: argparse.Namespace) -> None:
    # Resolve API key
    llm_api_key = args.api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not llm_api_key:
        print("ERROR: No LLM API key found. Set OPENAI_API_KEY or LLM_API_KEY.", file=sys.stderr)
        raise SystemExit(1)

    # Load evaluation dataset
    eval_path = Path(args.eval_dataset)
    if not eval_path.exists():
        print(f"ERROR: Evaluation dataset not found: {eval_path}", file=sys.stderr)
        raise SystemExit(1)

    eval_cases = [
        json.loads(line)
        for line in eval_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        eval_cases = eval_cases[: args.limit]
        print(f"[INFO] Limiting to {args.limit} cases for smoke test.")

    print(f"[INFO] Loaded {len(eval_cases)} cases from {eval_path.name}.")

    # Setup run output directory
    run_id = f"eval_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{str(uuid4())[:8]}"
    run_dir = Path(args.runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.jsonl"
    report_path = run_dir / "report.json"

    print(f"[INFO] Run ID: {run_id}")
    print(f"[INFO] Output: {run_dir}")
    print(f"[INFO] Model: {args.model}  Base URL: {args.llm_base_url}")

    # Build shared LLM client
    llm_client = VllmChatClient(
        base_url=args.llm_base_url,
        api_key=llm_api_key,
        request_timeout_seconds=args.timeout,
    )

    db_root = Path(args.db_root)
    tables_json = Path(args.tables_json)
    prompts_dir = Path(args.prompts_dir)

    # Cache runtimes by db_id
    runtime_cache: dict[str, TextToSqlRuntime] = {}
    results: list[dict[str, Any]] = []

    total = len(eval_cases)
    print(f"\n[INFO] Starting evaluation — {total} cases...")

    with results_path.open("w", encoding="utf-8") as results_file:
        for idx, case in enumerate(eval_cases, 1):
            db_id = case["inference"]["db_id"]
            gold_sql = case.get("bird_gold_sql") or case.get("gold", {}).get("sql_original")

            # Ensure runtime is built for this DB
            if db_id not in runtime_cache:
                db_path = db_root / db_id / f"{db_id}.sqlite"
                runtime_cache[db_id] = _build_runtime_for_db(
                    db_id=db_id,
                    db_path=db_path,
                    tables_json_path=tables_json,
                    llm_client=llm_client,
                    model_name=args.model,
                    prompts_dir=prompts_dir,
                )

            runtime = runtime_cache[db_id]

            # Execute gold SQL for ground truth
            db_path = db_root / db_id / f"{db_id}.sqlite"
            gold_rows = _execute_gold_sql(gold_sql, db_path) if gold_sql else None

            # Run case through T2S pipeline
            case_result = await _run_single_case(
                case=case,
                runtime=runtime,
                gold_rows=gold_rows,
                run_id_prefix=run_id,
            )
            results.append(case_result)

            # Write result immediately (crash-safe streaming)
            results_file.write(json.dumps(case_result, ensure_ascii=False) + "\n")
            results_file.flush()

            # Progress indicator
            ex_str = (
                "✓"
                if case_result["ex_official"] is True
                else ("✗" if case_result["ex_official"] is False else "?")
            )
            status_short = case_result["runtime_status"][:8]
            print(
                f"[{idx:3d}/{total}] {ex_str} {case['case_id']:25s} "
                f"db={db_id:22s} s={case_result['t2s_stratum']} "
                f"status={status_short:8s} {case_result['latency_ms']:6.0f}ms"
            )

    # Build and write aggregate report
    report = _build_report(results, run_id, args, args.model)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    _print_slice_report(report)
    print(f"[INFO] Results: {results_path}")
    print(f"[INFO] Report:  {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="T2S Benchmark Evaluation Runner")
    parser.add_argument(
        "--eval-dataset",
        default=str(EVAL_DATASET),
        help="Path to evaluation JSONL dataset",
    )
    parser.add_argument(
        "--db-root",
        default=str(OFFICIAL_DB_ROOT),
        help="Path to official SQLite database directory",
    )
    parser.add_argument(
        "--tables-json",
        default=str(TABLES_JSON),
        help="Path to mini_dev_tables.json for schema metadata",
    )
    parser.add_argument(
        "--prompts-dir",
        default=str(PROMPTS_DIR),
        help="Path to direct_sql prompt templates",
    )
    parser.add_argument(
        "--runs-dir",
        default=str(RUNS_DIR),
        help="Directory to write run outputs",
    )
    parser.add_argument(
        "--llm-base-url",
        default=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        help="LLM API base URL (OpenAI-compatible)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        help="LLM model name",
    )
    parser.add_argument("--api-key", default=None, help="LLM API key (overrides env)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="LLM request timeout in seconds",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of cases to run (smoke test mode)",
    )
    args = parser.parse_args()

    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
