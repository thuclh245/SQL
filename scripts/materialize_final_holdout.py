# ruff: noqa: E501
"""Materialize the 215-case Final Untouched Holdout dataset and manifest."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from t2s.benchmark.scoring import execute_gold_sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARTITION_MANIFEST_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "bird_unopened_partition_manifest.json"
POOL_MANIFEST_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "opened_vs_unopened_question_pool.json"
DEV100_MANIFEST_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "t2s_p8b_dev100_manifest.json"
SOURCE_PATH = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_sqlite.json"
DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"

OUTPUT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_final_holdout_v1.jsonl"
OUTPUT_MANIFEST = PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "t2s_final_holdout_v1_manifest.json"


def verify_holdout_invariants_by_id() -> list[int]:
    part_data = json.loads(PARTITION_MANIFEST_PATH.read_text(encoding="utf-8"))
    holdout_ids = part_data["final_untouched_holdout"]["question_ids"]
    if len(holdout_ids) != 215:
        raise ValueError(f"Expected 215 holdout IDs, got {len(holdout_ids)}")

    pool_data = json.loads(POOL_MANIFEST_PATH.read_text(encoding="utf-8"))
    pilot_ids = set(pool_data["pilot_v1_question_ids"])
    eval_v1_ids = set(pool_data["eval_v1_question_ids"])

    dev100_data = json.loads(DEV100_MANIFEST_PATH.read_text(encoding="utf-8"))
    dev100_ids = set(dev100_data["question_ids"])

    h_set = set(holdout_ids)
    if len(h_set) != 215:
        raise ValueError("Holdout question IDs contain duplicates")

    if h_set & pilot_ids:
        raise ValueError(f"Overlap with Pilot: {h_set & pilot_ids}")
    if h_set & eval_v1_ids:
        raise ValueError(f"Overlap with Eval v1: {h_set & eval_v1_ids}")
    if h_set & dev100_ids:
        raise ValueError(f"Overlap with Dev100: {h_set & dev100_ids}")

    return holdout_ids


def materialize() -> None:
    print("Verifying Stage A holdout invariants by ID...")
    holdout_ids = verify_holdout_invariants_by_id()
    print("Invariants verified: exactly 215 unique IDs, zero overlap with Pilot, Eval v1, and Dev100.")

    source_bytes = SOURCE_PATH.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    part_manifest_sha = hashlib.sha256(PARTITION_MANIFEST_PATH.read_bytes()).hexdigest()

    raw_items = json.loads(source_bytes.decode("utf-8"))
    item_map = {item["question_id"]: item for item in raw_items}

    missing = set(holdout_ids) - set(item_map.keys())
    if missing:
        raise ValueError(f"Missing question IDs in source data: {missing}")

    difficulty_map = {
        "simple": "S1",
        "moderate": "S2",
        "challenging": "S3",
    }

    OUTPUT_DATASET.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    db_counts: Counter[str] = Counter()
    diff_counts: Counter[str] = Counter()
    gold_ok_count = 0

    lines: list[str] = []
    print("Formatting 215 cases and validating gold executability...")

    for qid in holdout_ids:
        item = item_map[qid]
        db_id = item["db_id"]
        diff = item.get("difficulty", "simple").lower()
        stratum = difficulty_map.get(diff, "S1")
        gold_sql = item["SQL"]

        db_counts[db_id] += 1
        diff_counts[diff] += 1

        db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        exec_res = execute_gold_sql(gold_sql, db_path)
        if exec_res.ok:
            gold_ok_count += 1
        else:
            print(f"WARNING: Gold failed on qid {qid}: {exec_res.error}")

        case_obj = {
            "case_id": f"bird_{qid}",
            "question_id": qid,
            "db_id": db_id,
            "question": item["question"],
            "evidence": item.get("evidence") or "",
            "bird_gold_sql": gold_sql,
            "bird_difficulty": diff,
            "t2s_stratum": stratum,
            "source": {"dataset": "BIRD Mini-Dev", "question_id": qid},
            "inference": {
                "question": item["question"],
                "evidence": item.get("evidence") or "",
                "db_id": db_id,
            },
            "gold": {
                "sql_original": gold_sql,
                "bird_difficulty": diff,
                "stratum": stratum,
            },
        }
        lines.append(json.dumps(case_obj))

    OUTPUT_DATASET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dataset_sha = hashlib.sha256(OUTPUT_DATASET.read_bytes()).hexdigest()
    print(f"Wrote {len(lines)} cases to {OUTPUT_DATASET} (SHA256: {dataset_sha})")

    manifest = {
        "manifest_version": "v1.0",
        "dataset_name": "t2s_final_holdout_v1",
        "total_cases": len(lines),
        "dataset_sha256": dataset_sha,
        "source_sha256": source_sha,
        "partition_manifest_sha256": part_manifest_sha,
        "question_ids": holdout_ids,
        "database_count": len(db_counts),
        "databases": dict(db_counts.most_common()),
        "difficulty_distribution": dict(diff_counts),
        "gold_executability": {
            "total": len(lines),
            "ok": gold_ok_count,
            "rate": round(gold_ok_count / len(lines), 4),
        },
    }

    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote manifest to {OUTPUT_MANIFEST}")


if __name__ == "__main__":
    materialize()
