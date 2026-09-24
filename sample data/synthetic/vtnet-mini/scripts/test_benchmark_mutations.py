#!/usr/bin/env python3
"""
test_benchmark_mutations.py
===========================
Công cụ tự động hóa kiểm thử đột biến (Mutation Testing) cho 100 Benchmark Cases:
1. Nạp danh sách 100 cases từ benchmark/cases.py.
2. Chạy Gold SQL DuckDB trên generated/vtnet.duckdb để lấy baseline hash.
3. Sinh các biến thể đột biến (mutations) phổ biến:
   - DROP_WHERE: Loại bỏ điều kiện lọc WHERE
   - SWAP_JOIN: Đổi INNER JOIN -> LEFT JOIN hoặc LEFT JOIN -> INNER JOIN
   - DROP_DISTINCT: Loại bỏ DISTINCT trong SELECT hoặc COUNT(DISTINCT)
   - DROP_HAVING: Loại bỏ mệnh đề HAVING
   - FLIP_NOT_EXISTS: Đổi NOT EXISTS thành EXISTS
4. Kiểm tra xem mutation có bị "KILL" (kết quả khác baseline hoặc lỗi cú pháp)
   hay "SURVIVE" (trả về kết quả y hệt baseline - Lucky Match).
5. Tính Mutation Kill Rate tổng thể và theo từng danh mục.
"""

import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import duckdb

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.append(str(PROJECT_DIR))

from benchmark.cases import get_benchmark_cases

DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"
REPORTS_DIR = PROJECT_DIR / "reports"


def compute_result_hash(rows):
    norm_rows = []
    for row in rows:
        norm_row = [str(val) if val is not None else "NULL" for val in row]
        norm_rows.append(norm_row)
    norm_rows_sorted = sorted(norm_rows)
    payload = json.dumps(norm_rows_sorted, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mutate_drop_where(sql):
    """Thay thế các mệnh đề WHERE bằng WHERE 1=1 để loại bỏ điều kiện lọc một cách an toàn."""
    match = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
    if not match:
        return None
    start_idx = match.start()
    idx = match.end()
    depth = 0
    n = len(sql)
    end_idx = n
    while idx < n:
        ch = sql[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth > 0:
                depth -= 1
            else:
                end_idx = idx
                break
        elif depth == 0:
            rest = sql[idx:].upper()
            matched_kw = False
            for kw in ["GROUP BY", "ORDER BY", "HAVING", "LIMIT", "UNION", "WINDOW", ";"]:
                if rest.startswith(kw) and (len(rest) == len(kw) or not rest[len(kw)].isalnum()):
                    end_idx = idx
                    matched_kw = True
                    break
            if matched_kw:
                break
        idx += 1
    return sql[:start_idx] + "WHERE 1=1 " + sql[end_idx:]


def mutate_swap_join(sql):
    """Hoán đổi INNER JOIN <-> LEFT JOIN."""
    if re.search(r"\bINNER\s+JOIN\b", sql, re.IGNORECASE):
        return re.sub(r"\bINNER\s+JOIN\b", "LEFT JOIN", sql, flags=re.IGNORECASE)
    elif re.search(r"\bLEFT\s+JOIN\b", sql, re.IGNORECASE):
        return re.sub(r"\bLEFT\s+JOIN\b", "INNER JOIN", sql, flags=re.IGNORECASE)
    elif re.search(r"\bJOIN\b", sql, re.IGNORECASE) and not re.search(
        r"\bCROSS\s+JOIN\b|\bFULL\s+OUTER\s+JOIN\b", sql, re.IGNORECASE
    ):
        return re.sub(r"\bJOIN\b", "LEFT JOIN", sql, count=1, flags=re.IGNORECASE)
    return None


def mutate_drop_distinct(sql):
    """Loại bỏ COUNT(DISTINCT ...) -> COUNT(...) hoặc SELECT DISTINCT -> SELECT."""
    if "COUNT(DISTINCT " in sql.upper():
        return re.sub(
            r"COUNT\s*\(\s*DISTINCT\s+", "COUNT(", sql, flags=re.IGNORECASE
        )
    if "SELECT DISTINCT " in sql.upper():
        return re.sub(
            r"SELECT\s+DISTINCT\s+", "SELECT ", sql, count=1, flags=re.IGNORECASE
        )
    return None


def mutate_drop_having(sql):
    """Loại bỏ mệnh đề HAVING."""
    pattern = re.compile(
        r"\bHAVING\b\s+.*?(?=\bORDER\s+BY\b|\bLIMIT\b|\bUNION\b|\)|\;|$)",
        re.IGNORECASE | re.DOTALL,
    )
    if pattern.search(sql):
        return pattern.sub("", sql)
    return None


def mutate_flip_not_exists(sql):
    """Đổi NOT EXISTS thành EXISTS hoặc ngược lại."""
    if re.search(r"\bNOT\s+EXISTS\b", sql, re.IGNORECASE):
        return re.sub(
            r"\bNOT\s+EXISTS\b", "EXISTS", sql, count=1, flags=re.IGNORECASE
        )
    if re.search(r"\bEXISTS\b", sql, re.IGNORECASE):
        return re.sub(
            r"\bEXISTS\b", "NOT EXISTS", sql, count=1, flags=re.IGNORECASE
        )
    return None


def run_mutation_tests():
    print("=== BẮT ĐẦU CHẠY BENCHMARK MUTATION TESTING VTNET MINI ===")
    print(f"Database: {DUCKDB_PATH}")

    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"Database {DUCKDB_PATH} không tồn tại!")

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    cases = get_benchmark_cases()
    print(f"Tổng số test cases: {len(cases)}")

    mutators = {
        "DROP_WHERE": mutate_drop_where,
        "SWAP_JOIN": mutate_swap_join,
        "DROP_DISTINCT": mutate_drop_distinct,
        "DROP_HAVING": mutate_drop_having,
        "FLIP_NOT_EXISTS": mutate_flip_not_exists,
    }

    results = []
    stats_by_type = defaultdict(lambda: {"tested": 0, "killed": 0, "survived": 0})
    case_vulnerabilities = defaultdict(list)

    total_mutations_tested = 0
    total_mutations_killed = 0

    t_start = time.time()

    for c in cases:
        cid = c["id"]
        sql_gold = c["gold_sql_duckdb"]
        diff = c["difficulty"]

        # 1. Chạy Gold SQL
        try:
            gold_rows = con.execute(sql_gold).fetchall()
            gold_hash = compute_result_hash(gold_rows)
            gold_count = len(gold_rows)
        except Exception as err:
            print(f"[ERROR] Gold SQL lỗi ở {cid}: {err}")
            continue

        # 2. Thử từng mutation
        for m_name, m_func in mutators.items():
            mutated_sql = m_func(sql_gold)
            if not mutated_sql or mutated_sql.strip() == sql_gold.strip():
                continue

            stats_by_type[m_name]["tested"] += 1
            total_mutations_tested += 1

            try:
                mut_rows = con.execute(mutated_sql).fetchall()
                mut_hash = compute_result_hash(mut_rows)
                mut_count = len(mut_rows)

                # Nếu hash khác hoặc số dòng khác -> KILLED (thành công bắt lỗi)
                if mut_hash != gold_hash or mut_count != gold_count:
                    status = "KILLED"
                    stats_by_type[m_name]["killed"] += 1
                    total_mutations_killed += 1
                else:
                    # SURVIVED -> Lucky match!
                    status = "SURVIVED"
                    stats_by_type[m_name]["survived"] += 1
                    case_vulnerabilities[cid].append(m_name)
            except Exception:
                # Query đột biến bị lỗi cú pháp / execution error -> cũng coi như KILLED
                status = "KILLED"
                stats_by_type[m_name]["killed"] += 1
                total_mutations_killed += 1

            results.append({
                "case_id": cid,
                "difficulty": diff,
                "mutation": m_name,
                "status": status,
            })

    t_elapsed = round(time.time() - t_start, 2)
    overall_kill_rate = (
        round((total_mutations_killed / total_mutations_tested) * 100, 2)
        if total_mutations_tested > 0
        else 0.0
    )

    print("\n=== KẾT QUẢ MUTATION TESTING ===")
    print(f"Tổng số mutations đã thử: {total_mutations_tested}")
    print(f"Số mutations bị KILLED: {total_mutations_killed} ({overall_kill_rate}%)")
    print(f"Số mutations SURVIVED: {total_mutations_tested - total_mutations_killed}")
    print(f"Thời gian chạy: {t_elapsed}s\n")

    print("| Loại Mutation | Đã test | Bắt lỗi (KILLED) | Sống sót (SURVIVED) | Kill Rate |")
    print("|---|---:|---:|---:|---:|")
    for m_name, st in sorted(stats_by_type.items()):
        rate = round((st["killed"] / st["tested"]) * 100, 1) if st["tested"] > 0 else 0.0
        print(f"| {m_name} | {st['tested']} | {st['killed']} | {st['survived']} | {rate}% |")

    if case_vulnerabilities:
        print("\n[CẢNH BÁO] Các case có mutation SURVIVED (cần bổ sung dữ liệu bẫy):")
        for cid, muts in sorted(case_vulnerabilities.items()):
            print(f"  - {cid}: {', '.join(muts)}")
    else:
        print("\n[XUẤT SẮC] 100% mutations đã bị KILLED! Không có trường hợp lucky match nào.")

    # Lưu báo cáo JSON
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / "mutation_test_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_tested": total_mutations_tested,
                "total_killed": total_mutations_killed,
                "kill_rate_percent": overall_kill_rate,
                "by_mutation": dict(stats_by_type),
                "vulnerabilities": dict(case_vulnerabilities),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n-> Báo cáo chi tiết đã lưu tại {report_file}")
    return overall_kill_rate, dict(case_vulnerabilities)


if __name__ == "__main__":
    run_mutation_tests()
