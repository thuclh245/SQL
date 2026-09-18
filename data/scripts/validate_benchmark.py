#!/usr/bin/env python3
import argparse
import collections
import json
from pathlib import Path

BIRD_DBS = {
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


def load_jsonl(path: Path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--exclude-jsonl", type=Path)
    ap.add_argument("--expected-count", type=int)
    ap.add_argument("--require-all-bird-dbs", action="store_true")
    args = ap.parse_args()

    rows = load_jsonl(args.dataset)
    errors = []
    warnings = []
    if args.expected_count is not None and len(rows) != args.expected_count:
        errors.append(f"count={len(rows)} expected={args.expected_count}")

    case_ids = [r.get("case_id") for r in rows]
    qids = [(r.get("source") or {}).get("question_id") for r in rows]
    questions = [
        ((r.get("inference") or {}).get("question") or "").strip().casefold() for r in rows
    ]
    for name, vals in [("case_id", case_ids), ("question_id", qids), ("question", questions)]:
        dups = [x for x, n in collections.Counter(vals).items() if x not in (None, "") and n > 1]
        if dups:
            errors.append(f"duplicate {name}: {dups[:10]}")

    for r in rows:
        cid = r.get("case_id")
        inf = r.get("inference") or {}
        gold = r.get("gold") or {}
        src = r.get("source") or {}
        if not inf.get("question"):
            errors.append(f"{cid}: missing question")
        if not inf.get("db_id"):
            errors.append(f"{cid}: missing db_id")
        if not gold.get("sql_original"):
            errors.append(f"{cid}: missing gold SQL")
        if gold.get("stratum") not in {"S1", "S2", "S3", "S4"}:
            errors.append(f"{cid}: invalid eval stratum")
        if src.get("question_id") is None:
            errors.append(f"{cid}: missing source.question_id")
        if gold.get("corrected_diff") is True:
            warnings.append(f"{cid}: corrected_diff=true in sealed eval set")

    if args.exclude_jsonl:
        ex = load_jsonl(args.exclude_jsonl)
        ex_qids = {
            (r.get("source") or {}).get("question_id")
            for r in ex
            if (r.get("source") or {}).get("question_id") is not None
        }
        overlap = sorted({q for q in qids if q in ex_qids})
        if overlap:
            errors.append(f"overlap with excluded pilot question_ids: {overlap[:20]}")

    dbs = {((r.get("inference") or {}).get("db_id")) for r in rows}
    if args.require_all_bird_dbs:
        missing = sorted(BIRD_DBS - dbs)
        if missing:
            errors.append(f"missing BIRD databases: {missing}")

    summary = {
        "count": len(rows),
        "strata": dict(collections.Counter((r.get("gold") or {}).get("stratum") for r in rows)),
        "bird_difficulty": dict(
            collections.Counter((r.get("gold") or {}).get("bird_difficulty") for r in rows)
        ),
        "databases": dict(
            collections.Counter((r.get("inference") or {}).get("db_id") for r in rows)
        ),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
