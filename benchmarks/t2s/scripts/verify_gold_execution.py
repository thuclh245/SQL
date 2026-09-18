#!/usr/bin/env python3
"""Execute official BIRD gold SQL against official SQLite databases.

Records success/failure, observed row count, truncated flag, execution latency,
and a normalized deterministic SHA256 result hash for provenance.
Outputs gold_execution_report.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def compute_normalized_result_hash(rows: list[tuple[Any, ...]]) -> str:
    """Compute a deterministic hash of result rows for provenance."""
    # Convert all values to string representations and sort rows for order-insensitive hashing
    serialized_rows = [str(tuple(str(col) for col in row)) for row in rows]
    serialized_rows.sort()
    combined = "\n".join(serialized_rows).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify gold SQL execution on official databases.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"),
        help="Path to benchmark JSONL dataset",
    )
    parser.add_argument(
        "--db-root",
        type=Path,
        default=Path("benchmarks/t2s/databases/official"),
        help="Root directory of official SQLite databases",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/t2s/manifests/gold_execution_report.json"),
        help="Output path for execution report JSON",
    )
    parser.add_argument(
        "--fetch-cap",
        type=int,
        default=10000,
        help="Maximum rows to fetch per query",
    )
    args = parser.parse_args()

    records = load_jsonl(args.dataset)
    results = []

    for r in records:
        cid = r["case_id"]
        # Skip stubs that have no SQL
        gold = r.get("gold") or {}
        sql = gold.get("sql_original")
        if not sql:
            continue

        db_id = (r.get("inference") or {}).get("db_id")
        db_path = args.db_root / db_id / f"{db_id}.sqlite"

        rec: dict[str, Any] = {
            "case_id": cid,
            "question_id": (r.get("source") or {}).get("question_id"),
            "db_id": db_id,
            "success": False,
            "row_count_observed": None,
            "truncated": False,
            "result_hash": None,
            "latency_ms": None,
            "error": None,
        }

        start_time = time.perf_counter()
        try:
            uri = f"file:{db_path.resolve()}?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=30)
            try:
                con.execute("PRAGMA query_only = ON")
                cur = con.execute(sql)
                rows = cur.fetchmany(args.fetch_cap + 1)
                rec["row_count_observed"] = min(len(rows), args.fetch_cap)
                rec["truncated"] = len(rows) > args.fetch_cap
                rec["result_hash"] = compute_normalized_result_hash(rows[: args.fetch_cap])
                rec["success"] = True
            finally:
                con.close()
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"

        rec["latency_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        results.append(rec)

    total_tested = len(results)
    success_count = sum(1 for r in results if r["success"])
    failure_count = sum(1 for r in results if not r["success"])

    summary = {
        "dataset": str(args.dataset),
        "total_cases_tested": total_tested,
        "successfully_executable": success_count,
        "execution_failures": failure_count,
        "execution_rate_pct": round((success_count / total_tested * 100), 2) if total_tested else 0,
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"Verified gold execution: {success_count}/{total_tested} succeeded "
        f"({failure_count} failures). Wrote report to {args.output}"
    )


if __name__ == "__main__":
    main()
