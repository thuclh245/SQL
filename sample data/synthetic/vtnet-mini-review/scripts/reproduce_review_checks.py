#!/usr/bin/env python3
"""Tái lập các con số trong bộ review VTNet Mini.

Chạy:
    pip install duckdb
    python "sample data/synthetic/vtnet-mini-review/scripts/reproduce_review_checks.py"

Kết quả ghi vào outputs/review_checks.json. Script chỉ đọc vtnet.duckdb ở chế độ
read-only; phép thử H002 chạy trên một DuckDB in-memory riêng.
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

import duckdb

REVIEW_DIR = Path(__file__).resolve().parent.parent
MINI_DIR = REVIEW_DIR.parent / "vtnet-mini"
DB_PATH = MINI_DIR / "generated" / "vtnet.duckdb"
CASES_PATH = MINI_DIR / "benchmark" / "cases.jsonl"
OUTPUT_PATH = REVIEW_DIR / "outputs" / "review_checks.json"

PEAK_VIEW = "hive__npms__kpi_access5g_5g_cell_peak_view"


def load_cases() -> list[dict]:
    with CASES_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check_inventory() -> dict:
    tables = list(csv.DictReader((MINI_DIR / "metadata" / "selected_tables.csv").open(encoding="utf-8")))
    return {
        "total_tables": len(tables),
        "tables_by_domain": dict(Counter(t["domain"] for t in tables)),
        "tables_by_schema": dict(Counter(t["schema"] for t in tables)),
        "executable": dict(Counter(t["is_executable"] for t in tables)),
    }


def check_volume(con: duckdb.DuckDBPyConnection) -> dict:
    counts = json.loads((MINI_DIR / "generated" / "counts.json").read_text(encoding="utf-8"))
    values = sorted(counts.values())
    cells, rows, min_hour, max_hour = con.execute(
        f"SELECT COUNT(DISTINCT object_id), COUNT(*), MIN(date_hour), MAX(date_hour) FROM {PEAK_VIEW}"
    ).fetchone()
    distinct_hours = con.execute(
        f"SELECT COUNT(DISTINCT substr(date_hour, 12, 2)) FROM {PEAK_VIEW}"
    ).fetchone()[0]
    validation = json.loads((MINI_DIR / "generated" / "validation_report.json").read_text(encoding="utf-8"))
    trap_cells = 0
    for result in validation["test_results"].values():
        trap_cells += result.get("expected", result.get("expected_excluded", 0))
    return {
        "total_rows": sum(values),
        "median_rows_per_table": values[len(values) // 2],
        "max_rows_per_table": values[-1],
        "peak_view": {
            "distinct_cells": cells,
            "rows": rows,
            "date_hour_min": min_hour,
            "date_hour_max": max_hour,
            "distinct_hours_of_day": distinct_hours,
        },
        "trap_cells_groups_a_to_h": trap_cells,
        "trap_share_of_peak_view_cells": round(trap_cells / cells, 3),
    }


def check_gold_execution(con: duckdb.DuckDBPyConnection, cases: list[dict]) -> dict:
    errors, empty, row_counts = [], [], Counter()
    for case in cases:
        try:
            rows = con.execute(case["gold_sql_duckdb"]).fetchall()
        except Exception as exc:  # noqa: BLE001 - chỉ để báo cáo
            errors.append({"id": case["id"], "error": str(exc)[:200]})
            continue
        if not rows:
            empty.append(case["id"])
        row_counts["10+" if len(rows) >= 10 else str(len(rows))] += 1
    return {
        "executed": len(cases),
        "errors": errors,
        "empty_results": empty,
        "row_count_distribution": dict(row_counts),
        "expected_outcome_field_present": any("expected_outcome" in c for c in cases),
        "difficulty": dict(Counter(c["difficulty"] for c in cases)),
    }


def check_schema_leakage(cases: list[dict]) -> dict:
    """Đếm câu hỏi chứa định danh bảng/cột xuất hiện trong gold SQL hoặc required_tables."""
    identifier = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
    sql_keywords = re.compile(r"\b(GROUPING SETS|HAVING|NOT EXISTS|LEFT JOIN|CTE|LAG|ROLLUP)\b", re.I)
    leaked, sql_hint = [], []
    for case in cases:
        gold_idents = set(identifier.findall(case["gold_sql_duckdb"]))
        tables = {t.split(".")[-1] for t in case["required_tables"]}
        hits = sorted({w for w in identifier.findall(case["question"]) if w in gold_idents or w in tables})
        if hits:
            leaked.append({"id": case["id"], "identifiers": hits})
        if sql_keywords.search(case["question"]):
            sql_hint.append(case["id"])
    return {
        "questions_with_schema_identifiers": len(leaked),
        "questions_with_sql_syntax_hints": sql_hint,
        "examples": leaked[:15],
    }


def check_h002_fragility(cases: list[dict]) -> dict:
    """Gold H002 dùng LAG theo dòng, không theo ngày lịch. Hai loại dữ liệu làm nó sai:

    - CELL_GAP: ngày xấu 14, 15, 17; ngày 16 traffic = 0 nên bị WHERE lọc mất.
      Theo ngày lịch không có chuỗi 3 ngày liên tiếp, đáp án đúng là rỗng.
    - CELL_2H: ngày 14 có 2 khung giờ xấu, ngày 15 xấu, tức chỉ 2 ngày.
      LAG coi 3 dòng là 3 "ngày" nên đếm nhầm.

    Bản đúng gộp theo ngày trước (ngày xấu = mọi khung giờ < 4 Mbps và tổng traffic > 0),
    rồi tìm chuỗi ngày lịch liên tiếp. Định nghĩa "ngày xấu" khi có nhiều khung giờ là
    điểm mơ hồ của câu hỏi, cần DE chốt.
    """
    gold_sql = next(c for c in cases if c["id"] == "H002")["gold_sql_duckdb"]
    mem = duckdb.connect()
    mem.execute(
        f"CREATE TABLE {PEAK_VIEW} (object_id VARCHAR, date VARCHAR, "
        "dl_user_throughput_mbps VARCHAR, nr_ps_traffic_total_gb VARCHAR)"
    )
    mem.executemany(
        f"INSERT INTO {PEAK_VIEW} VALUES (?, ?, ?, ?)",
        [
            ("CELL_GAP", "2026-08-14", "2.0", "5.0"),
            ("CELL_GAP", "2026-08-15", "2.0", "5.0"),
            ("CELL_GAP", "2026-08-16", "2.0", "0.0"),
            ("CELL_GAP", "2026-08-17", "2.0", "5.0"),
            ("CELL_GAP", "2026-08-18", "9.0", "5.0"),
            ("CELL_2H", "2026-08-14", "2.0", "5.0"),
            ("CELL_2H", "2026-08-14", "3.0", "5.0"),
            ("CELL_2H", "2026-08-15", "2.0", "5.0"),
            ("CELL_2H", "2026-08-16", "9.0", "5.0"),
        ],
    )
    calendar_sql = f"""
        WITH d AS (
            SELECT object_id, CAST(date AS DATE) AS dt,
                   MAX(CAST(dl_user_throughput_mbps AS DOUBLE)) AS tp,
                   SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)) AS tr
            FROM {PEAK_VIEW}
            WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
            GROUP BY object_id, CAST(date AS DATE)
        ),
        bad AS (SELECT object_id, dt FROM d WHERE tp < 4.0 AND tr > 0),
        runs AS (
            SELECT object_id, dt - CAST(ROW_NUMBER() OVER (PARTITION BY object_id ORDER BY dt) AS INTEGER) AS grp
            FROM bad
        )
        SELECT DISTINCT object_id FROM runs GROUP BY object_id, grp HAVING COUNT(*) >= 3
    """
    gold_rows = [r[0] for r in mem.execute(gold_sql).fetchall()]
    calendar_rows = [r[0] for r in mem.execute(calendar_sql).fetchall()]

    real = duckdb.connect(str(DB_PATH), read_only=True)
    real_gold = {r[0] for r in real.execute(gold_sql).fetchall()}
    real_calendar = {r[0] for r in real.execute(calendar_sql).fetchall()}
    return {
        "synthetic_gap_case": {"gold_returns": gold_rows, "calendar_correct_returns": calendar_rows},
        "on_current_vtnet_data": {
            "gold_count": len(real_gold),
            "calendar_count": len(real_calendar),
            "identical": real_gold == real_calendar,
        },
    }


def check_h012_alignment(con: duckdb.DuckDBPyConnection, cases: list[dict]) -> dict:
    case = next(c for c in cases if c["id"] == "H012")
    rows = con.execute(case["gold_sql_duckdb"]).fetchall()
    od_columns = [
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'hive__gnoc__od_history'"
        ).fetchall()
    ]
    return {
        "question": case["question"],
        "distinct_od_action_values_across_departments": sorted({r[-1] for r in rows}),
        "departments": len(rows),
        "od_history_columns": od_columns,
    }


def check_peak_view_grain(con: duckdb.DuckDBPyConnection) -> dict:
    """Query production (sample data/query.md) đếm COUNT(*) AS no_bad_day, tức giả định
    peak_view có 1 dòng / cell / ngày. Kiểm tra dữ liệu synthetic có giữ grain đó không,
    và generator có chèn dữ liệu riêng cho từng case không."""
    dup_keys, dup_cells, differing = con.execute(
        f"""
        SELECT COUNT(*), COUNT(DISTINCT object_id),
               SUM(CASE WHEN n_vals > 1 THEN 1 ELSE 0 END)
        FROM (
            SELECT object_id, date_hour,
                   COUNT(DISTINCT dl_user_throughput_mbps || '|' || nr_ps_traffic_total_gb) AS n_vals
            FROM {PEAK_VIEW}
            GROUP BY object_id, date_hour
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()
    generator = (MINI_DIR / "scripts" / "generate_synthetic_data.py").read_text(encoding="utf-8").splitlines()
    case_specific = [
        {"line": i + 1, "text": line.strip()}
        for i, line in enumerate(generator)
        if re.search(r"\bfor [HME]\d{3}\b|carrier aggregation", line)
    ]
    return {
        "duplicate_object_id_date_hour_keys": dup_keys,
        "cells_with_duplicates": dup_cells,
        "duplicates_with_differing_values": differing,
        "generator_case_specific_injections": case_specific,
    }


def check_metadata_descriptions() -> dict:
    rows = list(csv.DictReader((MINI_DIR / "metadata" / "selected_columns.csv").open(encoding="utf-8")))

    def source(desc: str) -> str:
        desc = desc.strip()
        if not desc:
            return "empty"
        return "ai_gen" if desc.startswith("[AI Gen]") else "other"

    object_id = next(
        (r["description"] for r in rows if r["table_name"] == "kpi_access5g_5g_cell_peak_view" and r["column_name"] == "object_id"),
        None,
    )
    return {
        "total_columns": len(rows),
        "description_source": dict(Counter(source(r["description"]) for r in rows)),
        "data_type": dict(Counter(r["data_type"] for r in rows).most_common(6)),
        "example_peak_view_object_id_description": object_id,
    }


def main() -> None:
    cases = load_cases()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    report = {
        "inventory": check_inventory(),
        "volume": check_volume(con),
        "gold_execution": check_gold_execution(con, cases),
        "schema_leakage": check_schema_leakage(cases),
        "h002_fragility": check_h002_fragility(cases),
        "h012_alignment": check_h012_alignment(con, cases),
        "peak_view_grain": check_peak_view_grain(con),
        "metadata_descriptions": check_metadata_descriptions(),
    }
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
