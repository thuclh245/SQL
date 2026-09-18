#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
from pathlib import Path


def load_jsonl(path: Path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def locate_db(root: Path, db_id: str) -> Path:
    candidates = [
        root / db_id / f"{db_id}.sqlite",
        root / db_id / f"{db_id}.db",
        root / f"{db_id}.sqlite",
        root / f"{db_id}.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"Cannot locate SQLite DB for {db_id} under {root}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--db-root", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--fetch-cap", type=int, default=10001)
    args = ap.parse_args()

    rows = load_jsonl(args.dataset)
    results = []
    for r in rows:
        cid = r["case_id"]
        db_id = r["inference"]["db_id"]
        sql = r["gold"]["sql_original"]
        rec = {
            "case_id": cid,
            "db_id": db_id,
            "ok": False,
            "row_count_observed": None,
            "truncated": False,
            "elapsed_ms": None,
            "error": None,
        }
        start = time.perf_counter()
        try:
            db = locate_db(args.db_root, db_id)
            uri = f"file:{db.resolve()}?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=30)
            try:
                con.execute("PRAGMA query_only = ON")
                cur = con.execute(sql)
                fetched = cur.fetchmany(args.fetch_cap)
                rec["row_count_observed"] = len(fetched)
                rec["truncated"] = len(fetched) >= args.fetch_cap
                rec["ok"] = True
            finally:
                con.close()
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        results.append(rec)

    summary = {
        "dataset": str(args.dataset),
        "count": len(results),
        "ok": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    raise SystemExit(1 if summary["failed"] else 0)


if __name__ == "__main__":
    main()
