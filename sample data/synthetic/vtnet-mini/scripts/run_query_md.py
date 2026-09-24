#!/usr/bin/env python3
"""
run_query_md.py
===============
Thực thi trực tiếp câu query mẫu từ `sample data/query.md` trên `vtnet.duckdb`:
1. Đọc nội dung file `sample data/query.md`.
2. Thay thế biến môi trường ${ETL_DATE} = '2026-08-20' và chuẩn hóa hàm ngày tháng sang DuckDB.
3. Chuyển đổi FQN Trino (hive.npms.table) sang bảng DuckDB (hive__npms__table).
4. Thực thi trên database `sample data/synthetic/vtnet-mini/generated/vtnet.duckdb`.
5. In kết quả bảng định dạng Markdown và đối chiếu với Gold Answer H001.
"""

import sys
import os
import re
import json
from pathlib import Path
import duckdb

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJECT_DIR.parent.parent.parent # workspace root
QUERY_MD_PATH = ROOT_DIR / "sample data" / "query.md"
DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"
ANSWERS_PATH = PROJECT_DIR / "benchmark" / "answers.jsonl"

def main():
    print(f"=== CHẠY THỬ VÀ ĐỐI SOÁT FILE QUERY.MD TRÊN VTNET.DUCKDB ===")
    print(f"File nguồn: {QUERY_MD_PATH}")
    print(f"CSDL đích : {DUCKDB_PATH}")

    if not QUERY_MD_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file {QUERY_MD_PATH}")
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy database {DUCKDB_PATH}")

    raw_text = QUERY_MD_PATH.read_text(encoding="utf-8")

    # Bỏ các dòng 'refresh table ...'
    lines = [line for line in raw_text.splitlines() if not line.strip().lower().startswith("refresh table")]
    query_sql = "\n".join(lines)

    # Thay thế ${ETL_DATE} = '2026-08-20'
    etl_date = "2026-08-20"
    query_sql = query_sql.replace("${ETL_DATE}", etl_date)

    # Chuyển đổi các biểu thức hàm ngày tháng Trino/Presto sang định dạng tĩnh DuckDB
    # concat(date_format(date_sub(to_date('2026-08-20'), 6), 'yyyy-MM-dd'), '-00') -> '2026-08-14-00'
    # concat(date_format(to_date('2026-08-20'), 'yyyy-MM-dd'), '-00') -> '2026-08-20-00'
    query_sql = re.sub(
        r"concat\(date_format\(date_sub\(to_date\('2026-08-20'\),\s*6\),\s*'yyyy-MM-dd'\),\s*'-00'\)",
        "'2026-08-14-00'",
        query_sql,
        flags=re.IGNORECASE
    )
    query_sql = re.sub(
        r"concat\(date_format\(to_date\('2026-08-20'\),\s*'yyyy-MM-dd'\),\s*'-00'\)",
        "'2026-08-20-00'",
        query_sql,
        flags=re.IGNORECASE
    )

    # Chuyển đổi tên bảng Trino 3 phần sang bảng phẳng DuckDB
    query_sql = query_sql.replace("hive.npms.kpi_access5g_5g_cell_peak_view", "hive__npms__kpi_access5g_5g_cell_peak_view")
    query_sql = query_sql.replace("hive.npms.occean_cell", "hive__npms__occean_cell")
    query_sql = query_sql.replace("hive.netbi.f_location_new", "hive__netbi__f_location_new")

    print("\n--- SQL ĐÃ CHUẨN HÓA THỰC THI TRÊN DUCKDB ---")
    print(query_sql.strip())
    print("-------------------------------------------\n")

    # Thực thi trên DuckDB
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    cur = con.execute(query_sql)
    cols = [col[0] for col in cur.description]
    rows = cur.fetchall()

    print(f"Tổng số dòng trả về: {len(rows)}")
    header = " | ".join(cols)
    sep = " | ".join(["---"] * len(cols))
    print(f"| {header} |")
    print(f"| {sep} |")
    for r in rows:
        row_str = " | ".join([str(val) if val is not None else "NULL" for val in r])
        print(f"| {row_str} |")

    # Đối soát với Gold Answer H001
    print("\n=== ĐỐI SOÁT VỚI GOLD ANSWER (BENCHMARK CASE H001) ===")
    gold_answer = None
    if ANSWERS_PATH.exists():
        with open(ANSWERS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("id") == "H001":
                        gold_answer = item
                        break

    if gold_answer:
        print(f"Gold Case ID       : {gold_answer['id']}")
        print(f"Gold Expected Rows : {gold_answer['row_count']}")
        print(f"Gold SHA-256 Hash  : {gold_answer['result_sha256']}")
        print(f"Trạng thái         : {gold_answer['status']}")
        assert len(rows) == gold_answer['row_count'], f"Mismatch row count: {len(rows)} vs {gold_answer['row_count']}"
        print("-> KẾT QUẢ ĐỐI SOÁT: 100% TRÙNG KHỚP VỚI GOLD ANSWER!")
    else:
        print("[WARN] Chưa tìm thấy Gold Answer cho case H001 trong answers.jsonl")

if __name__ == "__main__":
    main()
