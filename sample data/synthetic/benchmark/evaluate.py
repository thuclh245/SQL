"""Score a JSONL file of predicted SQLite queries by execution result.

Usage: python3 evaluate.py predictions.jsonl
Each line: {"id":"E001","sql":"SELECT ..."}
"""

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
DB = HERE.parent / "generated" / "telecom.sqlite"


def normalized(rows):
    # Column aliases and row order do not change the tabular answer.
    def cell(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return ("number", round(float(value), 6))
        return ("value", value)

    return Counter(tuple(cell(value) for value in row) for row in rows)


def main(path):
    answers = {item["id"]: item for line in (HERE / "answers.jsonl").read_text(encoding="utf-8").splitlines() if (item := json.loads(line))}
    cases = {item["id"]: item for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines() if (item := json.loads(line))}
    predictions = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["id"] in predictions:
            raise ValueError(f"Duplicate case ID: {item['id']}")
        if item["id"] not in cases:
            raise ValueError(f"Unknown case ID: {item['id']}")
        predictions[item["id"]] = item["sql"]

    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    results = []
    for case_id, case in cases.items():
        sql = predictions.get(case_id)
        if sql is None:
            results.append({"id": case_id, "difficulty": case["difficulty"], "status": "missing"})
            continue
        first_word = sql.lstrip().split(None, 1)
        if not first_word or first_word[0].upper() not in {"SELECT", "WITH"}:
            results.append({"id": case_id, "difficulty": case["difficulty"], "status": "invalid_sql"})
            continue
        try:
            rows = conn.execute(sql).fetchall()
            expected = answers[case_id]["rows"]
            status = "correct" if normalized(rows) == normalized(expected) else "wrong_answer"
        except sqlite3.Error as exc:
            status = "execution_error"
            results.append({"id": case_id, "difficulty": case["difficulty"], "status": status, "error": str(exc)})
            continue
        results.append({"id": case_id, "difficulty": case["difficulty"], "status": status})

    summary = {"total": len(results), "submitted": len(predictions), "correct": sum(item["status"] == "correct" for item in results)}
    summary["accuracy"] = round(summary["correct"] / summary["total"], 4)
    summary["by_difficulty"] = {
        level: {"correct": sum(item["difficulty"] == level and item["status"] == "correct" for item in results),
                "total": sum(item["difficulty"] == level for item in results)}
        for level in ("easy", "medium", "hard", "extreme")
    }
    print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 evaluate.py predictions.jsonl")
    main(sys.argv[1])
