#!/usr/bin/env python3
"""Build a reproducible, leak-free 100-case evaluation set from official BIRD Mini-Dev.

Selection ensures zero overlap with the pilot benchmark (pilot_qids ∩ eval_qids = ∅),
covers all 11 BIRD databases, preserves official BIRD difficulty, and recomputes
SQL structural complexity features using the sqlglot AST parser.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

DEFAULT_SEED = 20260914


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def load_bird_json(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8").strip()
    if raw.startswith("["):
        return json.loads(raw)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def extract_sql_features(sql: str) -> dict[str, Any]:
    """Parse SQL AST via sqlglot and compute structural features."""
    ast = sqlglot.parse_one(sql, read="sqlite")
    joins = len(list(ast.find_all(exp.Join)))
    selects = len(list(ast.find_all(exp.Select)))
    subqueries = len(list(ast.find_all(exp.Subquery)))
    ctes = len(list(ast.find_all(exp.CTE)))
    windows = len(list(ast.find_all(exp.Window)))
    set_ops = len(list(ast.find_all((exp.Union, exp.Intersect, exp.Except))))
    has_agg = bool(ast.find(exp.AggFunc))
    has_group = bool(ast.find(exp.Group))
    has_having = bool(ast.find(exp.Having))
    has_order = bool(ast.find(exp.Order))

    def get_depth(node: Any) -> int:
        if not hasattr(node, "iter_expressions"):
            return 1
        children = [get_depth(c) for c in node.iter_expressions()]
        return 1 + max(children, default=0)

    depth = get_depth(ast)

    if ctes > 0 or windows > 0 or set_ops > 0 or selects >= 3:
        stratum = "S4"
    elif joins >= 2 or subqueries > 0 or selects >= 2 or has_having:
        stratum = "S3"
    elif joins == 1:
        stratum = "S2"
    else:
        stratum = "S1"

    return {
        "join_count": joins,
        "select_count": selects,
        "subquery_count": subqueries,
        "cte_count": ctes,
        "window_count": windows,
        "set_operation_count": set_ops,
        "aggregation": has_agg,
        "group_by": has_group,
        "having": has_having,
        "order_by": has_order,
        "nested_depth": depth,
        "stratum": stratum,
    }


def stable_hash_key(seed: int, db_id: str, question_id: int) -> str:
    payload = f"{seed}:{db_id}:{question_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build T2S Eval v1 dataset.")
    parser.add_argument(
        "--bird-json",
        type=Path,
        default=Path(
            "/home/thuclh245/MyCode/Text2sql/third_party/mini_dev/llm/mini_dev_data/mini_dev_sqlite.json"
        ),
        help="Path to canonical BIRD mini_dev_sqlite.json",
    )
    parser.add_argument(
        "--pilot-jsonl",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"),
        help="Path to pilot dataset to exclude",
    )
    parser.add_argument(
        "--output-dataset",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_eval_v1.jsonl"),
        help="Path to output eval JSONL",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=Path("benchmarks/t2s/manifests/t2s_eval_v1_manifest.json"),
        help="Path to output manifest JSON",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed")
    args = parser.parse_args()

    bird_data = load_bird_json(args.bird_json)
    pilot_data = load_jsonl(args.pilot_jsonl)

    pilot_qids = {
        r["source"]["question_id"]
        for r in pilot_data
        if (r.get("source") or {}).get("question_id") is not None
    }
    excluded_hash = hashlib.sha256(
        ",".join(str(q) for q in sorted(pilot_qids)).encode()
    ).hexdigest()

    candidates = [d for d in bird_data if d["question_id"] not in pilot_qids]
    for c in candidates:
        c["features"] = extract_sql_features(c["SQL"])

    # Target distribution
    # Note: Across entire BIRD Mini-Dev (500 cases), only 21 are S4 (CTEs, Windows, SetOps,
    # or >=3 SELECTs). The pilot previously incorporated 15 S4 cases, leaving exactly 7
    # in the remaining 415 pool. We exhaustively select all 7 remaining S4 cases and distribute
    # the remaining 93 slots across S1 (25), S3 (30), and S2 (38) while balancing across all 11 DBs.
    quotas = {"S1": 25, "S2": 38, "S3": 30, "S4": 7}
    selected: list[dict[str, Any]] = []
    db_counts: Counter[str] = Counter()

    # 1. Take all available S4 cases (ordered deterministically)
    s4_pool = sorted(
        [c for c in candidates if c["features"]["stratum"] == "S4"],
        key=lambda x: stable_hash_key(args.seed, x["db_id"], x["question_id"]),
    )
    for item in s4_pool:
        selected.append(item)
        db_counts[item["db_id"]] += 1

    # 2. Pick balanced distribution for S1, S3, S2
    for strat in ["S1", "S3", "S2"]:
        target = quotas[strat]
        pool = sorted(
            [c for c in candidates if c["features"]["stratum"] == strat and c not in selected],
            key=lambda x: stable_hash_key(args.seed, x["db_id"], x["question_id"]),
        )
        picked: list[dict[str, Any]] = []
        while len(picked) < target and pool:
            min_count = min(db_counts[item["db_id"]] for item in pool)
            eligible = [item for item in pool if db_counts[item["db_id"]] == min_count]
            pick = min(
                eligible,
                key=lambda x: stable_hash_key(args.seed, x["db_id"], x["question_id"]),
            )
            picked.append(pick)
            db_counts[pick["db_id"]] += 1
            pool.remove(pick)
        selected.extend(picked)

    # Sort final dataset by question_id for consistent ordering
    selected.sort(key=lambda x: x["question_id"])

    # Format JSONL records
    jsonl_lines = []
    for item in selected:
        qid = item["question_id"]
        db_id = item["db_id"]
        question = item["question"]
        evidence = item.get("evidence", "")
        gold_sql = item["SQL"]
        difficulty = item.get("difficulty", "moderate")
        stratum = item["features"]["stratum"]

        record = {
            "case_id": f"bird_eval_{qid}",
            "question_id": qid,
            "db_id": db_id,
            "question": question,
            "evidence": evidence,
            "bird_gold_sql": gold_sql,
            "bird_difficulty": difficulty,
            "t2s_stratum": stratum,
            "sql_features": item["features"],
            "source": {
                "dataset": "BIRD Mini-Dev",
                "question_id": qid,
            },
            # Compatible inference & gold wrappers
            "inference": {
                "question": question,
                "db_id": db_id,
                "evidence": evidence,
            },
            "gold": {
                "sql_original": gold_sql,
                "sql_corrected": gold_sql,
                "stratum": stratum,
                "bird_difficulty": difficulty,
            },
        }
        jsonl_lines.append(json.dumps(record, ensure_ascii=False))

    args.output_dataset.parent.mkdir(parents=True, exist_ok=True)
    args.output_dataset.write_text("\n".join(jsonl_lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(jsonl_lines)} evaluation cases to {args.output_dataset}")

    # Build manifest
    manifest = {
        "benchmark": "T2S Eval v1",
        "case_count": len(selected),
        "source_file": str(args.bird_json),
        "source_sha256": sha256_file(args.bird_json),
        "seed": args.seed,
        "selection_version": "v1.0.0-ast-stratified",
        "excluded_pilot_count": len(pilot_qids),
        "excluded_pilot_hash": excluded_hash,
        "overlap_with_pilot": len(set(x["question_id"] for x in selected) & pilot_qids),
        "strata_breakdown": dict(Counter(x["features"]["stratum"] for x in selected)),
        "bird_difficulty_breakdown": dict(Counter(x.get("difficulty") for x in selected)),
        "database_coverage_count": len(db_counts),
        "database_breakdown": dict(db_counts),
        "selected_question_ids": [x["question_id"] for x in selected],
    }

    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote evaluation manifest to {args.output_manifest}")


if __name__ == "__main__":
    main()
