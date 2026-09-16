# ruff: noqa: E501
"""Execution script for Phase P8-E2: Frozen 20-Call OSS-120B Causal Micro-Test.

Executes exactly the preregistered 20-call protocol (15 targets + 5 controls)
against openai/gpt-oss-120b with zero mid-run adaptation, concurrency 1,
and zero retries.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.benchmark.scoring import evaluate_candidate_vs_gold
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.errors import SolverDependencyError
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder
from t2s.solver.solver_response import SolverStructuredOutput, build_sql_candidate_json_schema
from t2s.verification import SqlAccessValidator, SqlAstParser, SqlSafetyValidator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLES_JSON = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
DEV100_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
OFFICIAL_DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"
RESULTS_DIR = PROJECT_ROOT / "results" / "p8e2_microtest"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e2_microtest.md"

TARGET_COHORT = [
    # Relationship Expansion (6)
    "bird_100",
    "bird_1096",
    "bird_1195",
    "bird_1247",
    "bird_1472",
    "bird_206",
    # Column Selection (8)
    "bird_344",
    "bird_416",
    "bird_640",
    "bird_705",
    "bird_753",
    "bird_963",
    "bird_1457",
    "bird_1484",
    # Column Budget (1)
    "bird_1057",
]

CONTROL_COHORT = [
    "bird_744",
    "bird_549",
    "bird_1344",
    "bird_168",
    "bird_213",
]

TARGET_MECHANISMS = {
    "bird_100": "Relationship Expansion",
    "bird_1096": "Relationship Expansion",
    "bird_1195": "Relationship Expansion",
    "bird_1247": "Relationship Expansion",
    "bird_1472": "Relationship Expansion",
    "bird_206": "Relationship Expansion",
    "bird_344": "Column Selection",
    "bird_416": "Column Selection",
    "bird_640": "Column Selection",
    "bird_705": "Column Selection",
    "bird_753": "Column Selection",
    "bird_963": "Column Selection",
    "bird_1457": "Column Selection",
    "bird_1484": "Column Selection",
    "bird_1057": "Column Budget",
}


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env"
    env_vars = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_candidate_sql_for_benchmark(
    sql: str,
    authorization_service: AuthorizationService,
    user_identity: UserIdentity,
) -> tuple[bool, str]:
    """Validate benchmark SQL through the production parser, safety, and access stack."""
    if not sql.strip():
        return False, "EMPTY_SQL"
    try:
        parsed_sql = SqlAstParser().parse_single_statement(sql, "sqlite")
        SqlSafetyValidator().validate_read_only_sql(parsed_sql)
        SqlAccessValidator(authorization_service).validate_table_access(
            user_identity=user_identity,
            parsed_sql=parsed_sql,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, "SAFE"


async def main() -> None:
    print("=" * 80)
    print("PHASE P8-E2: FROZEN 20-CALL OSS-120B CAUSAL MICRO-TEST")
    print("=" * 80)

    # 1. Environment and Git Metadata
    env_vars = load_env()
    api_key = os.environ.get("OPENAI_API_KEY") or env_vars.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL") or env_vars.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.environ.get("T2S_LLM_MODEL") or env_vars.get("T2S_LLM_MODEL", "openai/gpt-oss-120b")

    if not api_key:
        print("ERROR: Missing OPENAI_API_KEY.")
        sys.exit(1)

    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    git_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"]).decode().strip())
    python_ver = sys.version.split()[0]
    timestamp_start = datetime.now(UTC).isoformat()

    print(f"Git SHA: {git_sha} (dirty: {git_dirty})")
    print(f"Python: {python_ver}")
    print(f"Model: {model_name} via {base_url}")
    print(f"Targets ({len(TARGET_COHORT)}): {TARGET_COHORT}")
    print(f"Controls ({len(CONTROL_COHORT)}): {CONTROL_COHORT}")

    # 2. Strict Preflight
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dev100_cases = {
        c["case_id"]: c
        for c in [
            json.loads(line)
            for line in DEV100_PATH.read_text().splitlines()
            if line.strip()
        ]
    }

    assert len(TARGET_COHORT) == 15, "Target cohort must have exactly 15 cases"
    assert len(CONTROL_COHORT) == 5, "Control cohort must have exactly 5 cases"
    assert len(set(TARGET_COHORT) & set(CONTROL_COHORT)) == 0, "Targets and controls must not overlap"

    for qid in TARGET_COHORT:
        assert qid in dev100_cases, f"Target {qid} not in Dev100"
    for qid in CONTROL_COHORT:
        assert qid in dev100_cases, f"Control {qid} not in Dev100"

    # Verify holdout non-overlap
    holdout_path = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_final_holdout_v1.jsonl"
    if holdout_path.exists():
        holdout_cases = {
            c["case_id"]
            for c in [
                json.loads(line)
                for line in holdout_path.read_text().splitlines()
                if line.strip()
            ]
        }
        overlap = (set(TARGET_COHORT) | set(CONTROL_COHORT)) & holdout_cases
        assert len(overlap) == 0, f"Overlap with final holdout: {overlap}"

    # Load databases and verify snapshots
    db_catalogs: dict[str, InMemoryCatalog] = {}
    db_retrievers: dict[str, SchemaRetriever] = {}
    db_auth: dict[str, AuthorizationService] = {}

    for qid in TARGET_COHORT + CONTROL_COHORT:
        db_id = dev100_cases[qid]["db_id"]
        db_path = OFFICIAL_DB_ROOT / db_id / f"{db_id}.sqlite"
        assert db_path.exists(), f"Database file missing: {db_path}"

        if db_id not in db_catalogs:
            cat_tables = load_bird_catalog_tables(db_id=db_id, tables_json_path=TABLES_JSON)
            cat = InMemoryCatalog()
            cat.upsert_tables(cat_tables)
            doc_builder = CatalogSearchDocumentBuilder()
            docs = [doc for t in cat_tables for doc in doc_builder.build_search_documents(t)]
            retriever = SchemaRetriever(InMemorySchemaSearch(docs))
            auth_res = [
                AuthorizedSqlResource(catalog_fqn=t.table_fqn, sql_identifier=t.sql_identifier)
                for t in cat_tables
                if t.sql_identifier
            ]

            class StaticPolicy:
                def __init__(self, r: list[AuthorizedSqlResource]) -> None:
                    self.r = r

                def get_authorized_resources(self, u: UserIdentity) -> list[AuthorizedSqlResource]:
                    return list(self.r)

            db_catalogs[db_id] = cat
            db_retrievers[db_id] = retriever
            db_auth[db_id] = AuthorizationService(StaticPolicy(auth_res))

    # Treatment: P3 = A+B
    budget_ab = GroundingBudget(
        relationship_expansion_mode="unconditional",
        fill_column_budget=True,
        small_db_threshold=0,
    )
    prompt_builder = DirectSqlPromptBuilder(prompt_version="v001")
    user = UserIdentity(user_id="microtest_eval", roles=["analyst"])

    system_prompt_text = prompt_builder._read_prompt_file("v001_system.md")
    user_template_text = prompt_builder._read_prompt_file("v001_user_template.md")
    prompt_template_hash = hash_text(system_prompt_text + user_template_text)

    preflight_record = {
        "timestamp": timestamp_start,
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "python_version": python_ver,
        "model_name": model_name,
        "target_count": len(TARGET_COHORT),
        "control_count": len(CONTROL_COHORT),
        "total_planned_calls": 20,
        "target_cohort_hash": hash_text(",".join(TARGET_COHORT)),
        "control_cohort_hash": hash_text(",".join(CONTROL_COHORT)),
        "prompt_version": "v001",
        "prompt_template_hash": prompt_template_hash,
        "p3_treatment": "A+B (unconditional 1-hop FK expansion + fill_column_budget)",
        "concurrency": 1,
        "retries": 0,
        "status": "PREFLIGHT_PASS",
    }
    (RESULTS_DIR / "preflight.json").write_text(json.dumps(preflight_record, indent=2))
    print("Preflight validation PASSED.")

    # 3. Freeze Manifest Before First API Call
    manifest_data = {
        "experiment_id": "P8-E2-OSS120B-MICROTEST-20",
        "timestamp_start": timestamp_start,
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "model": model_name,
        "temperature": 0.0,
        "prompt_path": "prompts/direct_sql/v001",
        "prompt_template_hash": prompt_template_hash,
        "p3_configuration": {
            "relationship_expansion_mode": "unconditional",
            "fill_column_budget": True,
            "small_db_threshold": 0,
        },
        "p5_state": "OFF",
        "verifier_state": "OFF",
        "candidate_count": 1,
        "scorer_implementation": "t2s.benchmark.scoring.evaluate_candidate_vs_gold (symmetrical execution)",
        "target_ids": TARGET_COHORT,
        "control_ids": CONTROL_COHORT,
        "target_cohort_hash": hash_text(",".join(TARGET_COHORT)),
        "control_cohort_hash": hash_text(",".join(CONTROL_COHORT)),
        "execution_order": TARGET_COHORT + CONTROL_COHORT,
        "success_criterion": "target recovery >= 5 / 15 (>= 33.3%) AND control regressions == 0 / 5",
        "failure_criterion": "target recovery < 5 / 15 OR control regressions > 0 / 5",
        "frozen_status": "MANIFEST_FROZEN_BEFORE_API",
    }
    (RESULTS_DIR / "manifest.json").write_text(json.dumps(manifest_data, indent=2))
    print("Manifest FROZEN to results/p8e2_microtest/manifest.json.")

    # 4. Initialize HTTP client (strictly 0 retries, concurrency 1)
    chat_client = OpenAICompatibleChatClient(
        base_url=base_url,
        api_key=api_key,
        temperature=0.0,
        request_timeout_seconds=180.0,
    )

    call_order = [(qid, "TARGET") for qid in TARGET_COHORT] + [(qid, "CONTROL") for qid in CONTROL_COHORT]

    call_ledger: list[dict[str, Any]] = []
    request_metadata: list[dict[str, Any]] = []
    raw_responses: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    execution_results: list[dict[str, Any]] = []

    print("\nStarting frozen execution of 20 cases (15 targets, 5 controls)...")

    # Load baseline context stats from P8E1 baseline_grounding.jsonl
    base_grounding_path = PROJECT_ROOT / "results" / "p8e1_p3_remediation" / "baseline_grounding.jsonl"
    baseline_stats = {}
    if base_grounding_path.exists():
        for line in base_grounding_path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                baseline_stats[rec["case_id"]] = rec

    for idx, (qid, cohort) in enumerate(call_order, start=1):
        c = dev100_cases[qid]
        db_id = c["db_id"]
        q_text = c["question"]
        gold_sql = c["bird_gold_sql"]
        db_path = OFFICIAL_DB_ROOT / db_id / f"{db_id}.sqlite"

        print(f"[{idx:02d}/20] Running {cohort} {qid} ({db_id})...", end=" ", flush=True)

        # Build A+B Grounding Context
        bldr = GroundingContextBuilder(
            catalog=db_catalogs[db_id],
            schema_retriever=db_retrievers[db_id],
            authorization_service=db_auth[db_id],
            grounding_budget=budget_ab,
        )
        ctx = bldr.build_grounding_context(QueryRequest(question=q_text), user_identity=user)

        num_tables = len(ctx.tables)
        num_columns = sum(len(t.columns) for t in ctx.tables)
        prompt_str = prompt_builder._format_authorized_schema(ctx)
        est_tokens = len(prompt_str) // 4

        # Build prompt messages (Zero gold information)
        messages = prompt_builder.build_solver_messages(
            query_request=QueryRequest(question=q_text),
            grounding_context=ctx,
            target_dialect="sqlite",
        )

        q_hash = hash_text(q_text)
        ctx_hash = hash_text(json.dumps(ctx.model_dump(), sort_keys=True))
        final_prompt_hash = hash_text(json.dumps(messages, sort_keys=True))

        req_meta = {
            "call_index": idx,
            "case_id": qid,
            "cohort": cohort,
            "db_id": db_id,
            "question_hash": q_hash,
            "grounding_context_hash": ctx_hash,
            "prompt_template_hash": prompt_template_hash,
            "final_prompt_hash": final_prompt_hash,
            "grounding_table_count": num_tables,
            "grounding_column_count": num_columns,
            "estimated_prompt_tokens": est_tokens,
        }
        request_metadata.append(req_meta)

        # Send API request (concurrency 1, retries 0)
        t_req_start = datetime.now(UTC).isoformat()
        req_start_perf = time.perf_counter()

        api_error: str | None = None
        raw_content: Any = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None
        model_returned: str | None = None
        provider_request_id: str | None = None
        finish_reason: str | None = None
        http_status: int | None = None

        try:
            chat_resp = await chat_client.generate_structured_response(
                messages=messages,
                response_schema=build_sql_candidate_json_schema(),
                model_name=model_name,
                reasoning_effort=None,
                max_output_tokens=1500,
            )
            raw_content = chat_resp.content
            input_tokens = chat_resp.prompt_tokens
            output_tokens = chat_resp.output_tokens
            total_tokens = (input_tokens or 0) + (output_tokens or 0)
            model_returned = chat_resp.model_name
            http_status = 200
        except SolverDependencyError as exc:
            api_error = str(exc)
        except Exception as exc:
            api_error = f"UNEXPECTED_ERROR: {type(exc).__name__}: {exc}"

        t_req_end = datetime.now(UTC).isoformat()
        elapsed_ms = int((time.perf_counter() - req_start_perf) * 1000)

        # Call Ledger Record
        ledger_entry = {
            "call_index": idx,
            "case_id": qid,
            "cohort": cohort,
            "started_at": t_req_start,
            "completed_at": t_req_end,
            "elapsed_ms": elapsed_ms,
            "provider_request_id": provider_request_id,
            "status": "API_ERROR" if api_error else "SUCCESS",
            "error_detail": api_error,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        call_ledger.append(ledger_entry)

        # Raw Response Record
        raw_rec = {
            "call_index": idx,
            "case_id": qid,
            "cohort": cohort,
            "request_timestamp": t_req_start,
            "response_timestamp": t_req_end,
            "http_status": http_status,
            "model_returned": model_returned,
            "finish_reason": finish_reason,
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "raw_content": raw_content,
            "api_error": api_error,
        }
        raw_responses.append(raw_rec)

        candidate_sql: str | None = None
        parse_status = "NOT_ATTEMPTED"

        if api_error:
            parse_status = "API_ERROR"
            candidate_rec = {
                "case_id": qid,
                "cohort": cohort,
                "parse_status": parse_status,
                "candidate_sql": None,
            }
            candidates.append(candidate_rec)

            eval_rec = {
                "case_id": qid,
                "cohort": cohort,
                "execution_correct": False,
                "candidate_status": "API_ERROR",
                "gold_status": "NOT_RUN",
                "candidate_row_count": 0,
                "gold_row_count": 0,
                "outcome": "API_ERROR",
                "detail": api_error,
            }
            execution_results.append(eval_rec)
            print(f"API_ERROR ({api_error})")
            continue

        # Parse candidate SQL using production P4 parser
        try:
            structured_out = SolverStructuredOutput.model_validate(raw_content)
            candidate_sql = structured_out.sql.strip()
            parse_status = "PARSE_SUCCESS"
        except Exception as exc:
            parse_status = f"MALFORMED_OUTPUT: {exc}"

        candidate_rec = {
            "case_id": qid,
            "cohort": cohort,
            "parse_status": parse_status,
            "candidate_sql": candidate_sql,
        }
        candidates.append(candidate_rec)

        if parse_status != "PARSE_SUCCESS" or not candidate_sql:
            eval_rec = {
                "case_id": qid,
                "cohort": cohort,
                "execution_correct": False,
                "candidate_status": "GENERATION_FAILURE",
                "gold_status": "NOT_RUN",
                "candidate_row_count": 0,
                "gold_row_count": 0,
                "outcome": "GENERATION_FAILURE",
                "detail": parse_status,
            }
            execution_results.append(eval_rec)
            print(f"GENERATION_FAILURE ({parse_status})")
            continue

        # Deterministic SQL safety/access validation via the production validation stack.
        is_safe, safety_reason = validate_candidate_sql_for_benchmark(
            candidate_sql,
            db_auth[db_id],
            user,
        )
        if not is_safe:
            eval_rec = {
                "case_id": qid,
                "cohort": cohort,
                "execution_correct": False,
                "candidate_status": "SAFETY_REJECTED",
                "gold_status": "NOT_RUN",
                "candidate_row_count": 0,
                "gold_row_count": 0,
                "outcome": "SAFETY_REJECTED",
                "detail": safety_reason,
            }
            execution_results.append(eval_rec)
            print(f"SAFETY_REJECTED ({safety_reason})")
            continue

        # Benchmark Scorer Evaluation (Symmetric)
        is_match, cand_res, gold_res = evaluate_candidate_vs_gold(
            candidate_sql=candidate_sql,
            gold_sql=gold_sql,
            db_path=db_path,
        )

        if cohort == "TARGET":
            outcome = "RECOVERED" if is_match else "STILL_WRONG"
        else:
            outcome = "CONTROL_PRESERVED" if is_match else "CONTROL_REGRESSED"

        eval_rec = {
            "case_id": qid,
            "cohort": cohort,
            "candidate_sql": candidate_sql,
            "gold_sql": gold_sql,
            "execution_correct": is_match,
            "candidate_status": "OK" if cand_res.ok else f"ERROR: {cand_res.error}",
            "gold_status": "OK" if gold_res.ok else f"ERROR: {gold_res.error}",
            "candidate_row_count": len(cand_res.rows),
            "gold_row_count": len(gold_res.rows),
            "outcome": outcome,
            "elapsed_ms": elapsed_ms,
        }
        execution_results.append(eval_rec)
        print(f"{outcome} (cand_rows={len(cand_res.rows)}, gold_rows={len(gold_res.rows)}, match={is_match})")

    print("-" * 80)
    print("Execution complete. Processing and saving all required artifacts...")

    # Write JSONL artifacts
    with open(RESULTS_DIR / "call_ledger.jsonl", "w") as f:
        for r in call_ledger:
            f.write(json.dumps(r) + "\n")

    with open(RESULTS_DIR / "request_metadata.jsonl", "w") as f:
        for r in request_metadata:
            f.write(json.dumps(r) + "\n")

    with open(RESULTS_DIR / "raw_responses.jsonl", "w") as f:
        for r in raw_responses:
            f.write(json.dumps(r) + "\n")

    with open(RESULTS_DIR / "candidates.jsonl", "w") as f:
        for r in candidates:
            f.write(json.dumps(r) + "\n")

    with open(RESULTS_DIR / "execution_results.jsonl", "w") as f:
        for r in execution_results:
            f.write(json.dumps(r) + "\n")

    # Target Results
    target_evals = [r for r in execution_results if r["cohort"] == "TARGET"]
    recovered_targets = [r["case_id"] for r in target_evals if r["outcome"] == "RECOVERED"]
    still_wrong_targets = [r["case_id"] for r in target_evals if r["outcome"] == "STILL_WRONG"]
    gen_fail_targets = [r["case_id"] for r in target_evals if r["outcome"] == "GENERATION_FAILURE"]
    safety_fail_targets = [r["case_id"] for r in target_evals if r["outcome"] == "SAFETY_REJECTED"]
    api_error_targets = [r["case_id"] for r in target_evals if r["outcome"] == "API_ERROR"]

    target_results_data = {
        "total_targets": len(TARGET_COHORT),
        "recovered_count": len(recovered_targets),
        "recovered_rate": round(len(recovered_targets) / len(TARGET_COHORT) * 100, 2),
        "still_wrong_count": len(still_wrong_targets),
        "generation_failure_count": len(gen_fail_targets),
        "safety_rejected_count": len(safety_fail_targets),
        "api_error_count": len(api_error_targets),
        "recovered_cases": recovered_targets,
        "still_wrong_cases": still_wrong_targets,
        "case_details": [
            {
                "case_id": r["case_id"],
                "mechanism": TARGET_MECHANISMS[r["case_id"]],
                "difficulty": dev100_cases[r["case_id"]]["bird_difficulty"],
                "db_id": dev100_cases[r["case_id"]]["db_id"],
                "historical_score": "0/3",
                "outcome": r["outcome"],
                "execution_correct": r["execution_correct"],
                "candidate_row_count": r["candidate_row_count"],
                "gold_row_count": r["gold_row_count"],
                "candidate_sql": r.get("candidate_sql"),
            }
            for r in target_evals
        ],
    }
    (RESULTS_DIR / "target_results.json").write_text(json.dumps(target_results_data, indent=2))

    # Control Results
    control_evals = [r for r in execution_results if r["cohort"] == "CONTROL"]
    preserved_controls = [r["case_id"] for r in control_evals if r["outcome"] == "CONTROL_PRESERVED"]
    regressed_controls = [r["case_id"] for r in control_evals if r["outcome"] == "CONTROL_REGRESSED"]
    api_error_controls = [r["case_id"] for r in control_evals if r["outcome"] == "API_ERROR"]

    control_results_data = {
        "total_controls": len(CONTROL_COHORT),
        "preserved_count": len(preserved_controls),
        "regressed_count": len(regressed_controls),
        "api_error_count": len(api_error_controls),
        "preserved_cases": preserved_controls,
        "regressed_cases": regressed_controls,
        "case_details": [
            {
                "case_id": r["case_id"],
                "difficulty": dev100_cases[r["case_id"]]["bird_difficulty"],
                "db_id": dev100_cases[r["case_id"]]["db_id"],
                "historical_score": "3/3",
                "outcome": r["outcome"],
                "execution_correct": r["execution_correct"],
                "candidate_row_count": r["candidate_row_count"],
                "gold_row_count": r["gold_row_count"],
                "candidate_sql": r.get("candidate_sql"),
            }
            for r in control_evals
        ],
    }
    (RESULTS_DIR / "control_results.json").write_text(json.dumps(control_results_data, indent=2))

    # Mechanism Results
    mechanism_groups: dict[str, list[dict[str, Any]]] = {}
    for r in target_results_data["case_details"]:
        m = r["mechanism"]
        mechanism_groups.setdefault(m, []).append(r)

    mechanism_results_data = {
        mech: {
            "total": len(items),
            "recovered": sum(1 for i in items if i["outcome"] == "RECOVERED"),
            "recovery_rate": round(sum(1 for i in items if i["outcome"] == "RECOVERED") / len(items) * 100, 2),
            "cases": [i["case_id"] for i in items],
            "recovered_cases": [i["case_id"] for i in items if i["outcome"] == "RECOVERED"],
        }
        for mech, items in mechanism_groups.items()
    }
    (RESULTS_DIR / "mechanism_results.json").write_text(json.dumps(mechanism_results_data, indent=2))

    # Difficulty Results (Targets)
    diff_groups: dict[str, list[dict[str, Any]]] = {}
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

    # Context Delta Analysis
    context_delta_records = []
    for r in target_results_data["case_details"]:
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
            "mechanism": r["mechanism"],
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

    # Usage Summary
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

    # Final Decision
    n_recovered = len(recovered_targets)
    n_regressed = len(regressed_controls)
    n_api_errors = sum(1 for r in call_ledger if r["status"] == "API_ERROR")

    if n_api_errors > 0 and (n_recovered < 5 or n_regressed > 0):
        decision = "P8_E2_RESULT = INCONCLUSIVE_INFRASTRUCTURE"
        next_action = "NO_SCIENTIFIC_CONCLUSION\nREVIEW_INFRASTRUCTURE_FAILURE"
        decision_reason = f"Provider errors ({n_api_errors}) invalidated cohort completion."
    elif n_recovered >= 5 and n_regressed == 0:
        decision = "P8_E2_RESULT = PASS"
        next_action = "PROCEED_TO_LEVEL_2_TARGETED_VALIDATION"
        decision_reason = (
            f"Target recoveries ({n_recovered}/15, {round(n_recovered/15*100, 1)}%) >= 5/15 "
            f"AND control regressions ({n_regressed}/5) == 0/5."
        )
    else:
        decision = "P8_E2_RESULT = FAIL"
        next_action = "STOP_PAID_EXPANSION\nRETURN_TO_P3_P4_DIAGNOSTICS"
        reasons = []
        if n_recovered < 5:
            reasons.append(f"Target recoveries ({n_recovered}/15) < 5/15")
        if n_regressed > 0:
            reasons.append(f"Control regressions ({n_regressed}/5) > 0/5")
        decision_reason = " AND ".join(reasons)

    decision_data = {
        "experiment_decision": decision,
        "next_action": next_action,
        "decision_reason": decision_reason,
        "recovered_targets_count": n_recovered,
        "regressed_controls_count": n_regressed,
        "success_threshold_met": (n_recovered >= 5 and n_regressed == 0),
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
    }
    (RESULTS_DIR / "experiment_decision.json").write_text(json.dumps(decision_data, indent=2))

    # Summary Markdown
    summary_md = f"""# Phase P8-E2: Frozen 20-Call OSS-120B Causal Micro-Test Summary

## 1. Executive Status
- **Experiment Result**: `{decision}`
- **Next Action**: `{next_action}`
- **Decision Reason**: {decision_reason}
- **Model**: `{model_name}` (temperature: 0.0)
- **Zero Rerun Invariant**: Dev100 rerun = NO, Final Holdout run = NO.

---

## 2. Headline Results

| Metric | Measured Result | Required Criterion | Pass? |
|---|---:|---:|:---:|
| **Target SQL Recoveries** | **{n_recovered} / 15** ({round(n_recovered/15*100, 1)}%) | $\\ge 5 / 15$ ($\\ge 33.3\\%) | **{'YES' if n_recovered >= 5 else 'NO'}** |
| **Control SQL Regressions** | **{n_regressed} / 5** | Exactly $0 / 5$ | **{'YES' if n_regressed == 0 else 'NO'}** |
| **API Errors / Dropped Requests** | **{n_api_errors}** | 0 | **{'YES' if n_api_errors == 0 else 'NO'}** |

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

| Mechanism | Total (N) | Recovered | Recovery Rate |
|---|---:|---:|---:|
| **Relationship Expansion** | 6 | {mechanism_results_data.get('Relationship Expansion', {}).get('recovered', 0)} | {mechanism_results_data.get('Relationship Expansion', {}).get('recovery_rate', 0.0)}% |
| **Column Selection** | 8 | {mechanism_results_data.get('Column Selection', {}).get('recovered', 0)} | {mechanism_results_data.get('Column Selection', {}).get('recovery_rate', 0.0)}% |
| **Column Budget** | 1 | {mechanism_results_data.get('Column Budget', {}).get('recovered', 0)} | {mechanism_results_data.get('Column Budget', {}).get('recovery_rate', 0.0)}% |

---

## 6. Difficulty Breakdown (Targets)

| Difficulty | Total (N) | Recovered | Recovery Rate |
|---|---:|---:|---:|
| **Simple** | 2 | {difficulty_results_data.get('simple', {}).get('recovered', 0)} | {difficulty_results_data.get('simple', {}).get('recovery_rate', 0.0)}% |
| **Moderate** | 9 | {difficulty_results_data.get('moderate', {}).get('recovered', 0)} | {difficulty_results_data.get('moderate', {}).get('recovery_rate', 0.0)}% |
| **Challenging** | 4 | {difficulty_results_data.get('challenging', {}).get('recovered', 0)} | {difficulty_results_data.get('challenging', {}).get('recovery_rate', 0.0)}% |

---

## 7. Token & Cost Usage
- **Planned Calls**: 20
- **Attempted Calls**: {len(call_ledger)}
- **Successful API Responses**: {usage_summary_data['successful_api_responses']}
- **API Errors**: {n_api_errors}
- **Total Input Tokens**: {tot_input_tokens:,}
- **Total Output Tokens**: {tot_output_tokens:,}
- **Total Tokens**: {tot_tokens:,}
"""
    (RESULTS_DIR / "summary.md").write_text(summary_md)

    print("\n" + "=" * 80)
    print(f"EXPERIMENT DECISION: {decision}")
    print(f"RECOVERED TARGETS: {n_recovered} / 15")
    print(f"REGRESSED CONTROLS: {n_regressed} / 5")
    print(f"NEXT ACTION: {next_action}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
