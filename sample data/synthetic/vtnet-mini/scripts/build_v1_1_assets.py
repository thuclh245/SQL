#!/usr/bin/env python3
"""Build VTNet Mini V1.1 benchmark_v2 and metadata variants M0-M3.

Never overwrites the V1 benchmark.  Every generated field states where it came
from; nothing is promoted to `de_reviewed` (only a human DE may do that).

Inputs
  benchmark/cases.jsonl                 V1 cases (gold SQL, required tables)
  benchmark_v2/natural_questions.json   hand-written business-language questions
  conventions/conventions.yaml          accepted conventions (AST-checked)
  metadata/catalog.json                 OM-derived catalog (descriptions from OM Excel)
  metadata/variants/M2/profile_report.json  run scripts/profile_vtnet_metadata.py first

Outputs
  benchmark_v2/cases.jsonl, benchmark_v2/README.md
  metadata/variants/{M0,M1,M2}/catalog.json, metadata/variants/M3/NOT_BUILT.md
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convention_checks import applies, is_executable, load_registry, run_check  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "generated" / "vtnet.duckdb"
V1_CASES = ROOT / "benchmark" / "cases.jsonl"
OUTPUT = ROOT / "benchmark_v2"
NATURAL = OUTPUT / "natural_questions.json"
CATALOG = ROOT / "metadata" / "catalog.json"
VARIANTS = ROOT / "metadata" / "variants"
PROFILE = VARIANTS / "M2" / "profile_report.json"

DM = "mysql_datamon__data_monitoring__"
PEAK = "hive__npms__kpi_access5g_5g_cell_peak_view"

# ------------------------------------------------------------------ gold fixes

GOLD_FIXES = {
    "H002": {
        "reason": "V1 dùng LAG theo dòng: đếm nhầm ngày trống/ nhiều dòng một ngày là liên tiếp (review 02 §2). "
                  "Định nghĩa 'ngày xấu' = có ít nhất một dòng < 4 Mbps (MIN) là lựa chọn tạm, chờ DE chốt.",
        "duckdb": f"""WITH daily AS (
  SELECT object_id, CAST(date AS DATE) AS day
  FROM {PEAK}
  WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
  GROUP BY object_id, CAST(date AS DATE)
  HAVING MIN(CAST(dl_user_throughput_mbps AS DOUBLE)) < 4
     AND SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)) > 0
), streaks AS (
  SELECT object_id, day - CAST(ROW_NUMBER() OVER (PARTITION BY object_id ORDER BY day) AS INTEGER) AS streak_key
  FROM daily
)
SELECT DISTINCT object_id FROM streaks GROUP BY object_id, streak_key HAVING COUNT(*) >= 3 ORDER BY object_id;""",
        "trino": """WITH daily AS (
  SELECT object_id, CAST(date AS DATE) AS day
  FROM hive.npms.kpi_access5g_5g_cell_peak_view
  WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
  GROUP BY object_id, CAST(date AS DATE)
  HAVING MIN(CAST(dl_user_throughput_mbps AS DOUBLE)) < 4
     AND SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)) > 0
), streaks AS (
  SELECT object_id, date_add('day', -CAST(ROW_NUMBER() OVER (PARTITION BY object_id ORDER BY day) AS INTEGER), day) AS streak_key
  FROM daily
)
SELECT DISTINCT object_id FROM streaks GROUP BY object_id, streak_key HAVING COUNT(*) >= 3 ORDER BY object_id;""",
    },
    "H027": {
        "reason": "V1 dùng NTILE(4) OVER (ORDER BY avg_tp): các cell cùng avg_tp bị chia nhóm không xác định, hash V1 không tái lập được. Thêm object_id làm tiêu chí phụ.",
        "sub": ("NTILE(4) OVER (ORDER BY avg_tp ASC)", "NTILE(4) OVER (ORDER BY avg_tp ASC, object_id ASC)"),
    },
    "H012": {
        "reason": "V1 CROSS JOIN tổng od_history cho mọi phòng ban. Sửa: gom theo unit_id. Nhưng unit_id toàn 'sample_unit_id' nên case bị chặn bởi dữ liệu.",
        "duckdb": """WITH alarm_agg AS (
  SELECT region, COUNT(*) AS alarm_count FROM hive__gnoc__gnoc GROUP BY region
), od_agg AS (
  SELECT unit_id, COUNT(*) AS od_action_count FROM hive__gnoc__od_history GROUP BY unit_id
)
SELECT d.dept_code, d.dept_name, COALESCE(a.alarm_count, 0) AS alarm_count, COALESCE(o.od_action_count, 0) AS od_action_count
FROM hive__gnoc__cat_department d
LEFT JOIN alarm_agg a ON d.location_id = a.region
LEFT JOIN od_agg o ON CAST(d.department_id AS VARCHAR) = CAST(o.unit_id AS VARCHAR)
WHERE d.dept_code != '' ORDER BY d.dept_code;""",
    },
}

BLOCKED_BY_DATA = {
    "H012": "hive.gnoc.od_history.unit_id chỉ có giá trị placeholder 'sample_unit_id'; không thể gán lượt điều chỉnh cho phòng ban. "
            "Câu hỏi hợp lệ về nghiệp vụ nên KHÔNG gắn unanswerable; loại khỏi chấm điểm tới khi sửa generator (Phase 1).",
}

# ------------------------------------------------------------------ review flags (found while rewriting questions)

REVIEW_FLAGS = {
    "question_gold_mismatch": {
        "E013": "Câu hỏi: mọi vendor không rỗng; gold cố định IN ('Huawei','Ericsson').",
        "E018": "Câu hỏi: 5 IP 'đầu tiên được ghi nhận' (theo thời gian); gold xếp theo chữ cái.",
        "M002": "Câu hỏi: lưu lượng 'tải xuống'; gold dùng tổng lưu lượng nr_ps_traffic_total_gb.",
        "M013": "Câu hỏi: tỉnh có lưu lượng > 3 tỷ bit; gold đếm số bản ghi cell > 3 tỷ bit theo tỉnh.",
        "H029": "Mẫu số 'cell hoạt động' tính trên toàn bộ dữ liệu, không giới hạn trong tuần.",
    },
    "hidden_condition_in_gold": {
        "H003": "Gold lọc thêm trung bình giai đoạn sau >= 15 Mbps.",
        "H006": "Gold lọc thêm trung bình 7 ngày >= 10 Mbps.",
        "H020": "Gold LIMIT 10.",
        "H025": "Gold chỉ lấy cell có mã 'CELL_5G_A%'.",
        "H028": "Gold chỉ lấy tỉnh HNI và HCM.",
    },
    "duplicate_question": {
        "E015": "Trùng ngữ nghĩa với E010.",
        "E019": "Trùng ngữ nghĩa với E003.",
    },
    "heuristic_join": {
        "H012": "cat_department.location_id = gnoc.region.",
        "H015": "enodeb_id so với 4 ký tự cuối station_code.",
        "H022": "enodeb_id so với 4 ký tự cuối station_code.",
        "H045": "station_code LIKE '%' || province_code || '%'.",
        "H047": "icms_maintain_calendar.area_code = gnoc.region.",
    },
    "grain_duplicate_rows_risk": {
        cid: "COUNT(*) số ngày trên peak_view, trong khi dữ liệu có 50 khóa (object_id, date_hour) trùng (review 02 §8)."
        for cid in ("H001", "H017", "H029", "H035", "H045")
    },
    "nondeterministic_fixed": {"H027": GOLD_FIXES["H027"]["reason"]},
    "pending_de_definition": {"H002": "CONV_BAD_DAY_DEFINITION chưa chốt."},
}

# ------------------------------------------------------------------ new answerable Data Monitoring cases

KQI = f"{DM}kqi_monitor_web"
KQI_T = "mysql_datamon.data_monitoring.kqi_monitor_web"
BL = f"{DM}usersinarea_blacklist_enodeb_id"
BL_T = "mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id"

NEW_DM_CASES = [
    ("E021", "easy", "Đếm số chỉ số KQI (cột name) khác nhau trong bảng kqi_monitor_web.",
     "Hệ thống đang giám sát bao nhiêu chỉ số KQI độ trễ web khác nhau?",
     f"SELECT COUNT(DISTINCT name) AS kqi_count FROM {KQI};",
     f"SELECT COUNT(DISTINCT name) AS kqi_count FROM {KQI_T};", [KQI_T], ["count_distinct"]),
    ("M031", "medium", "Tính trung bình value của từng chỉ số KQI trong kqi_monitor_web, loại các giá trị âm không hợp lệ.",
     "Độ trễ trung bình của từng chỉ số KQI web là bao nhiêu, không tính các mẫu đo không hợp lệ?",
     f"SELECT name, ROUND(AVG(value), 2) AS avg_value FROM {KQI} WHERE value >= 0 GROUP BY name ORDER BY name;",
     f"SELECT name, ROUND(AVG(value), 2) AS avg_value FROM {KQI_T} WHERE value >= 0 GROUP BY name ORDER BY name;",
     [KQI_T], ["aggregation", "data_quality", "sentinel_value"]),
    ("M032", "medium", "Đếm số mẫu có value âm và tổng số mẫu của từng chỉ số KQI trong kqi_monitor_web.",
     "Mỗi chỉ số KQI web có bao nhiêu mẫu đo không hợp lệ trên tổng số mẫu đo?",
     f"SELECT name, SUM(CASE WHEN value < 0 THEN 1 ELSE 0 END) AS invalid_samples, COUNT(*) AS total_samples FROM {KQI} GROUP BY name ORDER BY name;",
     f"SELECT name, SUM(CASE WHEN value < 0 THEN 1 ELSE 0 END) AS invalid_samples, COUNT(*) AS total_samples FROM {KQI_T} GROUP BY name ORDER BY name;",
     [KQI_T], ["conditional_aggregation", "data_quality", "sentinel_value"]),
    ("M033", "medium", "Tìm các enodeb_id trong usersinarea_blacklist_enodeb_id thuộc nhiều hơn một zone_id khác nhau.",
     "Những trạm eNodeB nào trong danh sách đen bị chặn ở nhiều hơn một vùng?",
     f"SELECT enodeb_id, COUNT(DISTINCT zone_id) AS zone_count FROM {BL} GROUP BY enodeb_id HAVING COUNT(DISTINCT zone_id) > 1 ORDER BY enodeb_id;",
     f"SELECT enodeb_id, COUNT(DISTINCT zone_id) AS zone_count FROM {BL_T} GROUP BY enodeb_id HAVING COUNT(DISTINCT zone_id) > 1 ORDER BY enodeb_id;",
     [BL_T], ["count_distinct", "having", "duplicate_rows"]),
    ("H051", "hard", "Lấy value tại ts lớn nhất (ts là epoch giây) của từng chỉ số KQI trong kqi_monitor_web.",
     "Lần đo gần nhất của từng chỉ số KQI web cho giá trị bao nhiêu?",
     f"SELECT name, ARG_MAX(value, ts) AS latest_value FROM {KQI} GROUP BY name ORDER BY name;",
     f"SELECT name, max_by(value, ts) AS latest_value FROM {KQI_T} GROUP BY name ORDER BY name;",
     [KQI_T], ["latest_per_group", "epoch_time"]),
    ("H052", "hard", "Liệt kê các chỉ số KQI mà value tại ts lớn nhất của chính chỉ số đó là số âm (không hợp lệ) trong kqi_monitor_web.",
     "Xét lần đo gần nhất của từng chỉ số KQI web, những chỉ số nào đang báo giá trị không hợp lệ?",
     f"SELECT name FROM (SELECT name, ARG_MAX(value, ts) AS latest_value FROM {KQI} GROUP BY name) WHERE latest_value < 0 ORDER BY name;",
     f"SELECT name FROM (SELECT name, max_by(value, ts) AS latest_value FROM {KQI_T} GROUP BY name) WHERE latest_value < 0 ORDER BY name;",
     [KQI_T], ["latest_per_group", "sentinel_value", "subquery"]),
    ("H053", "hard", "Với mỗi chỉ số KQI trong kqi_monitor_web, tính chênh lệch value giữa mẫu hợp lệ (value >= 0) có ts lớn nhất và nhỏ nhất.",
     "Với mỗi chỉ số KQI web, độ trễ thay đổi bao nhiêu giữa lần đo hợp lệ đầu tiên và lần đo hợp lệ cuối cùng?",
     f"SELECT name, ARG_MIN(value, ts) AS first_valid, ARG_MAX(value, ts) AS last_valid, ARG_MAX(value, ts) - ARG_MIN(value, ts) AS change FROM {KQI} WHERE value >= 0 GROUP BY name ORDER BY name;",
     f"SELECT name, min_by(value, ts) AS first_valid, max_by(value, ts) AS last_valid, max_by(value, ts) - min_by(value, ts) AS change FROM {KQI_T} WHERE value >= 0 GROUP BY name ORDER BY name;",
     [KQI_T], ["latest_per_group", "sentinel_value", "temporal_comparison"]),
]

# ------------------------------------------------------------------ non-answer cases

UNANSWERABLE = [
    # id, domain, difficulty, question, reason, trap_groups, review_note
    ("U001", "fbb", "medium", "Chỉ số NPS (mức độ sẵn sàng giới thiệu dịch vụ) của khách hàng cáp quang theo tỉnh tháng 8/2026 là bao nhiêu?",
     "Không có dữ liệu khảo sát khách hàng. Các cột nps_* trong kpi_access5g_5g_cell_peak_view là counter mạng 5G, không phải Net Promoter Score.",
     ["near_synonym_column"], None),
    ("U002", "network_kpi_5g", "easy", "Thông lượng 5G toàn quốc tháng 12/2025 là bao nhiêu?",
     "Dữ liệu KPI 5G chỉ có từ 2026-08-01 đến 2026-08-20.", ["out_of_time_range"], None),
    ("U003", "fbb", "medium", "Cho tôi số điện thoại và địa chỉ chi tiết của từng thuê bao cáp quang.",
     "Yêu cầu dữ liệu định danh cá nhân hàng loạt: phải từ chối theo chính sách truy cập. Lưu ý catalog CÓ cột msisdn (fbb.edcr_kpi_tmp, fbb.esr_kpi_tmp), nên lý do là chính sách, không phải thiếu dữ liệu.",
     ["policy_refusal", "pii"], "DE xác nhận chính sách PII áp dụng cho NL2SQL."),
    ("U004", "alarm", "easy", "Nhân viên nào trong đội vận hành có đánh giá hiệu suất cao nhất?",
     "Không có bảng nhân sự hay đánh giá hiệu suất.", ["missing_entity"], None),
    ("U005", "data_monitoring", "easy", "Tỷ lệ hoàn thành SLA của các pipeline dữ liệu theo tháng là bao nhiêu?",
     "Không có bảng lịch chạy hoặc SLA pipeline trong schema data_monitoring.", ["missing_entity"], None),
    ("U006", "data_monitoring", "easy", "Chi phí hạ tầng cloud của từng pipeline trong tháng này là bao nhiêu?",
     "Không có dữ liệu chi phí.", ["missing_entity"], None),
    ("U007", "data_monitoring", "medium", "Dự báo số lỗi pipeline trong ba tháng tới.",
     "Catalog chỉ có dữ liệu quan sát; không có mô hình/bảng dự báo được xác thực.", ["forecast_request"], None),
    ("U008", "common_location", "medium", "Dân số từng phường năm 2030 là bao nhiêu?",
     "Có cột population ở geolocation.bin_region_map nhưng không có số liệu dự báo 2030 và không ở cấp phường.",
     ["near_synonym_column", "forecast_request"], None),
    ("U009", "data_monitoring", "hard", "Ai đã thay đổi cấu hình pipeline dữ liệu gần đây?",
     "Không có audit cấu hình pipeline. Cột update_user ở gnoc.mr_hard_group_config là cấu hình nhóm GNOC, không phải pipeline.",
     ["near_synonym_column"], "DE xác nhận mr_hard_group_config không liên quan pipeline dữ liệu."),
    ("U010", "data_monitoring", "medium", "Tỷ lệ sử dụng CPU và bộ nhớ của từng pipeline dữ liệu là bao nhiêu?",
     "Cột cpu/memory ở npms.iptv_qos_data là QoS thiết bị IPTV, không phải tài nguyên pipeline.",
     ["near_synonym_column"], None),
    ("U011", "data_monitoring", "easy", "Job nào chạy chậm nhất hôm nay?",
     "Không có bảng job/lượt chạy hay thời gian chạy. (Bản trước xếp là ambiguous: A007.)", ["missing_entity"], None),
    ("U012", "data_monitoring", "medium", "Nhóm giám sát dữ liệu nào đang có nhiều vấn đề nhất?",
     "Bảng groups chỉ có tên/mô tả nhóm; không có chỉ số vấn đề gắn với nhóm. (Bản trước xếp là ambiguous: A005.)",
     ["missing_metric"], None),
]

AMBIGUOUS = [
    # id, domain, difficulty, question, reason, options[(label, duckdb_sql | None, blocked_reason | None)]
    ("A001", "network_kpi_5g", "medium", "Top 10 cell 5G có lưu lượng cao nhất ngày 20/8/2026",
     "'Lưu lượng' có thể là tổng lưu lượng PS, lưu lượng tải xuống hoặc tải lên; mỗi cách cho top 10 khác nhau.",
     [("Tổng lưu lượng PS (nr_ps_traffic_total_gb)",
       f"SELECT object_id, CAST(nr_ps_traffic_total_gb AS DOUBLE) AS traffic_gb FROM {PEAK} WHERE date_hour = '2026-08-20-00' ORDER BY traffic_gb DESC, object_id ASC LIMIT 10;", None),
      ("Lưu lượng tải xuống (nr_dl_ps_traffic_gb)", None, "Cột toàn giá trị 0 trong dữ liệu synthetic (Phase 1)."),
      ("Lưu lượng tải lên (nr_ul_ps_traffic_gb)", None, "Cột toàn giá trị 0 trong dữ liệu synthetic (Phase 1).")]),
    ("A002", "network_kpi_5g", "hard", "Cell nào có chất lượng kém nhất tuần qua?",
     "'Chất lượng' có thể là thông lượng, độ trễ hoặc tỷ lệ mất gói.",
     [("Tốc độ tải xuống trung bình của người dùng thấp nhất, 14–20/8/2026",
       f"WITH a AS (SELECT object_id, AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS avg_tp FROM {PEAK} WHERE date BETWEEN '2026-08-14' AND '2026-08-20' AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0 GROUP BY object_id) SELECT object_id, ROUND(avg_tp, 2) AS avg_tp FROM a WHERE avg_tp = (SELECT MIN(avg_tp) FROM a) ORDER BY object_id;", None),
      ("Độ trễ tải xuống cao nhất (avg_latency_dl_ms)", None, "Cột toàn giá trị 0 trong dữ liệu synthetic (Phase 1)."),
      ("Tỷ lệ mất gói tải xuống cao nhất (dl_packet_loss_rate)", None, "Cột toàn giá trị 0 trong dữ liệu synthetic (Phase 1).")]),
    ("A003", "alarm", "medium", "Khu vực nào có nhiều cảnh báo nhất?",
     "'Khu vực' có thể là vùng vận hành (region) hoặc tỉnh.",
     [("Vùng vận hành (region)",
       "WITH c AS (SELECT region, COUNT(*) AS alarm_count FROM hive__gnoc__gnoc GROUP BY region) SELECT region, alarm_count FROM c WHERE alarm_count = (SELECT MAX(alarm_count) FROM c) ORDER BY region;", None),
      ("Tỉnh", None, "Bảng cảnh báo không có cột tỉnh; chỉ suy được qua mã trạm (heuristic).")]),
    ("A004", "fbb", "medium", "Tài khoản nào hoạt động nhiều nhất?",
     "'Hoạt động' có thể là số kết nối hiện tại, số phiên tính cước hoặc lưu lượng.",
     [("Số kết nối hiện tại lớn nhất (ftth_account_pppoe.count)",
       "SELECT username, count FROM hive__aaa__ftth_account_pppoe WHERE count = (SELECT MAX(count) FROM hive__aaa__ftth_account_pppoe) ORDER BY username;", None),
      ("Số phiên tính cước", None, "Bảng accounting không có cột tài khoản (chỉ có hostname)."),
      ("Lưu lượng", None, "Không có lưu lượng theo tài khoản trong dữ liệu.")]),
    ("A006", "common_location", "medium", "Báo cáo tình hình mạng cho miền Bắc.",
     "'Miền Bắc' chưa được ánh xạ tới area_code/tập tỉnh; khu vực chỉ có tên 'Khu vuc 1..4'. Ngoài ra 'tình hình mạng' chưa rõ chỉ số.",
     [("Theo một area_code cụ thể do người dùng chọn", None, "Cần người dùng/DE chỉ định ánh xạ miền → khu vực.")]),
]

CONVENTION_TRAPS = {
    "CONV_KPI_METRICS_CAST_DOUBLE": "cast",
    "CONV_DATE_HOUR_YYYY_MM_DD_HH": "date_format",
    "CONV_SUPERSEDE_F_LOCATION": "table_selection",
    "CONV_BAD_CELL_EXCLUDE_OCEAN": "F",
    "CONV_OCEAN_CELL_SNAPSHOT": "snapshot",
    "CONV_SCOPE_BAD_CELL_COUNTRY_VNM": "G",
    "CONV_BAD_CELL_REQUIRES_TRAFFIC": "D",
    "CONV_BAD_CELL_EXCLUDE_ZERO_THROUGHPUT": "C",
    "CONV_BAD_CELL_THRESHOLD_STRICT": "boundary",
    "CONV_COUNT_CELLS_BY_OBJECT": "grain",
    "CONV_KPI_WEEKLY_WINDOW_INCLUSIVE": "window_boundary",
}

# ------------------------------------------------------------------ helpers


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def result_hash(con, sql: str) -> tuple[str, int]:
    """Same normalisation as scripts/build_benchmark.py (V1), so hashes are comparable."""
    cur = con.execute(sql)
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    norm = sorted([[str(v) if v is not None else "NULL" for v in row] for row in rows])
    payload = json.dumps({"columns": columns, "rows": norm}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), len(rows)


def required_columns(sql: str, tables: list[str], table_columns: dict[str, list[str]]) -> list[str]:
    low = sql.lower()
    return sorted({
        f"{t}.{c}" for t in tables for c in table_columns.get(t, [])
        if re.search(rf"(?<![a-z0-9_]){re.escape(c.lower())}(?![a-z0-9_])", low)
    })


def flags_for(case_id: str) -> dict[str, str]:
    return {flag: notes[case_id] for flag, notes in REVIEW_FLAGS.items() if case_id in notes}


def annotate_conventions(case: dict, accepted: list[dict]) -> None:
    applicable, conflicts = [], []
    sql = case.get("gold_sql_duckdb")
    for conv in accepted:
        if not is_executable(conv) or not applies(conv, case, sql):
            continue
        applicable.append(conv["id"])
        if sql and (violations := run_check(sql, conv)):
            conflicts.append({"convention": conv["id"], "violations": violations})
    case["conventions"] = applicable
    case["trap_groups"] = sorted({CONVENTION_TRAPS[c] for c in applicable if c in CONVENTION_TRAPS})
    case["convention_conflicts"] = conflicts


# ------------------------------------------------------------------ benchmark


def build_benchmark_v2(catalog: dict) -> list[dict]:
    natural = json.loads(NATURAL.read_text(encoding="utf-8"))
    questions, author = natural["questions"], natural["_meta"]["author"]
    accepted = [c for c in load_registry()["conventions"] if c["status"] == "accepted"]
    table_columns = {t["trino_fqn"]: [c["name"] for c in t["columns"]] for t in catalog["tables"]}
    con = duckdb.connect(str(DB), read_only=True)

    v1 = load_jsonl(V1_CASES)
    missing = [c["id"] for c in v1 if c["id"] not in questions]
    if missing:
        raise SystemExit(f"natural_questions.json thiếu: {missing}")

    records = []
    for old in v1:
        cid = old["id"]
        row = copy.deepcopy(old)
        fix = GOLD_FIXES.get(cid)
        gold_writer = "v1_legacy"
        if fix:
            gold_writer = "v1_1_fix"
            if "sub" in fix:
                before, after = fix["sub"]
                row["gold_sql_duckdb"] = row["gold_sql_duckdb"].replace(before, after)
                row["gold_sql_trino"] = row["gold_sql_trino"].replace(before, after)
            else:
                row["gold_sql_duckdb"] = fix["duckdb"]
                row["gold_sql_trino"] = fix.get("trino", fix["duckdb"].replace("hive__gnoc__", "hive.gnoc."))
            row["gold_fix_reason"] = fix["reason"]
        row["question_explicit"] = old["question"]
        row["question_natural"] = questions[cid]
        row["expected_outcome"] = "answer"
        row["required_columns"] = required_columns(row["gold_sql_trino"], row["required_tables"], table_columns)
        if cid in BLOCKED_BY_DATA:
            row["case_status"] = "blocked_by_data"
            row["exclude_from_scoring"] = True
            row["blocked_reason"] = BLOCKED_BY_DATA[cid]
            row.pop("expected_result_sha256", None)
        else:
            row["case_status"] = "active"
            row["exclude_from_scoring"] = False
            row["expected_result_sha256"], row["expected_row_count"] = result_hash(con, row["gold_sql_duckdb"])
        annotate_conventions(row, accepted)
        row["review_flags"] = flags_for(cid)
        if row["convention_conflicts"]:
            row["review_flags"]["gold_violates_convention"] = "; ".join(c["convention"] for c in row["convention_conflicts"])
        row["generation"] = {"gold_writer": gold_writer, "question_writer": author, "cross_checker": None}
        row["review_status"] = "draft"
        records.append(row)

    for cid, diff, explicit, nat, duck, trino, tables, skills in NEW_DM_CASES:
        row = {
            "id": cid, "question": explicit, "question_explicit": explicit, "question_natural": nat,
            "difficulty": diff, "domain": "data_monitoring", "expected_outcome": "answer",
            "gold_sql_duckdb": duck, "gold_sql_trino": trino, "required_tables": tables,
            "required_columns": required_columns(trino, tables, table_columns), "skills": skills,
            "case_status": "active", "exclude_from_scoring": False,
        }
        row["expected_result_sha256"], row["expected_row_count"] = result_hash(con, duck)
        annotate_conventions(row, accepted)
        row["review_flags"] = {"new_case_v1_1": "Viết mới để bù domain Data Monitoring; chỉ dùng các cột có dữ liệu thật trong synthetic."}
        row["generation"] = {"gold_writer": author, "question_writer": author, "cross_checker": None}
        row["review_status"] = "draft"
        records.append(row)

    for cid, domain, diff, question, reason, traps, note in UNANSWERABLE:
        records.append({
            "id": cid, "question": question, "question_explicit": question, "question_natural": question,
            "difficulty": diff, "domain": domain, "expected_outcome": "unanswerable",
            "expected_outcome_reason": reason, "skills": ["abstention"], "conventions": [],
            "trap_groups": traps, "case_status": "active", "exclude_from_scoring": False,
            "review_flags": {"de_check": note} if note else {},
            "generation": {"gold_writer": None, "question_writer": author, "cross_checker": None},
            "review_status": "draft",
        })

    for cid, domain, diff, question, reason, options in AMBIGUOUS:
        opts = []
        for label, sql, blocked in options:
            opt = {"label": label, "gold_sql_duckdb": sql}
            if sql:
                opt["expected_result_sha256"], opt["expected_row_count"] = result_hash(con, sql)
            else:
                opt["blocked_reason"] = blocked
            opts.append(opt)
        records.append({
            "id": cid, "question": question, "question_explicit": question, "question_natural": question,
            "difficulty": diff, "domain": domain, "expected_outcome": "ambiguous",
            "expected_outcome_reason": reason, "clarification_options": opts,
            "skills": ["clarification"], "conventions": [], "trap_groups": ["ambiguous_term"],
            "case_status": "active", "exclude_from_scoring": False, "review_flags": {},
            "generation": {"gold_writer": author, "question_writer": author, "cross_checker": None},
            "review_status": "draft",
        })

    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "cases.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    write_readme(records)
    return records


def write_readme(records: list[dict]) -> None:
    scored = [r for r in records if not r["exclude_from_scoring"]]
    answer = [r for r in scored if r["expected_outcome"] == "answer"]
    by = lambda key, rows: ", ".join(f"{k} {v}" for k, v in sorted(Counter(r[key] for r in rows).items()))  # noqa: E731
    flag_counts = Counter(f for r in records for f in r.get("review_flags", {}))
    lines = [
        "# VTNet Mini benchmark v2",
        "",
        "Sinh bởi `scripts/build_v1_1_assets.py`; không sửa tay file `cases.jsonl`.",
        "",
        "## Trạng thái",
        "",
        f"- Tổng {len(records)} case; chấm điểm {len(scored)}; loại khỏi chấm điểm {len(records) - len(scored)} "
        f"({', '.join(r['id'] for r in records if r['exclude_from_scoring'])}: blocked_by_data).",
        f"- expected_outcome (chấm điểm): {by('expected_outcome', scored)}.",
        f"- Độ khó câu answer: {by('difficulty', answer)}.",
        f"- Domain câu answer: {by('domain', answer)}.",
        "- **Toàn bộ case ở trạng thái `draft`.** Chưa có DE review và chưa có chú thích kép độc lập.",
        "",
        "## Nguồn gốc từng trường",
        "",
        "| Trường | Nguồn |",
        "|---|---|",
        "| `question_explicit` | Câu hỏi V1 (có thể chứa tên bảng/cột) |",
        "| `question_natural` | `natural_questions.json`, viết tay; người viết có xem gold nên chưa phải kiểm tra chéo độc lập |",
        "| `gold_sql_*` | V1, trừ H002/H012/H027 (xem `gold_fix_reason`) và 7 case Data Monitoring mới |",
        "| `expected_result_sha256` | Tính lại từ DuckDB, cùng cách chuẩn hóa với V1 |",
        "| `conventions` | Quy ước `accepted` áp dụng cho case, suy ra từ câu hỏi và bảng (không từ gold) |",
        "| `convention_conflicts` | Gold vi phạm quy ước theo checker AST: cần DE xem gold sai hay quy ước quá rộng |",
        "| `review_flags` | Vấn đề phát hiện khi viết lại câu hỏi và kiểm tra gold |",
        "",
        "## Cờ review",
        "",
        *[f"- `{k}`: {v} case" for k, v in sorted(flag_counts.items())],
    ]
    (OUTPUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ metadata variants


def base_source(desc: str) -> str:
    if not desc:
        return "none"
    return "ai_gen" if desc.startswith("[AI Gen]") else "om_other"


def profiler_notes(fqn: str, col: dict, stats: dict | None, rels: list[dict]) -> tuple[list[str], bool]:
    """Vietnamese notes derived only from profiler evidence; returns (notes, replace_base)."""
    notes, replace = [], False
    if stats:
        flags = stats["flags"]
        if "numeric_text" in flags:
            notes.append("[Profiler] Giá trị đều là số nhưng lưu kiểu chuỗi; cần CAST sang kiểu số khi so sánh, tính toán hoặc sắp xếp.")
        if "format" in flags:
            fmt = {"date_hour": "YYYY-MM-DD-HH", "iso_date": "YYYY-MM-DD (chuỗi)", "yyyymmdd": "YYYYMMDD"}[stats["format"]]
            notes.append(f"[Profiler] Định dạng giá trị: {fmt}.")
        if "epoch_unit" in flags:
            unit = "giây" if stats["epoch_unit"] == "seconds" else "mili giây"
            notes.append(f"[Profiler] Epoch tính bằng {unit} (khoảng {stats['epoch_range'][0]} – {stats['epoch_range'][1]}).")
            if "millisecond" in (col.get("description") or "").lower() and stats["epoch_unit"] == "seconds":
                notes.append("[Profiler] Mô tả AI ghi 'milliseconds' mâu thuẫn với dữ liệu.")
        if "negative_sentinel" in flags:
            s = stats["negative_sentinel"]
            notes.append(f"[Profiler] Giá trị âm {s['value']} lặp lại {s['count']} lần, giống mã giá trị không hợp lệ.")
    for r in rels:
        other = r["right"] if r["left"] == fqn.rsplit(".", 1)[0] else r["left"]
        notes.append(f"[Profiler] Có {r['shared_values']} giá trị chung với {other}.{r['column']}; có thể dùng làm khóa nối.")
    desc = (col.get("description") or "").lower()
    if rels and ("chưa xác định" in desc or "chưa được mô tả" in desc):
        replace = True
    return notes, replace


def build_variants(catalog: dict) -> dict:
    if not PROFILE.exists():
        raise SystemExit("Thiếu profile_report.json: chạy scripts/profile_vtnet_metadata.py trước.")
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    rel_by_col: dict[str, list[dict]] = {}
    for r in profile["relationships"]:
        for side in ("left", "right"):
            rel_by_col.setdefault(f"{r[side]}.{r['column']}", []).append(r)

    summary = {}
    for name in ("M0", "M1", "M2"):
        v = copy.deepcopy(catalog)
        v["version"] = f"1.1-{name}"
        v["metadata_variant"] = name
        changed = replaced = 0
        for table in v["tables"]:
            if name == "M0":
                table["description"] = ""
            for col in table["columns"]:
                fqn = f"{table['trino_fqn']}.{col['name']}"
                desc = col.get("description") or ""
                if name == "M0":
                    col["description"], col["description_source"] = "", "none"
                    continue
                col["description_source"] = base_source(desc)
                if name == "M1":
                    continue
                stats = profile["columns"].get(fqn)
                if stats:
                    col["profile_flags"] = stats["flags"]
                notes, replace = profiler_notes(fqn, col, stats, rel_by_col.get(fqn, []))
                if not notes:
                    continue
                changed += 1
                if replace or not desc:
                    replaced += bool(replace)
                    col["replaced_description"] = desc if replace else None
                    col["description"] = " ".join(notes)
                    col["description_source"] = "profiler"
                else:
                    col["description"] = desc + " " + " ".join(notes)
                    col["description_source"] = f"{col['description_source']}+profiler"
        target = VARIANTS / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "catalog.json").write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary[name] = {"columns_changed_by_profiler": changed, "ai_descriptions_replaced": replaced}

    m3 = VARIANTS / "M3"
    m3.mkdir(parents=True, exist_ok=True)
    (m3 / "catalog.json").unlink(missing_ok=True)
    (m3 / "NOT_BUILT.md").write_text(
        "# M3 chưa được xây dựng\n\n"
        "M3 là mô tả do người (DE) viết tay cho khoảng 20 bảng lõi, dùng làm mốc trên trong thí nghiệm.\n"
        "Không thể sinh tự động. Không dùng M1 thay thế và gắn nhãn `human`.\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    records = build_benchmark_v2(catalog)
    variants = build_variants(catalog)
    print(json.dumps({
        "cases": len(records),
        "outcomes": dict(Counter(r["expected_outcome"] for r in records)),
        "excluded_from_scoring": [r["id"] for r in records if r["exclude_from_scoring"]],
        "variants": variants,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
