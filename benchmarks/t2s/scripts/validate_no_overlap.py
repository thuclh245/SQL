#!/usr/bin/env python3
"""Validate that evaluation dataset has zero overlap with pilot and zero gold leakage."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

BIRD_ALL_DBS = {
    "california_schools",
    "card_games",
    "codebase_community",
    "debit_card_specializing",
    "european_football_2",
    "financial",
    "formula_1",
    "student_club",
    "superhero",
    "thrombosis_prediction",
    "toxicology",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate evaluation dataset integrity.")
    parser.add_argument(
        "--eval-jsonl",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_eval_v1.jsonl"),
        help="Path to evaluation JSONL",
    )
    parser.add_argument(
        "--pilot-jsonl",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"),
        help="Path to pilot JSONL",
    )
    args = parser.parse_args()

    eval_rows = load_jsonl(args.eval_jsonl)
    pilot_rows = load_jsonl(args.pilot_jsonl)

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Exact count check
    if len(eval_rows) != 100:
        errors.append(f"Expected exactly 100 eval cases, found {len(eval_rows)}")

    # 2. Overlap check
    eval_qids = {
        r.get("question_id") or (r.get("source") or {}).get("question_id") for r in eval_rows
    }
    pilot_qids = {
        r.get("question_id") or (r.get("source") or {}).get("question_id")
        for r in pilot_rows
        if (r.get("source") or {}).get("question_id") is not None
    }
    overlap = sorted(list(eval_qids & pilot_qids))
    if overlap:
        errors.append(f"Found {len(overlap)} overlapping question_ids with pilot: {overlap}")

    # 3. Duplicate checks within eval
    case_ids = [r.get("case_id") for r in eval_rows]
    dup_cases = [k for k, v in Counter(case_ids).items() if v > 1]
    if dup_cases:
        errors.append(f"Duplicate case_ids in eval set: {dup_cases}")

    dup_qids = [k for k, v in Counter(eval_qids).items() if v > 1]
    if dup_qids:
        errors.append(f"Duplicate question_ids in eval set: {dup_qids}")

    # 4. Leakage checks
    gold_sql_in_inference = 0
    expected_result_in_inference = 0
    gold_schema_in_inference = 0

    for r in eval_rows:
        cid = r.get("case_id")
        inf = r.get("inference", {})

        # Ensure required inference fields exist
        if not inf.get("question"):
            errors.append(f"{cid}: Missing inference question")
        if not inf.get("db_id"):
            errors.append(f"{cid}: Missing inference db_id")

        # Check for leakage
        if "sql" in inf or "SQL" in inf or "bird_gold_sql" in inf:
            gold_sql_in_inference += 1
        if "expected_result" in inf or "result" in inf or "answer" in inf:
            expected_result_in_inference += 1
        if "gold_tables" in inf or "gold_columns" in inf or "gold_schema" in inf:
            gold_schema_in_inference += 1

    if gold_sql_in_inference > 0:
        errors.append(f"Gold SQL exposed in inference block for {gold_sql_in_inference} cases")
    if expected_result_in_inference > 0:
        errors.append(
            f"Expected results exposed in inference block for {expected_result_in_inference} cases"
        )
    if gold_schema_in_inference > 0:
        errors.append(
            f"Gold schema labels exposed in inference block for {gold_schema_in_inference} cases"
        )

    # 5. Database coverage check
    eval_dbs = {r.get("db_id") or (r.get("inference") or {}).get("db_id") for r in eval_rows}
    missing_dbs = BIRD_ALL_DBS - eval_dbs
    if missing_dbs:
        errors.append(f"Evaluation set is missing BIRD databases: {missing_dbs}")

    # Print validation summary
    strata_counts = dict(
        Counter(r.get("t2s_stratum") or (r.get("gold") or {}).get("stratum") for r in eval_rows)
    )
    diff_counts = dict(
        Counter(
            r.get("bird_difficulty") or (r.get("gold") or {}).get("bird_difficulty")
            for r in eval_rows
        )
    )
    db_counts = dict(
        Counter(r.get("db_id") or (r.get("inference") or {}).get("db_id") for r in eval_rows)
    )

    result = {
        "status": "PASS" if not errors else "FAIL",
        "eval_case_count": len(eval_rows),
        "pilot_overlap_count": len(overlap),
        "gold_sql_exposed_to_runtime": "NO" if gold_sql_in_inference == 0 else "YES",
        "gold_result_exposed_to_runtime": "NO" if expected_result_in_inference == 0 else "YES",
        "gold_schema_exposed_to_solver": "NO" if gold_schema_in_inference == 0 else "YES",
        "database_coverage_count": len(eval_dbs),
        "all_11_bird_databases_present": len(missing_dbs) == 0,
        "strata_distribution": strata_counts,
        "difficulty_distribution": diff_counts,
        "database_distribution": db_counts,
        "errors": errors,
        "warnings": warnings,
    }

    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
