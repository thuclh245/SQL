#!/usr/bin/env python3
"""Validate the convention registry and scan benchmark gold SQL for violations.

1. Fixtures: every accepted convention must accept all of its `pass` SQL
   (no false positive on equivalent spellings) and reject all of its `fail` SQL.
2. Gold scan: every answer case in benchmark_v2 is checked against each
   accepted convention that applies to it (by question terms and tables).
   Violations are reported for DE review, not auto-fixed: either the gold is
   wrong or the convention is too broad.

Exit code 1 only when a fixture fails (the checker itself is wrong).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convention_checks import ROOT, applies, is_executable, load_registry, run_check  # noqa: E402

CASES = ROOT / "benchmark_v2" / "cases.jsonl"
OUT = ROOT / "reports" / "convention_validation.json"


def main() -> int:
    registry = load_registry()
    accepted = [c for c in registry["conventions"] if c["status"] == "accepted"]
    fixture_failures, fixture_counts = [], {"pass_total": 0, "fail_total": 0}
    for conv in accepted:
        if not is_executable(conv):
            fixture_failures.append(f"{conv['id']}: accepted nhưng check '{conv['check']['kind']}' chưa được implement")
            continue
        fixtures = conv.get("fixtures") or {}
        if not fixtures.get("pass") or not fixtures.get("fail"):
            fixture_failures.append(f"{conv['id']}: thiếu fixture pass/fail")
        for sql in fixtures.get("pass", []):
            fixture_counts["pass_total"] += 1
            if violations := run_check(sql, conv):
                fixture_failures.append(f"{conv['id']}: SQL đúng bị từ chối ({violations}): {sql}")
        for sql in fixtures.get("fail", []):
            fixture_counts["fail_total"] += 1
            if not run_check(sql, conv):
                fixture_failures.append(f"{conv['id']}: SQL vi phạm không bị bắt: {sql}")

    gold_violations, checked = [], 0
    if CASES.exists():
        for line in CASES.read_text(encoding="utf-8").splitlines():
            case = json.loads(line)
            sql = case.get("gold_sql_duckdb")
            if case.get("expected_outcome") != "answer" or not sql:
                continue
            for conv in accepted:
                if is_executable(conv) and applies(conv, case, sql):
                    checked += 1
                    if violations := run_check(sql, conv):
                        gold_violations.append({"case": case["id"], "convention": conv["id"], "violations": violations})

    report = {
        "accepted": len(accepted),
        "proposed": sum(c["status"] == "proposed" for c in registry["conventions"]),
        "fixtures": {**fixture_counts, "failures": fixture_failures},
        "gold_scan": {"checks_run": checked, "violations": gold_violations},
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"accepted={report['accepted']} proposed={report['proposed']} "
          f"fixtures pass={fixture_counts['pass_total']} fail={fixture_counts['fail_total']} failures={len(fixture_failures)}")
    print(f"gold scan: {checked} checks, {len(gold_violations)} violations -> {OUT.relative_to(ROOT)}")
    for f in fixture_failures:
        print("FIXTURE FAIL", f, file=sys.stderr)
    return 1 if fixture_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
