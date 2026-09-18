#!/usr/bin/env python3
import argparse
import collections
import json
from pathlib import Path


def load_jsonl(path: Path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    rows = load_jsonl(args.dataset)

    strata = collections.Counter((r.get("gold") or {}).get("stratum") for r in rows)
    dbs = collections.Counter((r.get("inference") or {}).get("db_id") for r in rows)
    datasets = collections.Counter((r.get("source") or {}).get("dataset") for r in rows)
    missing_q = [r.get("case_id") for r in rows if not (r.get("inference") or {}).get("question")]
    changed = [r for r in rows if (r.get("gold") or {}).get("corrected_diff") is True]
    changed_result = [
        r
        for r in changed
        if ((r.get("gold") or {}).get("execution") or {}).get("results_match") is False
    ]
    ids = [r.get("case_id") for r in rows]
    qids = [
        (r.get("source") or {}).get("question_id")
        for r in rows
        if (r.get("source") or {}).get("question_id") is not None
    ]

    summary = {
        "count": len(rows),
        "strata": dict(strata),
        "databases": dict(dbs),
        "source_datasets": dict(datasets),
        "missing_question_count": len(missing_q),
        "missing_question_case_ids": missing_q,
        "corrected_diff_count": len(changed),
        "corrected_result_changed_count": len(changed_result),
        "duplicate_case_ids": [x for x, n in collections.Counter(ids).items() if n > 1],
        "duplicate_question_ids": [x for x, n in collections.Counter(qids).items() if n > 1],
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
