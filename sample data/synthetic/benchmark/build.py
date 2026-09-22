"""Execute all gold SQL against the generated SQLite database and save benchmark artifacts."""

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from cases import CASES


HERE = Path(__file__).resolve().parent
DB = HERE.parent / "generated" / "telecom.sqlite"
PREFIX = {"easy": "E", "medium": "M", "hard": "H", "extreme": "X"}
EXPECTED = {"easy": 20, "medium": 20, "hard": 30, "extreme": 30}


def dump_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main():
    counts = Counter(case["difficulty"] for case in CASES)
    assert dict(counts) == EXPECTED, counts
    assert len({case["question_vi"] for case in CASES}) == 100
    assert len({case["gold_sql_sqlite"] for case in CASES}) == 100

    uri = f"file:{DB.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    found_tables = set()
    cases = []
    answers = []
    empty = []
    per_level = Counter()

    for case in CASES:
        level = case["difficulty"]
        per_level[level] += 1
        case_id = f"{PREFIX[level]}{per_level[level]:03d}"
        sql = case["gold_sql_sqlite"]
        assert re.match(r"^(SELECT|WITH)\b", sql, re.I), case_id
        mentioned = sorted(set(re.findall(r"\b[a-z][a-z0-9_]*__[a-z][a-z0-9_]*\b", sql)))
        assert mentioned and set(mentioned) <= tables, (case_id, mentioned)
        found_tables.update(mentioned)
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
        if not rows:
            empty.append(case_id)
        answer = {"id": case_id, "columns": columns, "rows": rows}
        digest = hashlib.sha256(dump_json(answer).encode("utf-8")).hexdigest()
        trino = re.sub(
            r"\b[a-z][a-z0-9_]*__[a-z][a-z0-9_]*\b",
            lambda match: match.group().replace("__", ".", 1),
            sql,
        )
        cases.append({
            "id": case_id,
            "difficulty": level,
            "question_vi": case["question_vi"],
            "gold_sql_sqlite": sql,
            "gold_sql_trino": trino,
            "tables": mentioned,
            "tags": case["tags"],
            "expected_columns": columns,
            "expected_row_count": len(rows),
            "answer_sha256": digest,
        })
        answers.append(answer)

    assert not empty, f"Empty gold results: {empty}"
    for filename, items in (("cases.jsonl", cases), ("answers.jsonl", answers)):
        (HERE / filename).write_text("".join(dump_json(item) + "\n" for item in items), encoding="utf-8")
    with (HERE / "questions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "difficulty", "question_vi", "expected_row_count"])
        writer.writeheader()
        writer.writerows({key: item[key] for key in writer.fieldnames} for item in cases)
    report = {
        "status": "PASS",
        "database": str(DB.relative_to(HERE.parent)),
        "cases": len(cases),
        "difficulty_counts": dict(counts),
        "tables_covered": len(found_tables),
        "schemas_covered": len({table.split("__", 1)[0] for table in found_tables}),
        "gold_queries_executed": len(answers),
        "empty_results": empty,
        "answer_rows": sum(len(answer["rows"]) for answer in answers),
        "sqlite_version": sqlite3.sqlite_version,
        "trino_executed": False,
    }
    (HERE / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
