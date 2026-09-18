#!/usr/bin/env python3
"""Inspect SQLite databases and generate database_integrity_report.json.

Evaluates table count, row count, non-empty tables, and classifies each database as:
OFFICIAL_EXECUTION_DB or SCHEMA_ONLY_PLACEHOLDER.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

BIRD_DATABASES = [
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
]


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def inspect_database_file(db_id: str, db_file: Path, source_label: str) -> dict[str, Any]:
    if not db_file.exists():
        return {
            "db_id": db_id,
            "path": str(db_file),
            "source": source_label,
            "sha256": None,
            "file_size": 0,
            "table_count": 0,
            "non_empty_table_count": 0,
            "total_row_count": 0,
            "classification": "INVALID",
            "error": "File not found",
        }

    size_bytes = db_file.stat().st_size
    sha256_hash = compute_sha256(db_file)

    uri = f"file:{db_file.resolve()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        tables_res = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        tables = [row[0] for row in tables_res]
        table_count = len(tables)

        total_rows = 0
        non_empty_count = 0
        table_details = {}

        for t in tables:
            try:
                cnt = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                table_details[t] = cnt
                total_rows += cnt
                if cnt > 0:
                    non_empty_count += 1
            except Exception as e:
                table_details[t] = f"ERROR: {e}"

    except Exception as e:
        con.close()
        return {
            "db_id": db_id,
            "path": str(db_file),
            "source": source_label,
            "sha256": sha256_hash,
            "file_size": size_bytes,
            "table_count": 0,
            "non_empty_table_count": 0,
            "total_row_count": 0,
            "classification": "INVALID",
            "error": str(e),
        }
    con.close()

    if table_count > 0 and total_rows > 0 and non_empty_count == table_count:
        classification = "OFFICIAL_EXECUTION_DB"
    elif table_count > 0 and total_rows == 0:
        classification = "SCHEMA_ONLY_PLACEHOLDER"
    else:
        classification = "UNKNOWN"

    return {
        "db_id": db_id,
        "path": str(db_file),
        "source": source_label,
        "sha256": sha256_hash,
        "file_size": size_bytes,
        "table_count": table_count,
        "non_empty_table_count": non_empty_count,
        "total_row_count": total_rows,
        "classification": classification,
        "table_row_counts": table_details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect BIRD databases.")
    parser.add_argument(
        "--official-dir",
        type=Path,
        default=Path("benchmarks/t2s/databases/official"),
        help="Path to official databases directory",
    )
    parser.add_argument(
        "--placeholder-dir",
        type=Path,
        default=Path("benchmarks/t2s/databases/schema_only_placeholders"),
        help="Path to placeholder databases directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/t2s/manifests/database_integrity_report.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    official_results = []
    placeholder_results = []

    for db_id in BIRD_DATABASES:
        official_path = args.official_dir / db_id / f"{db_id}.sqlite"
        official_results.append(
            inspect_database_file(db_id, official_path, "official_mini_dev_databases")
        )

        placeholder_path = args.placeholder_dir / f"{db_id}.sqlite"
        if not placeholder_path.exists():
            placeholder_path = args.placeholder_dir / db_id / f"{db_id}.sqlite"
        placeholder_results.append(
            inspect_database_file(db_id, placeholder_path, "schema_only_ddl_reconstruction")
        )

    summary = {
        "official_databases": {
            "total_inspected": len(official_results),
            "official_execution_db_count": sum(
                1 for r in official_results if r["classification"] == "OFFICIAL_EXECUTION_DB"
            ),
            "schema_only_count": sum(
                1 for r in official_results if r["classification"] == "SCHEMA_ONLY_PLACEHOLDER"
            ),
            "invalid_count": sum(1 for r in official_results if r["classification"] == "INVALID"),
            "total_rows_across_all_dbs": sum(r["total_row_count"] for r in official_results),
            "records": official_results,
        },
        "placeholder_databases": {
            "total_inspected": len(placeholder_results),
            "schema_only_count": sum(
                1 for r in placeholder_results if r["classification"] == "SCHEMA_ONLY_PLACEHOLDER"
            ),
            "official_execution_db_count": sum(
                1 for r in placeholder_results if r["classification"] == "OFFICIAL_EXECUTION_DB"
            ),
            "records": placeholder_results,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote database integrity report to {args.output}")


if __name__ == "__main__":
    main()
