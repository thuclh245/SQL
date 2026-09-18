#!/usr/bin/env python3
"""Audit T2S Pilot v1 against official BIRD Mini-Dev.

Evaluates Gates 1 through 8 and generates:
- pilot_compatibility_report.json
- pilot_gold_correction_review.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def load_bird_official(path: Path) -> dict[int, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {item["question_id"]: item for item in raw}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit T2S Pilot v1.")
    parser.add_argument(
        "--pilot",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"),
        help="Path to t2s_pilot_v1.jsonl",
    )
    parser.add_argument(
        "--bird-json",
        type=Path,
        default=Path(
            "/home/thuclh245/MyCode/Text2sql/third_party/mini_dev/llm/mini_dev_data/mini_dev_sqlite.json"
        ),
        help="Path to official mini_dev_sqlite.json",
    )
    parser.add_argument(
        "--official-db-dir",
        type=Path,
        default=Path("benchmarks/t2s/databases/official"),
        help="Path to official DB directory",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path("benchmarks/t2s/manifests/pilot_compatibility_report.json"),
        help="Output path for compatibility JSON report",
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        default=Path("benchmarks/t2s/manifests/pilot_gold_correction_review.csv"),
        help="Output path for correction review CSV",
    )
    args = parser.parse_args()

    pilot_rows = load_jsonl(args.pilot)
    bird_official = load_bird_official(args.bird_json)

    total_slots = len(pilot_rows)
    executable_bird = [
        r for r in pilot_rows if (r.get("source") or {}).get("question_id") is not None
    ]
    stubs = [
        r
        for r in pilot_rows
        if r.get("status") == "stub_pending" or not (r.get("inference") or {}).get("question")
    ]
    robustness_slots = len(stubs)

    # Gate 1: Source identity
    gate1_failures = []
    for r in executable_bird:
        qid = r["source"]["question_id"]
        if qid not in bird_official:
            gate1_failures.append(r["case_id"])
    gate1_status = "PASS" if not gate1_failures else "FAIL"

    # Gate 2: Database identity
    gate2_failures = []
    for r in executable_bird:
        qid = r["source"]["question_id"]
        db_id = r["inference"]["db_id"]
        if qid in bird_official and bird_official[qid]["db_id"] != db_id:
            gate2_failures.append(f"{r['case_id']}: {db_id} != {bird_official[qid]['db_id']}")
    gate2_status = "PASS" if not gate2_failures else "FAIL"

    # Gate 3: Question identity
    gate3_failures = []
    for r in executable_bird:
        qid = r["source"]["question_id"]
        pilot_q = (r["inference"].get("question") or "").strip()
        if qid in bird_official:
            official_q = bird_official[qid]["question"].strip()
            if pilot_q != official_q:
                gate3_failures.append(r["case_id"])
    gate3_status = "PASS" if not gate3_failures else "FAIL"

    # Gate 4: Evidence identity
    gate4_mismatches = []
    for r in executable_bird:
        qid = r["source"]["question_id"]
        pilot_ev = (r["inference"].get("evidence") or "").strip()
        if qid in bird_official:
            official_ev = (bird_official[qid].get("evidence") or "").strip()
            if pilot_ev != official_ev:
                gate4_mismatches.append(r["case_id"])
    gate4_status = "PASS" if not gate4_mismatches else "PARTIAL"

    # Gate 5: Gold provenance
    # Verify official gold preserved in sql_original and corrections separated in sql_corrected
    gate5_failures = []
    corrected_rows = []
    unchanged_count = 0
    for r in executable_bird:
        qid = r["source"]["question_id"]
        orig_sql = (r.get("gold") or {}).get("sql_original")
        corr_sql = (r.get("gold") or {}).get("sql_corrected")
        if not orig_sql:
            gate5_failures.append(f"{r['case_id']}: missing sql_original")
        elif qid in bird_official and orig_sql != bird_official[qid]["SQL"]:
            gate5_failures.append(f"{r['case_id']}: sql_original differs from official BIRD")

        if orig_sql == corr_sql:
            unchanged_count += 1
        else:
            corrected_rows.append(r)
    gate5_status = "PASS" if not gate5_failures else "FAIL"

    # Gate 6: Database availability
    gate6_failures = []
    for r in executable_bird:
        db_id = r["inference"]["db_id"]
        db_path = args.official_db_dir / db_id / f"{db_id}.sqlite"
        if not db_path.exists() or db_path.stat().st_size == 0:
            gate6_failures.append(f"{r['case_id']}: db {db_id} missing or empty")
    gate6_status = "PASS" if not gate6_failures else "FAIL"

    # Gate 7: Gold executability & result comparison for corrections
    gate7_failures = []
    result_diff_count = 0
    csv_records = []

    for r in executable_bird:
        cid = r["case_id"]
        qid = r["source"]["question_id"]
        db_id = r["inference"]["db_id"]
        orig_sql = r["gold"]["sql_original"]
        corr_sql = r["gold"]["sql_corrected"]
        stratum = r["gold"]["stratum"]
        question = r["inference"]["question"]

        db_path = args.official_db_dir / db_id / f"{db_id}.sqlite"
        uri = f"file:{db_path.resolve()}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=30)
        try:
            con.execute("PRAGMA query_only = ON")
            res_orig = con.execute(orig_sql).fetchall()
        except Exception as e:
            gate7_failures.append(f"{cid} (original): {e}")
            res_orig = None

        try:
            res_corr = con.execute(corr_sql).fetchall()
        except Exception as e:
            gate7_failures.append(f"{cid} (corrected): {e}")
            res_corr = None
        con.close()

        results_match = (
            (res_orig == res_corr) if (res_orig is not None and res_corr is not None) else False
        )

        if orig_sql != corr_sql:
            if not results_match:
                result_diff_count += 1
            csv_records.append(
                {
                    "case_id": cid,
                    "question_id": qid,
                    "db_id": db_id,
                    "stratum": stratum,
                    "results_match": results_match,
                    "risk_flags": (
                        "execution_result_changed"
                        if not results_match
                        else "syntax_formatting_only"
                    ),
                    "question": question,
                    "sql_original": orig_sql,
                    "sql_corrected": corr_sql,
                    "review_status": "NEEDS_MANUAL_REVIEW",
                    "rationale": (
                        "Execution result differs from official BIRD"
                        if not results_match
                        else "Query reformatting/standardization"
                    ),
                }
            )

    gate7_status = "PASS" if not gate7_failures else "FAIL"

    # Gate 8: Duplicate detection
    case_ids = [r["case_id"] for r in pilot_rows]
    qids = [r["source"]["question_id"] for r in executable_bird]
    dup_case_ids = [k for k, v in Counter(case_ids).items() if v > 1]
    dup_qids = [k for k, v in Counter(qids).items() if v > 1]
    gate8_status = "PASS" if (not dup_case_ids and not dup_qids) else "FAIL"

    # Compile Audit Report
    report = {
        "summary": {
            "total_slots": total_slots,
            "executable_bird_cases": len(executable_bird),
            "robustness_slots": robustness_slots,
            "stub_cases": len(stubs),
            "exact_official_matches": (
                len(executable_bird) - len(gate1_failures) - len(gate3_failures)
            ),
            "modified_questions": len(gate3_failures),
            "missing_ids": len(gate1_failures),
            "duplicates": len(dup_case_ids) + len(dup_qids),
        },
        "gold_sql_audit": {
            "official_unchanged": unchanged_count,
            "corrected": len(corrected_rows),
            "corrections_with_different_execution_result": result_diff_count,
            "corrections_with_matching_execution_result": len(corrected_rows) - result_diff_count,
            "needs_manual_review": len(corrected_rows),
        },
        "gates": {
            "gate_1_source_identity": {"status": gate1_status, "failures": gate1_failures},
            "gate_2_database_identity": {"status": gate2_status, "failures": gate2_failures},
            "gate_3_question_identity": {"status": gate3_status, "failures": gate3_failures},
            "gate_4_evidence_identity": {
                "status": gate4_status,
                "mismatches": len(gate4_mismatches),
            },
            "gate_5_gold_provenance": {"status": gate5_status, "failures": gate5_failures},
            "gate_6_database_availability": {"status": gate6_status, "failures": gate6_failures},
            "gate_7_gold_executability": {"status": gate7_status, "failures": gate7_failures},
            "gate_8_duplicate_detection": {
                "status": gate8_status,
                "duplicate_case_ids": dup_case_ids,
                "duplicate_qids": dup_qids,
            },
        },
        "overall_compatibility_verdict": (
            "COMPATIBLE_WITH_CAVEATS"
            if gate1_status == "PASS" and gate2_status == "PASS" and gate7_status == "PASS"
            else "INCOMPATIBLE"
        ),
    }

    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote pilot compatibility report to {args.report_json}")

    # Write review CSV
    args.review_csv.parent.mkdir(parents=True, exist_ok=True)
    if csv_records:
        fieldnames = [
            "case_id",
            "question_id",
            "db_id",
            "stratum",
            "results_match",
            "risk_flags",
            "question",
            "sql_original",
            "sql_corrected",
            "review_status",
            "rationale",
        ]
        with args.review_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_records)
        print(f"Wrote gold correction review queue to {args.review_csv} ({len(csv_records)} rows)")


if __name__ == "__main__":
    main()
