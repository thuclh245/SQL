#!/usr/bin/env python3
"""Build a deterministic 100-case T2S evaluation set from the user's local BIRD Mini-Dev file.

No benchmark question/SQL is invented by this script. It only selects and wraps records that
already exist in the supplied canonical BIRD JSON.
"""

import argparse
import collections
import hashlib
import json
import math
import re
from pathlib import Path

DEFAULT_QUOTAS = {"S1": 25, "S2": 30, "S3": 30, "S4": 15}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_bird(path: Path):
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("BIRD JSON must be a JSON list or JSONL")
        return data
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_jsonl(path: Path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def sql_features(sql: str):
    u = " " + re.sub(r"\s+", " ", sql.upper()) + " "
    n_select = len(re.findall(r"\bSELECT\b", u))
    n_join = len(re.findall(r"\bJOIN\b", u))
    cte = bool(re.search(r"^\s*WITH\b", sql, re.I))
    window = bool(re.search(r"\bOVER\s*\(", sql, re.I))
    set_op = bool(re.search(r"\b(UNION|INTERSECT|EXCEPT)\b", sql, re.I))
    subquery = n_select >= 2
    sub_deep = n_select >= 3
    having = bool(re.search(r"\bHAVING\b", sql, re.I))
    return {
        "CTE": cte,
        "window": window,
        "set_op": set_op,
        "subquery": subquery,
        "sub_deep": sub_deep,
        "HAVING": having,
        "n_join": n_join,
        "n_select": n_select,
    }


def classify(features):
    if features["CTE"] or features["window"] or features["set_op"] or features["sub_deep"]:
        return "S4"
    if features["n_join"] >= 2 or features["subquery"] or features["HAVING"]:
        return "S3"
    if features["n_join"] == 1:
        return "S2"
    return "S1"


def stable_key(seed: str, row) -> str:
    qid = str(row.get("question_id"))
    db = str(row.get("db_id"))
    return hashlib.sha256(f"{seed}|{db}|{qid}".encode()).hexdigest()


def pick_balanced(candidates, quota, selected_db_counts, seed, max_per_db):
    pool = sorted(candidates, key=lambda r: stable_key(seed, r))
    chosen = []
    while pool and len(chosen) < quota:
        eligible = [r for r in pool if selected_db_counts[r["db_id"]] < max_per_db]
        if not eligible:
            eligible = pool
        min_count = min(selected_db_counts[r["db_id"]] for r in eligible)
        eligible = [r for r in eligible if selected_db_counts[r["db_id"]] == min_count]
        pick = min(eligible, key=lambda r: stable_key(seed, r))
        chosen.append(pick)
        selected_db_counts[pick["db_id"]] += 1
        pool.remove(pick)
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bird-json", required=True, type=Path)
    ap.add_argument("--exclude-jsonl", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--seed", default="t2s-eval-v1-2026-09")
    args = ap.parse_args()

    bird = load_bird(args.bird_json)
    pilot = load_jsonl(args.exclude_jsonl)
    excluded_qids = {
        (r.get("source") or {}).get("question_id")
        for r in pilot
        if (r.get("source") or {}).get("question_id") is not None
    }
    excluded_questions = {
        ((r.get("inference") or {}).get("question") or "").strip().casefold()
        for r in pilot
        if (r.get("inference") or {}).get("question")
    }

    normalized = []
    seen_qids = set()
    for r in bird:
        qid = r.get("question_id")
        question = (r.get("question") or "").strip()
        sql = (r.get("SQL") or r.get("sql") or "").strip()
        db_id = (r.get("db_id") or "").strip()
        if qid in excluded_qids or question.casefold() in excluded_questions:
            continue
        if not question or not sql or not db_id or qid is None:
            continue
        if qid in seen_qids:
            continue
        seen_qids.add(qid)
        f = sql_features(sql)
        r2 = dict(r)
        r2["_features"] = f
        r2["_stratum"] = classify(f)
        normalized.append(r2)

    by_stratum = collections.defaultdict(list)
    for r in normalized:
        by_stratum[r["_stratum"]].append(r)

    for s, quota in DEFAULT_QUOTAS.items():
        if len(by_stratum[s]) < quota:
            raise SystemExit(
                f"Insufficient unseen BIRD cases for {s}: need {quota}, have {len(by_stratum[s])}. "
                "Do not silently relax quotas; inspect source/version or choose a new explicit "
                "config."
            )

    dbs = sorted({r["db_id"] for r in normalized})
    max_per_db = max(12, math.ceil(100 / max(1, len(dbs))) + 2)
    selected_db_counts = collections.Counter()
    chosen = []
    for s in ["S4", "S3", "S2", "S1"]:  # rare/complex first to protect quotas
        picked = pick_balanced(
            by_stratum[s], DEFAULT_QUOTAS[s], selected_db_counts, args.seed + "|" + s, max_per_db
        )
        if len(picked) != DEFAULT_QUOTAS[s]:
            raise SystemExit(f"Could not fill quota for {s}: {len(picked)}/{DEFAULT_QUOTAS[s]}")
        chosen.extend(picked)

    # Stable final order independent from selection loop.
    chosen = sorted(chosen, key=lambda r: stable_key(args.seed + "|final", r))
    source_sha = sha256_file(args.bird_json)

    out_rows = []
    for i, r in enumerate(chosen, 1):
        qid = r["question_id"]
        sql = r.get("SQL") or r.get("sql")
        out_rows.append(
            {
                "case_id": f"bird_{qid}",
                "inference": {
                    "question": r["question"],
                    "evidence": r.get("evidence", ""),
                    "db_id": r["db_id"],
                },
                "gold": {
                    "stratum": r["_stratum"],
                    "subtype": None,
                    "bird_difficulty": r.get("difficulty"),
                    "sql_features": r["_features"],
                    "sql_original": sql,
                    "sql_corrected": sql,
                    "corrected_diff": False,
                    "execution": None,
                },
                "source": {
                    "dataset": "bird_mini_dev_sqlite",
                    "question_id": qid,
                    "split_role": "evaluation",
                    "source_sha256": source_sha,
                },
                "eval_id": f"t2s_eval_v1_{i:03d}",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows),
        encoding="utf-8",
    )

    counts_s = collections.Counter(r["gold"]["stratum"] for r in out_rows)
    counts_db = collections.Counter(r["inference"]["db_id"] for r in out_rows)
    counts_diff = collections.Counter(r["gold"]["bird_difficulty"] for r in out_rows)
    manifest = {
        "benchmark_id": "t2s_eval_v1",
        "count": len(out_rows),
        "selector_seed": args.seed,
        "source_path": str(args.bird_json),
        "source_sha256": source_sha,
        "excluded_bird_question_ids": len(excluded_qids),
        "strata": dict(sorted(counts_s.items())),
        "databases": dict(sorted(counts_db.items())),
        "bird_difficulty": {
            str(k): v for k, v in sorted(counts_diff.items(), key=lambda x: str(x[0]))
        },
        "gold_policy": "official_bird_unchanged_on_first_run",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
