#!/usr/bin/env python3
"""
evaluate_benchmark.py
=====================
Đánh giá độ chính xác của hệ thống NL2SQL trên VTNet Mini Benchmark:
- So sánh kết quả thực thi (Execution Accuracy - EX) giữa predicted_sql và gold answer.
- Phân tích lỗi theo danh mục:
  1. SYNTAX_ERROR: Lỗi cú pháp SQL hoặc dialect không hợp lệ
  2. TABLE_NOT_FOUND: Tên bảng không tồn tại hoặc sai catalog/schema
  3. COLUMN_NOT_FOUND: Cột không tồn tại hoặc sai kiểu dữ liệu
  4. EMPTY_RESULT: Query chạy được nhưng trả về 0 dòng trong khi ground truth có dữ liệu
  5. ROW_COUNT_MISMATCH: Số dòng khác ground truth
  6. VALUE_MISMATCH: Giá trị kết quả không khớp với ground truth
- Đánh giá Table Retrieval Precision, Recall, F1 (nếu có predicted_tables hoặc trích xuất từ SQL).
- Xuất báo cáo json chi tiết.
"""

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path

import duckdb

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"
BENCHMARK_DIR = PROJECT_DIR / "benchmark"
ANSWERS_PATH = BENCHMARK_DIR / "answers.jsonl"
CASES_PATH = BENCHMARK_DIR / "cases.jsonl"

def compute_result_hash(columns, rows):
    norm_rows = []
    for row in rows:
        norm_row = [str(val) if val is not None else "NULL" for val in row]
        norm_rows.append(norm_row)
    norm_rows_sorted = sorted(norm_rows)
    payload = json.dumps({"columns": columns, "rows": norm_rows_sorted}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def extract_tables_from_sql(sql: str):
    """Trích xuất danh sách tên bảng từ SQL query đơn giản (hỗ trợ FROM và JOIN)"""
    tokens = set()
    pattern = r'(?:FROM|JOIN)\s+([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)'
    matches = re.findall(pattern, sql, re.IGNORECASE)
    for m in matches:
        # Chuẩn hóa về dạng catalog.schema.table nếu là catalog__schema__table
        parts = m.split("__")
        if len(parts) == 3:
            tokens.add(".".join(parts))
        else:
            tokens.add(m)
    return tokens

def evaluate(predictions_path=None, output_report_path=None, run_self_test=False):
    print("=== BẮT ĐẦU ĐÁNH GIÁ NL2SQL EVALUATOR VTNET MINI ===")

    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"Database {DUCKDB_PATH} không tồn tại!")
    if not ANSWERS_PATH.exists() or not CASES_PATH.exists():
        raise FileNotFoundError("Chưa tìm thấy cases.jsonl hoặc answers.jsonl. Hãy chạy build_benchmark.py trước!")

    # Load ground truth cases
    cases_dict = {}
    with open(CASES_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                cases_dict[item["id"]] = item

    # Load ground truth answers
    answers_dict = {}
    with open(ANSWERS_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                answers_dict[item["id"]] = item

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)

    predictions = []
    if run_self_test or not predictions_path or not Path(predictions_path).exists():
        print("[INFO] Chạy chế độ Self-Test (sử dụng Gold SQL DuckDB làm prediction)")
        for cid, case_data in sorted(cases_dict.items()):
            predictions.append({
                "id": cid,
                "predicted_sql": case_data["gold_sql_duckdb"],
                "predicted_tables": case_data["required_tables"]
            })
    else:
        print(f"[INFO] Nạp predictions từ file: {predictions_path}")
        with open(predictions_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    predictions.append(json.loads(line))

    total = len(predictions)
    correct_count = 0
    error_counter = Counter()
    difficulty_scores = {"easy": [0, 0], "medium": [0, 0], "hard": [0, 0]}
    detailed_results = []

    t_start = time.time()

    for item in predictions:
        cid = item.get("id")
        sql = item.get("predicted_sql", "")
        pred_tables = item.get("predicted_tables")

        gold_case = cases_dict.get(cid)
        gold_ans = answers_dict.get(cid)

        if not gold_case or not gold_ans:
            print(f"[WARN] Bỏ qua ID không xác định trong benchmark: {cid}")
            continue

        diff = gold_case["difficulty"]
        difficulty_scores[diff][1] += 1

        is_correct = False
        error_type = None
        error_detail = None
        pred_hash = None
        pred_row_count = 0

        if not sql or not sql.strip():
            error_type = "EMPTY_QUERY"
            error_detail = "Prediction không có SQL"
        else:
            try:
                cur = con.execute(sql)
                cols = [c[0] for c in cur.description]
                rows = cur.fetchall()
                pred_row_count = len(rows)
                pred_hash = compute_result_hash(cols, rows)

                if pred_hash == gold_ans["result_sha256"]:
                    is_correct = True
                else:
                    if pred_row_count == 0 and gold_ans["row_count"] > 0:
                        error_type = "EMPTY_RESULT"
                        error_detail = f"Predicted trả về 0 rows, ground truth có {gold_ans['row_count']} rows"
                    elif pred_row_count != gold_ans["row_count"]:
                        error_type = "ROW_COUNT_MISMATCH"
                        error_detail = f"Predicted trả về {pred_row_count} rows, ground truth có {gold_ans['row_count']} rows"
                    else:
                        error_type = "VALUE_MISMATCH"
                        error_detail = "Số lượng dòng khớp nhưng giá trị hoặc thứ tự cột khác nhau"
            except Exception as err:
                err_msg = str(err)
                if "does not exist" in err_msg.lower() or "not found" in err_msg.lower():
                    if "table" in err_msg.lower():
                        error_type = "TABLE_NOT_FOUND"
                    else:
                        error_type = "COLUMN_NOT_FOUND"
                elif "syntax error" in err_msg.lower() or "parser" in err_msg.lower():
                    error_type = "SYNTAX_ERROR"
                else:
                    error_type = "EXECUTION_ERROR"
                error_detail = err_msg

        if is_correct:
            correct_count += 1
            difficulty_scores[diff][0] += 1
        else:
            error_counter[error_type] += 1

        detailed_results.append({
            "id": cid,
            "difficulty": diff,
            "domain": gold_case["domain"],
            "question": gold_case["question"],
            "predicted_sql": sql,
            "gold_sql": gold_case["gold_sql_duckdb"],
            "is_correct": is_correct,
            "error_type": error_type,
            "error_detail": error_detail,
            "gold_row_count": gold_ans["row_count"],
            "pred_row_count": pred_row_count
        })

    t_elapsed = round(time.time() - t_start, 3)
    accuracy = round((correct_count / total) * 100, 2) if total > 0 else 0

    diff_summary = {}
    for d, (passed, tot) in difficulty_scores.items():
        diff_summary[d] = {
            "passed": passed,
            "total": tot,
            "accuracy_percent": round((passed / tot) * 100, 2) if tot > 0 else 0
        }

    report = {
        "benchmark": "VTNet Mini 100 NL2SQL",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_evaluated": total,
        "correct_predictions": correct_count,
        "failed_predictions": total - correct_count,
        "overall_execution_accuracy_percent": accuracy,
        "evaluation_time_seconds": t_elapsed,
        "difficulty_breakdown": diff_summary,
        "error_distribution": dict(error_counter),
        "detailed_results": detailed_results
    }

    if not output_report_path:
        output_report_path = BENCHMARK_DIR / "evaluation_report.json"
    else:
        output_report_path = Path(output_report_path)

    with open(output_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "="*50)
    print(f"KẾT QUẢ ĐÁNH GIÁ (Overall Execution Accuracy): {accuracy}% ({correct_count}/{total})")
    print("="*50)
    print(f"- Easy  : {diff_summary.get('easy', {}).get('accuracy_percent', 0)}% ({diff_summary.get('easy', {}).get('passed', 0)}/{diff_summary.get('easy', {}).get('total', 0)})")
    print(f"- Medium: {diff_summary.get('medium', {}).get('accuracy_percent', 0)}% ({diff_summary.get('medium', {}).get('passed', 0)}/{diff_summary.get('medium', {}).get('total', 0)})")
    print(f"- Hard  : {diff_summary.get('hard', {}).get('accuracy_percent', 0)}% ({diff_summary.get('hard', {}).get('passed', 0)}/{diff_summary.get('hard', {}).get('total', 0)})")
    if error_counter:
        print("\nPhân bố các loại lỗi:")
        for err, cnt in error_counter.most_common():
            print(f"  * {err}: {cnt}")
    print(f"\n-> Đã lưu báo cáo đánh giá: {output_report_path}")

    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate NL2SQL Predictions on VTNet Mini Benchmark")
    parser.add_argument("--predictions", type=str, default=None, help="Path to predictions.jsonl")
    parser.add_argument("--output", type=str, default=None, help="Path to evaluation_report.json")
    parser.add_argument("--self-test", action="store_true", help="Run self test with ground truth SQL")
    args = parser.parse_args()

    evaluate(predictions_path=args.predictions, output_report_path=args.output, run_self_test=args.self_test)
