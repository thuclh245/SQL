"""Reproduce ResultVerifier replay evaluation from source/runtime and persist machine-readable artifacts."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.benchmark.invariants import resolve_official_database_path
from t2s.benchmark.runtime_factory import AllTablesBenchmarkAccessPolicy
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.database import QueryExecutionPolicy
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.semantics.semantic_planner import GroundedSemanticPlanner
from t2s.verification.result_verifier import ResultVerifier


def reproduce_replay() -> None:
    cases_path = Path("results/accuracy_foundation_ablation/arm_d_value_linking/cases.jsonl")
    dataset_path = Path("benchmarks/t2s/datasets/t2s_pilot_v1.jsonl")
    db_root = Path("benchmarks/t2s/databases/official")
    tables_json = Path("data/bird_mini_dev/mini_dev_tables.json")
    output_dir = Path("results/result_verifier_replay")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(cases_path, encoding="utf-8") as f:
        arm_d_cases = [json.loads(line) for line in f]

    with open(dataset_path, encoding="utf-8") as f:
        dataset_cases = {
            c["case_id"]: c["inference"]["question"]
            for c in [json.loads(line) for line in f]
        }

    verifier = ResultVerifier()
    planner = GroundedSemanticPlanner()
    policy = QueryExecutionPolicy(maximum_result_rows=1000, statement_timeout_seconds=30)

    # Build catalog builders per db
    catalog_cache: dict[str, GroundingContextBuilder] = {}
    for db_id in set(c["db_id"] for c in arm_d_cases):
        catalog_tables = load_bird_catalog_tables(db_id=db_id, tables_json_path=tables_json)
        cat = InMemoryCatalog()
        cat.upsert_tables(catalog_tables)
        doc_builder = CatalogSearchDocumentBuilder()
        docs = [d for ct in catalog_tables for d in doc_builder.build_search_documents(ct)]
        retriever = SchemaRetriever(InMemorySchemaSearch(docs))
        auth_resources = [
            AuthorizedSqlResource(catalog_fqn=ct.table_fqn, sql_identifier=ct.sql_identifier)
            for ct in catalog_tables
            if ct.sql_identifier
        ]
        auth_svc = AuthorizationService(AllTablesBenchmarkAccessPolicy(auth_resources))
        builder = GroundingContextBuilder(cat, retriever, auth_svc, GroundingBudget())
        catalog_cache[db_id] = builder

    persisted_cases: list[dict[str, Any]] = []

    # Counters
    eligible_count = 0
    evaluated_count = 0
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0

    # Also decoupled counters
    decoupled_tp = 0
    decoupled_fp = 0
    decoupled_tn = 0
    decoupled_fn = 0

    for c in arm_d_cases:
        case_id = c["case_id"]
        runtime_status = c.get("runtime_status")
        execution_success = c.get("execution_success") is True
        sql_correct = c.get("execution_correct")
        generated_sql = c.get("generated_sql")
        db_id = c["db_id"]

        if not execution_success or not generated_sql or runtime_status != "SUCCESS":
            # Ineligible for post-execution result verification
            exec_status = runtime_status if runtime_status else "FAILED"
            persisted_cases.append({
                "run_id": "result_verifier_replay",
                "case_id": case_id,
                "db_id": db_id,
                "execution_status": exec_status,
                "verifier_status": "NOT_APPLICABLE",
                "verifier_reason_codes": [],
                "sql_correct": sql_correct,
                "flagged": False,
                "decoupled_flagged": False,
                "decoupled_reason_codes": [],
            })
            continue

        eligible_count += 1
        evaluated_count += 1

        db_path = resolve_official_database_path(db_root, db_id)
        executor = SqliteReadOnlyQueryExecutor(db_path)
        exec_result = executor.execute_read_only_query(generated_sql, policy)

        # 1. Verification with deterministic plan
        builder = catalog_cache[db_id]
        q_text = dataset_cases[case_id]
        q_req = QueryRequest(question=q_text, database_dialect="sqlite")
        g_ctx = builder.build_grounding_context(q_req, UserIdentity(user_id="verifier-replay"))
        plan = planner._plan_deterministic(q_req, g_ctx, f"plan-{case_id}")

        outcome = verifier.verify_result(exec_result, plan=plan)
        is_flagged = outcome.is_suspicious
        reasons = [outcome.failure_code] if outcome.failure_code else []

        # 2. Verification decoupled (plan=None)
        decoupled_outcome = verifier.verify_result(exec_result, plan=None)
        decoupled_is_flagged = decoupled_outcome.is_suspicious
        decoupled_reasons = [decoupled_outcome.failure_code] if decoupled_outcome.failure_code else []

        if is_flagged:
            verifier_status = "FLAGGED"
            if sql_correct is False:
                true_positives += 1
            elif sql_correct is True:
                false_positives += 1
        else:
            verifier_status = "PASSED"
            if sql_correct is True:
                true_negatives += 1
            elif sql_correct is False:
                false_negatives += 1

        if decoupled_is_flagged:
            if sql_correct is False:
                decoupled_tp += 1
            elif sql_correct is True:
                decoupled_fp += 1
        else:
            if sql_correct is True:
                decoupled_tn += 1
            elif sql_correct is False:
                decoupled_fn += 1

        persisted_cases.append({
            "run_id": "result_verifier_replay",
            "case_id": case_id,
            "db_id": db_id,
            "execution_status": "COMPLETED",
            "verifier_status": verifier_status,
            "verifier_reason_codes": reasons,
            "sql_correct": sql_correct,
            "flagged": is_flagged,
            "recommended_probe": outcome.recommended_probe,
            "verifier_details": outcome.details,
            "decoupled_status": "FLAGGED" if decoupled_is_flagged else "PASSED",
            "decoupled_flagged": decoupled_is_flagged,
            "decoupled_reason_codes": decoupled_reasons,
        })

    # Write cases.jsonl
    cases_file = output_dir / "cases.jsonl"
    with open(cases_file, "w", encoding="utf-8") as f:
        for item in persisted_cases:
            f.write(json.dumps(item, sort_keys=True) + "\n")

    flagged_count = true_positives + false_positives
    decoupled_flagged = decoupled_tp + decoupled_fp

    # Metrics
    precision = (true_positives / flagged_count) if flagged_count > 0 else 0.0
    recall = (true_positives / (true_positives + false_negatives)) if (true_positives + false_negatives) > 0 else 0.0
    fpr = (false_positives / (false_positives + true_negatives)) if (false_positives + true_negatives) > 0 else 0.0
    coverage = (evaluated_count / len(arm_d_cases)) if arm_d_cases else 0.0

    decoupled_precision = (decoupled_tp / decoupled_flagged) if decoupled_flagged > 0 else 0.0
    decoupled_recall = (decoupled_tp / (decoupled_tp + decoupled_fn)) if (decoupled_tp + decoupled_fn) > 0 else 0.0
    decoupled_fpr = (decoupled_fp / (decoupled_fp + decoupled_tn)) if (decoupled_fp + decoupled_tn) > 0 else 0.0

    metrics = {
        "dataset_total_cases": len(arm_d_cases),
        "eligible_for_verification": eligible_count,
        "not_applicable_count": len(arm_d_cases) - eligible_count,
        "verifier_evaluated_count": evaluated_count,
        "coverage_applicability_rate": round(coverage, 4),
        "with_plan": {
            "flagged_count": flagged_count,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "true_negatives": true_negatives,
            "false_negatives": false_negatives,
            "precision": round(precision, 4),
            "recall_sensitivity": round(recall, 4),
            "false_positive_rate": round(fpr, 4),
            "flagged_cases": [c["case_id"] for c in persisted_cases if c.get("flagged")],
            "false_alarm_cases": [c["case_id"] for c in persisted_cases if c.get("flagged") and c.get("sql_correct") is True],
        },
        "decoupled_mode": {
            "flagged_count": decoupled_flagged,
            "true_positives": decoupled_tp,
            "false_positives": decoupled_fp,
            "true_negatives": decoupled_tn,
            "false_negatives": decoupled_fn,
            "precision": round(decoupled_precision, 4),
            "recall_sensitivity": round(decoupled_recall, 4),
            "false_positive_rate": round(decoupled_fpr, 4),
            "flagged_cases": [c["case_id"] for c in persisted_cases if c.get("decoupled_flagged")],
            "false_alarm_cases": [c["case_id"] for c in persisted_cases if c.get("decoupled_flagged") and c.get("sql_correct") is True],
        },
    }

    metrics_file = output_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)

    # Manifest
    manifest = {
        "run_id": "result_verifier_replay",
        "timestamp": datetime.now(UTC).isoformat(),
        "source_cases": str(cases_path),
        "dataset_path": str(dataset_path),
        "database_root": str(db_root),
        "database_dialect": "sqlite",
        "verifier_evaluated": evaluated_count,
        "config_hash": hashlib.sha256(json.dumps(metrics, sort_keys=True).encode()).hexdigest(),
    }
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    print("ResultVerifier replay complete.")
    print(f"Persisted to {output_dir}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    reproduce_replay()
