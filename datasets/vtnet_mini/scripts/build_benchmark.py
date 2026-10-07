#!/usr/bin/env python3
"""
build_benchmark.py
==================
Xây dựng bộ benchmark 100 câu hỏi cho VTNet Mini:
- Nạp danh sách 100 test cases từ benchmark/cases.py.
- Chạy từng gold SQL DuckDB trên generated/vtnet.duckdb để tạo expected answers (ground truth).
- Tính hash sha256 và lưu kết quả chi tiết.
- Xuất ra 4 artifact chuẩn:
  1. benchmark/questions.csv
  2. benchmark/cases.jsonl
  3. benchmark/answers.jsonl
  4. benchmark/report.json
"""

import csv
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import duckdb

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.append(str(PROJECT_DIR))

from benchmark.cases import get_benchmark_cases

DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"
BENCHMARK_DIR = PROJECT_DIR / "benchmark"

def compute_result_hash(columns, rows):
    """
    Tính sha256 hash chuẩn hoá cho bảng kết quả để đối soát deterministic:
    - Sắp xếp cột theo tên hoặc giữ nguyên thứ tự
    - Chuyển từng cell sang string đại diện
    """
    norm_rows = []
    for row in rows:
        norm_row = [str(val) if val is not None else "NULL" for val in row]
        norm_rows.append(norm_row)
    # Sắp xếp rows để hash không bị ảnh hưởng nếu không có ORDER BY
    norm_rows_sorted = sorted(norm_rows)
    payload = json.dumps({"columns": columns, "rows": norm_rows_sorted}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def build_benchmark():
    print("=== BẮT ĐẦU BUILD BENCHMARK VTNET MINI ===")
    print(f"Database: {DUCKDB_PATH}")
    print(f"Benchmark Dir: {BENCHMARK_DIR}")
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"Database {DUCKDB_PATH} không tồn tại!")

    cases = get_benchmark_cases()
    print(f"Tổng số cases đã nạp: {len(cases)}")

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)

    questions_rows = []
    cases_records = []
    answers_records = []
    passed_cases = 0
    failed_cases = 0
    domain_counter = Counter()
    diff_counter = Counter()

    t_start = time.time()

    for idx, c in enumerate(cases, 1):
        cid = c["id"]
        q = c["question"]
        diff = c["difficulty"]
        domain = c["domain"]
        sql_duckdb = c["gold_sql_duckdb"]
        sql_trino = c["gold_sql_trino"]
        tables = c["required_tables"]
        skills = c.get("skills", [])

        domain_counter[domain] += 1
        diff_counter[diff] += 1

        questions_rows.append({
            "id": cid,
            "difficulty": diff,
            "domain": domain,
            "question": q
        })

        case_obj = {
            "id": cid,
            "question": q,
            "difficulty": diff,
            "domain": domain,
            "gold_sql_duckdb": sql_duckdb,
            "gold_sql_trino": sql_trino,
            "required_tables": tables,
            "skills": skills
        }
        cases_records.append(case_obj)

        # Thực thi query DuckDB
        try:
            cur = con.execute(sql_duckdb)
            columns = [col[0] for col in cur.description]
            raw_rows = cur.fetchall()
            row_count = len(raw_rows)
            res_hash = compute_result_hash(columns, raw_rows)
            sample_rows = [list(r) for r in raw_rows[:5]]

            answer_obj = {
                "id": cid,
                "gold_sql": sql_duckdb,
                "columns": columns,
                "row_count": row_count,
                "result_sha256": res_hash,
                "sample_rows": sample_rows,
                "status": "PASS"
            }
            passed_cases += 1
        except Exception as err:
            answer_obj = {
                "id": cid,
                "gold_sql": sql_duckdb,
                "columns": [],
                "row_count": 0,
                "result_sha256": None,
                "sample_rows": [],
                "status": f"FAIL: {str(err)}"
            }
            failed_cases += 1
            print(f"[FAIL] {cid}: {err}")

        answers_records.append(answer_obj)

    t_elapsed = round(time.time() - t_start, 3)

    # 1. Ghi questions.csv
    csv_file = BENCHMARK_DIR / "questions.csv"
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "difficulty", "domain", "question"])
        writer.writeheader()
        writer.writerows(questions_rows)
    print(f"-> Đã ghi {csv_file}")

    # 2. Ghi cases.jsonl
    cases_file = BENCHMARK_DIR / "cases.jsonl"
    with open(cases_file, "w", encoding="utf-8") as f:
        for obj in cases_records:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"-> Đã ghi {cases_file}")

    # 3. Ghi answers.jsonl
    answers_file = BENCHMARK_DIR / "answers.jsonl"
    with open(answers_file, "w", encoding="utf-8") as f:
        for obj in answers_records:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"-> Đã ghi {answers_file}")

    # 4. Ghi report.json
    report_obj = {
        "benchmark_name": "VTNet Mini 100 NL2SQL Benchmark",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": len(cases),
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "pass_rate_percent": round((passed_cases / len(cases)) * 100, 2) if cases else 0,
        "execution_time_seconds": t_elapsed,
        "difficulty_distribution": dict(diff_counter),
        "domain_distribution": dict(domain_counter),
        "status": "ALL_PASSED" if failed_cases == 0 else "HAS_FAILURES"
    }
    report_file = BENCHMARK_DIR / "report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_obj, f, ensure_ascii=False, indent=2)
    print(f"-> Đã ghi {report_file}")

    print(f"\n=== HOÀN TẤT BUILD BENCHMARK: {passed_cases}/{len(cases)} PASS ({report_obj['pass_rate_percent']}%) trong {t_elapsed}s ===")

if __name__ == "__main__":
    build_benchmark()
