#!/usr/bin/env python3
"""Evidence-first audit for VTNet Mini V1.1 artifacts.

Deliberately independent of build_v1_1_assets.py: leakage is detected from the
gold SQL and the schema of each case, not from the builder's own word lists, and
hashes are recomputed rather than trusted.

Exit 1 on hard failures (broken gold, hash mismatch, nondeterminism, leaked or
malformed natural questions, false provenance).  Everything else is reported
as review work.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "generated" / "vtnet.duckdb"
CASES = ROOT / "benchmark_v2" / "cases.jsonl"
CATALOG = ROOT / "metadata" / "catalog.json"
VARIANTS = ROOT / "metadata" / "variants"
CONVENTION_REPORT = ROOT / "reports" / "convention_validation.json"
OUT = ROOT / "reports" / "v1_1_asset_audit.json"

SQL_TOKENS = re.compile(
    r"\b(SELECT|FROM|WHERE|GROUP BY|HAVING|GROUPING SETS|ROLLUP|NOT EXISTS|LEFT JOIN|INNER JOIN|CROSS JOIN|"
    r"FULL OUTER JOIN|CTE|NTILE|ROW_NUMBER|DENSE_RANK|LAG|STDDEV_SAMP|Window Function|Anti-Join|CAST)\b"
)
IDENTIFIER = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
DANGLING = re.compile(r"(\(\s*\)|\b(bằng|với|và|qua phép|trong bảng)\s*[.?]?$)")


def result_hash(con, sql: str) -> str:
    cur = con.execute(sql)
    columns = [d[0] for d in cur.description]
    norm = sorted([[str(v) if v is not None else "NULL" for v in row] for row in cur.fetchall()])
    return hashlib.sha256(json.dumps({"columns": columns, "rows": norm}, ensure_ascii=False).encode()).hexdigest()


def main() -> int:
    cases = [json.loads(x) for x in CASES.read_text(encoding="utf-8").splitlines() if x.strip()]
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    schema_idents = {t["table_name"].lower() for t in catalog["tables"]}
    columns_by_table = {t["trino_fqn"]: {c["name"].lower() for c in t["columns"]} for t in catalog["tables"]}
    cons = [duckdb.connect(str(DB), read_only=True) for _ in range(3)]
    for i, con in enumerate(cons):
        con.execute(f"SET threads = {i + 1}")

    hard: dict[str, list] = {k: [] for k in (
        "failed_gold", "hash_mismatch", "nondeterministic", "natural_leak", "natural_malformed",
        "natural_equals_explicit", "missing_natural", "false_provenance", "m3_fake")}
    scored = [c for c in cases if not c.get("exclude_from_scoring")]

    for case in cases:
        nat = case.get("question_natural") or ""
        if not nat:
            hard["missing_natural"].append(case["id"])
        if case["expected_outcome"] != "answer":
            for opt in case.get("clarification_options", []):
                if opt.get("gold_sql_duckdb"):
                    h = {result_hash(con, opt["gold_sql_duckdb"]) for con in cons}
                    if len(h) > 1:
                        hard["nondeterministic"].append(f"{case['id']}:{opt['label']}")
                    elif opt.get("expected_result_sha256") not in h:
                        hard["hash_mismatch"].append(f"{case['id']}:{opt['label']}")
            continue
        gold = case["gold_sql_duckdb"]
        idents = set(IDENTIFIER.findall(gold.lower())) | schema_idents
        for t in case.get("required_tables", []):
            idents |= columns_by_table.get(t, set())
        leaked = sorted({w for w in IDENTIFIER.findall(nat.lower()) if w in idents} | set(SQL_TOKENS.findall(nat)))
        if leaked:
            hard["natural_leak"].append({"id": case["id"], "tokens": leaked})
        if DANGLING.search(nat.strip()):
            hard["natural_malformed"].append({"id": case["id"], "question_natural": nat})
        if nat.strip(" .?") == (case.get("question_explicit") or "").strip(" .?") and IDENTIFIER.search(case["question_explicit"].lower()):
            hard["natural_equals_explicit"].append(case["id"])
        try:
            hashes = {result_hash(con, gold) for con in cons}
        except Exception as exc:  # noqa: BLE001
            hard["failed_gold"].append({"id": case["id"], "error": str(exc)[:300]})
            continue
        if len(hashes) > 1:
            hard["nondeterministic"].append(case["id"])
        elif not case.get("exclude_from_scoring") and case.get("expected_result_sha256") not in hashes:
            hard["hash_mismatch"].append(case["id"])

    # provenance: the label must match the text actually present
    provenance = {}
    for name in ("M0", "M1", "M2"):
        v = json.loads((VARIANTS / name / "catalog.json").read_text(encoding="utf-8"))
        cols = [c for t in v["tables"] for c in t["columns"]]
        provenance[name] = dict(Counter(c.get("description_source") for c in cols))
        for t in v["tables"]:
            for c in t["columns"]:
                d, s = c.get("description") or "", c.get("description_source")
                ok = (
                    (s == "none" and not d)
                    or (s == "ai_gen" and d.startswith("[AI Gen]") and "[Profiler]" not in d)
                    or (s == "om_other" and d and not d.startswith("[AI Gen]") and "[Profiler]" not in d)
                    or (s == "profiler" and d.startswith("[Profiler]"))
                    or (s and s.endswith("+profiler") and "[Profiler]" in d and not d.startswith("[Profiler]"))
                )
                if not ok or s == "human":
                    hard["false_provenance"].append(f"{name}:{t['trino_fqn']}.{c['name']}={s}")
        if name == "M0" and any(t.get("description") for t in v["tables"]):
            hard["false_provenance"].append("M0: còn mô tả bảng")
    if (VARIANTS / "M3" / "catalog.json").exists():
        hard["m3_fake"].append("metadata/variants/M3/catalog.json tồn tại nhưng M3 cần DE viết tay")

    profile = json.loads((VARIANTS / "M2" / "profile_report.json").read_text(encoding="utf-8"))
    conv = json.loads(CONVENTION_REPORT.read_text(encoding="utf-8")) if CONVENTION_REPORT.exists() else None

    report = {
        "cases": len(cases),
        "scored": len(scored),
        "excluded_from_scoring": [c["id"] for c in cases if c.get("exclude_from_scoring")],
        "outcomes_scored": dict(Counter(c["expected_outcome"] for c in scored)),
        "answer_by_domain": dict(Counter(c["domain"] for c in scored if c["expected_outcome"] == "answer")),
        "review_status": dict(Counter(c["review_status"] for c in cases)),
        "hard_failures": hard,
        "review_work": {
            "review_flags": dict(Counter(f for c in cases for f in c.get("review_flags", {}))),
            "convention_conflicts": {c["id"]: [x["convention"] for x in c["convention_conflicts"]] for c in cases if c.get("convention_conflicts")},
            "convention_fixture_failures": conv["fixtures"]["failures"] if conv else "chưa chạy validate_conventions.py",
        },
        "metadata_provenance": provenance,
        "data_quality": {
            "profiler_summary": profile["summary"],
            "note": "constant/placeholder là cột lấp chỗ của dữ liệu synthetic; cần sửa generator (Phase 1)",
        },
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = {k: len(v) for k, v in hard.items() if v}
    print(json.dumps({"cases": report["cases"], "scored": report["scored"], "hard_failures": failures or "none"}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
