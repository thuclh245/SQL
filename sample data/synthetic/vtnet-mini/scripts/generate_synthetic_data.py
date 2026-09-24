"""
generate_synthetic_data.py
==========================
Script sinh dữ liệu tổng hợp (adversarial synthetic data) có seed 20260923:
- Cài đặt đầy đủ 8 nhóm bẫy (trap cases A-H) cho query mẫu 5G Bad Cell
- Sinh dữ liệu đa chiều, ngăn chặn hoàn toàn "lucky match" (bỏ WHERE, đổi INNER/LEFT JOIN, bỏ DISTINCT, bỏ HAVING)
- Bổ sung quan hệ 1-N thực sự để bẫy các lỗi nhân bản bản ghi (fan-out multiplication)
- Nạp vào vtnet.duckdb, cập nhật counts.json và validation_report.json
"""

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

SEED = 20260923
random.seed(SEED)

BASE_DIR = Path(__file__).resolve().parents[1]
METADATA_DIR = BASE_DIR / "metadata"
GENERATED_DIR = BASE_DIR / "generated"
DUCKDB_PATH = GENERATED_DIR / "vtnet.duckdb"
DDL_PATH = GENERATED_DIR / "ddl_duckdb.sql"

ETL_DATE = "2026-08-20"
DATES_7DAYS = [
    (datetime.strptime(ETL_DATE, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
    for i in range(7)
]
DATES_7DAYS.reverse()  # 2026-08-14 to 2026-08-20


def get_table_columns(con, table_name):
    info = con.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return [(col[1], col[2]) for col in info]


def insert_records(con, table_name, records):
    if not records:
        return
    col_names = [f'"{k}"' for k in records[0].keys()]
    placeholders = ", ".join(["?"] * len(records[0]))
    cols_clause = ", ".join(col_names)
    sql = f"INSERT INTO {table_name} ({cols_clause}) VALUES ({placeholders})"
    values = [list(r.values()) for r in records]
    con.executemany(sql, values)


def make_row_for_table(cols, explicit_values=None):
    if explicit_values is None:
        explicit_values = {}
    row = {}
    for col_name, col_type in cols:
        if col_name in explicit_values:
            val = explicit_values[col_name]
            if val is None:
                row[col_name] = None
                continue
            if col_type in ("BIGINT", "INTEGER", "SMALLINT"):
                try:
                    val = int(val)
                except Exception:
                    val = 0
            elif col_type in ("DOUBLE", "FLOAT"):
                try:
                    val = float(val)
                except Exception:
                    val = 0.0
            elif col_type == "BOOLEAN":
                val = bool(val)
            elif col_type == "TIMESTAMP":
                if not val or val == "":
                    val = f"{ETL_DATE} 00:00:00"
            elif col_type in ("BLOB", "VARBINARY"):
                val = b""
            row[col_name] = val
        else:
            if col_type in ("BIGINT", "INTEGER", "SMALLINT"):
                row[col_name] = 1787200000 if "time" in col_name.lower() else 0
            elif col_type in ("DOUBLE", "FLOAT"):
                row[col_name] = 0.0
            elif col_type == "BOOLEAN":
                row[col_name] = False
            elif col_type == "TIMESTAMP":
                row[col_name] = f"{ETL_DATE} 00:00:00"
            elif col_type in ("BLOB", "VARBINARY"):
                row[col_name] = b""
            elif "date_hour" in col_name.lower():
                row[col_name] = f"{ETL_DATE}-00"
            elif "date" in col_name.lower():
                row[col_name] = ETL_DATE
            else:
                row[col_name] = f"sample_{col_name}"
    return row


def main():
    print(f"=== VTNet Mini Adversarial Synthetic Data Generator (Seed: {SEED}) ===")
    t0 = time.time()

    # 1. Khởi tạo DuckDB từ DDL
    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()

    print(f"Connecting to DuckDB: {DUCKDB_PATH}")
    con = duckdb.connect(str(DUCKDB_PATH))

    print(f"Executing DDL from {DDL_PATH}...")
    with open(DDL_PATH, encoding="utf-8") as f:
        con.execute(f.read())
    print("DDL executed successfully.")

    # 2. Location Dimension (hive__netbi__f_location_new)
    # Lưu ý: Cần nhiều hàng trên mỗi tỉnh (nhiều huyện / date_hour) để COUNT(*) != COUNT(DISTINCT province_code)
    # Đồng thời bổ sung tỉnh orphan không có cell để thử INNER vs LEFT JOIN
    print("Populating location dimensions...")
    provinces_master = [
        # Area 1: Miền Bắc
        ("VNM", "Vietnam", "AREA_1", "Khu vuc 1", "HNI", "Ha Noi", "DPT_HNI", "VNPT/VTNet HN", ["DIST_HK", "DIST_CG", "DIST_TX"]),
        ("VNM", "Vietnam", "AREA_1", "Khu vuc 1", "HPG", "Hai Phong", "DPT_HPG", "Chi nhanh Hai Phong", ["DIST_HB", "DIST_LC"]),
        ("VNM", "Vietnam", "AREA_1", "Khu vuc 1", "QNH", "Quang Ninh", "DPT_QNH", "Chi nhanh Quang Ninh", ["DIST_HL", "DIST_CP"]),
        ("VNM", "Vietnam", "AREA_1", "Khu vuc 1", "BGG", "Bac Giang", "DPT_BGG", "Chi nhanh Bac Giang", ["DIST_BG", "DIST_YP"]),
        # Area 2: Miền Trung
        ("VNM", "Vietnam", "AREA_2", "Khu vuc 2", "DNG", "Da Nang", "DPT_DNG", "Chi nhanh Da Nang", ["DIST_HC", "DIST_TK"]),
        ("VNM", "Vietnam", "AREA_2", "Khu vuc 2", "HUE", "Thua Thien Hue", "DPT_HUE", "Chi nhanh Hue", ["DIST_HU", "DIST_PH"]),
        ("VNM", "Vietnam", "AREA_2", "Khu vuc 2", "QNM", "Quang Nam", "DPT_QNM", "Chi nhanh Quang Nam", ["DIST_TK", "DIST_HA"]),
        ("VNM", "Vietnam", "AREA_2", "Khu vuc 2", "KHA", "Khanh Hoa", "DPT_KHA", "Chi nhanh Khanh Hoa", ["DIST_NT", "DIST_CR"]),
        # Area 3: Miền Đông Nam Bộ & TP.HCM
        ("VNM", "Vietnam", "AREA_3", "Khu vuc 3", "HCM", "TP Ho Chi Minh", "DPT_HCM", "VTNet HCM", ["DIST_Q1", "DIST_Q3", "DIST_TB"]),
        ("VNM", "Vietnam", "AREA_3", "Khu vuc 3", "BDG", "Binh Duong", "DPT_BDG", "Chi nhanh Binh Duong", ["DIST_TDM", "DIST_DA"]),
        ("VNM", "Vietnam", "AREA_3", "Khu vuc 3", "DNI", "Dong Nai", "DPT_DNI", "Chi nhanh Dong Nai", ["DIST_BH", "DIST_LT"]),
        ("VNM", "Vietnam", "AREA_3", "Khu vuc 3", "VTU", "Ba Ria Vung Tau", "DPT_VTU", "Chi nhanh Vung Tau", ["DIST_VT", "DIST_BR"]),
        # Area 4: Tây Nam Bộ
        ("VNM", "Vietnam", "AREA_4", "Khu vuc 4", "CTO", "Can Tho", "DPT_CTO", "Chi nhanh Can Tho", ["DIST_NK", "DIST_CR"]),
        ("VNM", "Vietnam", "AREA_4", "Khu vuc 4", "AGG", "An Giang", "DPT_AGG", "Chi nhanh An Giang", ["DIST_LX", "DIST_CD"]),
        ("VNM", "Vietnam", "AREA_4", "Khu vuc 4", "KGG", "Kien Giang", "DPT_KGG", "Chi nhanh Kien Giang", ["DIST_RG", "DIST_HT"]),
        ("VNM", "Vietnam", "AREA_4", "Khu vuc 4", "CMU", "Ca Mau", "DPT_CMU", "Chi nhanh Ca Mau", ["DIST_CM", "DIST_TN"]),
        # Tỉnh mồ côi (Orphan) - Không có cell nào trong KPI
        ("VNM", "Vietnam", "AREA_1", "Khu vuc 1", "PRV_ORPHAN", "Tinh Mo Coi", "DPT_ORP", "Chi nhanh Orphan", ["DIST_ORP"]),
    ]

    loc_records = []
    for p in provinces_master:
        for dist in p[8]:
            loc_records.append({
                "country_name": p[1],
                "area_name": p[3],
                "area_code": p[2],
                "province_name": p[5],
                "province_code": p[4],
                "dept_code": p[6],
                "dept_name": p[7],
                "date_hour": f"{ETL_DATE}-00",
            })
    insert_records(con, "hive__netbi__f_location_new", loc_records)
    print(f"Inserted {len(loc_records)} location dimension rows (17 distinct provinces).")

    # 3. Occean Cell (hive__npms__occean_cell)
    # Bổ sung cả 5G_NR và 4G_LTE, date_hour đa dạng để WHERE cell_type = '5G_NR' có tác dụng lọc
    print("Populating occean_cell...")
    occean_records = []
    # Trap cell CELL_5G_A00 for H020
    occean_records.append({
        "object_id": "CELL_5G_A00",
        "cell_type": "5G_NR",
        "country": "VNM",
        "date": "2026-01-01",
        "_c3": "EXCLUDE_OCEAN",
        "date_hour": "2026-01-01-00",
    })
    # Trap Group F cells (5G_NR, date_hour = 2026-01-01-00)
    for i in range(1, 6):
        occean_records.append({
            "object_id": f"CELL_5G_F{i:02d}",
            "cell_type": "5G_NR",
            "country": "VNM",
            "date": "2026-01-01",
            "_c3": "EXCLUDE_OCEAN",
            "date_hour": "2026-01-01-00",
        })
    # Additional 5G ocean cells
    for i in range(1, 15):
        occean_records.append({
            "object_id": f"OCEAN_CELL_{i:03d}",
            "cell_type": "5G_NR",
            "country": "VNM",
            "date": "2026-01-01",
            "_c3": "EXCLUDE_OCEAN",
            "date_hour": "2026-01-01-00",
        })
    # Counter-example cells: cell_type = 4G_LTE (để bỏ WHERE cell_type = '5G_NR' sẽ đổi kết quả)
    for i in range(1, 10):
        occean_records.append({
            "object_id": f"OCEAN_4G_CELL_{i:03d}",
            "cell_type": "4G_LTE",
            "country": "VNM",
            "date": "2026-01-01",
            "_c3": "EXCLUDE_OCEAN_4G",
            "date_hour": "2026-01-01-00",
        })
    insert_records(con, "hive__npms__occean_cell", occean_records)

    # 4. Network KPI 5G Peak View (hive__npms__kpi_access5g_5g_cell_peak_view)
    print("Populating kpi_access5g_5g_cell_peak_view with trap cases A-H + Anomaly + Incomplete...")
    peak_cols = get_table_columns(con, "hive__npms__kpi_access5g_5g_cell_peak_view")
    peak_col_names = [c[0] for c in peak_cols]

    peak_records = []

    def make_peak_row(obj_id, p_code, a_code, d_code, dt_hr, dl_tp, traffic, ctry="VNM", ul_tp=2.5):
        row = {c: "0" for c in peak_col_names}
        row["object_id"] = obj_id
        if "province_code" in row:
            row["province_code"] = p_code
        if "area_code" in row:
            row["area_code"] = a_code
        if "district_code" in row:
            row["district_code"] = d_code
        if "date_hour" in row:
            row["date_hour"] = dt_hr
        if "date" in row:
            row["date"] = dt_hr[:10]
        if "country" in row:
            row["country"] = ctry
        if "dl_user_throughput_mbps" in row:
            row["dl_user_throughput_mbps"] = str(dl_tp)
        if "nr_ps_traffic_total_gb" in row:
            row["nr_ps_traffic_total_gb"] = str(traffic)
        if "ul_user_throughput_mbps" in row:
            row["ul_user_throughput_mbps"] = str(ul_tp)
        return row

    prov_cycler = [
        ("HNI", "AREA_1", "DIST_HK"),
        ("DNG", "AREA_2", "DIST_HC"),
        ("HCM", "AREA_3", "DIST_Q1"),
        ("CTO", "AREA_4", "DIST_NK"),
    ]

    # Group A: 10 cells -> Pass bad cell (throughput < 5 for 4 days > 3, traffic > 0)
    for i in range(1, 11):
        cell_id = f"CELL_5G_A{i:02d}"
        p_code, a_code, d_code = prov_cycler[i % len(prov_cycler)]
        for day_idx, day_str in enumerate(DATES_7DAYS):
            dt_hr = f"{day_str}-00"
            if day_idx < 4:  # 4 bad days
                dl_tp = round(2.0 + (i * 0.2), 2)  # < 5 and > 0
                traffic = round(15.0 + (i * 1.5), 2)  # > 0
                ul_tp = 2.0
            else:  # 3 good days
                dl_tp = 18.5
                traffic = 35.0
                ul_tp = 8.0
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, dl_tp, traffic, ul_tp=ul_tp))

    # Group B: 10 cells -> Fail (throughput < 5 for exactly 3 days <= 3)
    for i in range(1, 11):
        cell_id = f"CELL_5G_B{i:02d}"
        p_code, a_code, d_code = prov_cycler[(i + 1) % len(prov_cycler)]
        for day_idx, day_str in enumerate(DATES_7DAYS):
            dt_hr = f"{day_str}-00"
            if day_idx < 3:  # exactly 3 bad days
                dl_tp = 3.2
                traffic = 12.0
            else:
                dl_tp = 22.0
                traffic = 40.0
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, dl_tp, traffic))

    # Group C: 5 cells -> Fail (throughput = 0)
    for i in range(1, 6):
        cell_id = f"CELL_5G_C{i:02d}"
        p_code, a_code, d_code = prov_cycler[0]
        for day_str in DATES_7DAYS:
            dt_hr = f"{day_str}-00"
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, 0.0, 20.0))

    # Group D: 5 cells -> Fail (traffic = 0)
    for i in range(1, 6):
        cell_id = f"CELL_5G_D{i:02d}"
        p_code, a_code, d_code = prov_cycler[1]
        for day_str in DATES_7DAYS:
            dt_hr = f"{day_str}-00"
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, 2.5, 0.0))

    # Group E: 10 cells -> Fail (throughput >= 5)
    for i in range(1, 11):
        cell_id = f"CELL_5G_E{i:02d}"
        p_code, a_code, d_code = prov_cycler[2]
        for day_str in DATES_7DAYS:
            dt_hr = f"{day_str}-00"
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, 25.0, 50.0))

    # Group F: 5 cells -> Fail (in occean_cell)
    for i in range(1, 6):
        cell_id = f"CELL_5G_F{i:02d}"
        p_code, a_code, d_code = prov_cycler[3]
        for day_str in DATES_7DAYS:
            dt_hr = f"{day_str}-00"
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, 2.1, 18.0))

    # Group G: 5 cells -> Fail (country != 'VNM')
    for i in range(1, 6):
        cell_id = f"CELL_5G_G{i:02d}"
        p_code, a_code, d_code = ("VTN", "AREA_LAO", "DIST_VTE")
        for day_str in DATES_7DAYS:
            dt_hr = f"{day_str}-00"
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, 2.2, 15.0, ctry="LAO"))

    # Group H: 3 cells -> Pass with missing province mapping (LEFT JOIN retains row)
    for i in range(1, 4):
        cell_id = f"CELL_5G_H{i:02d}"
        p_code, a_code, d_code = ("UNKNOWN_PRV", "AREA_1", "DIST_UNK")
        for day_idx, day_str in enumerate(DATES_7DAYS):
            dt_hr = f"{day_str}-00"
            if day_idx < 5:  # 5 bad days
                dl_tp = 3.8
                traffic = 22.0
            else:
                dl_tp = 14.0
                traffic = 30.0
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, dt_hr, dl_tp, traffic))

    # New cell only on 2026-08-20 for INNER vs LEFT join sensitivity (high throughput in late week)
    peak_records.append(make_peak_row("CELL_5G_NEW_01", "HNI", "AREA_1", "DIST_HK", f"{ETL_DATE}-00", 35.0, 25.0))

    # CELL_5G_A00: present in occean_cell AND low traffic (<= 10.0) for H020
    peak_records.append(make_peak_row("CELL_5G_A00", "HNI", "AREA_1", "DIST_HK", f"{ETL_DATE}-00", 2.0, 5.0))

    # Cells with empty district code to ensure WHERE district_code != '' is required (H013)
    # 2 cells with empty district so HAVING COUNT(DISTINCT object_id) >= 2 is satisfied
    for day_str in DATES_7DAYS[:3]:
        peak_records.append(make_peak_row("CELL_5G_NO_DIST_01", "HNI", "AREA_1", "", f"{day_str}-00", 15.0, 20.0))
        peak_records.append(make_peak_row("CELL_5G_NO_DIST_02", "HNI", "AREA_1", "", f"{day_str}-00", 16.0, 22.0))

    # Historical records (outside 7-day window) to ensure WHERE date/date_hour filters are required
    # (kills DROP_WHERE on M016, H006, H008, H032, H044)
    for hist_date in ["2026-08-01", "2026-08-05", "2026-08-10"]:
        for i in range(1, 11):
            cell_id = f"CELL_5G_A{i:02d}"
            p_code, a_code, d_code = prov_cycler[i % len(prov_cycler)]
            peak_records.append(make_peak_row(cell_id, p_code, a_code, d_code, f"{hist_date}-00", 48.0, 60.0))
    # Historical record for AREA_5 (orphan area for H008)
    peak_records.append(make_peak_row("CELL_5G_HIST_AREA5", "PRV_HIST_05", "AREA_5", "DIST_HIST", "2026-08-01-00", 25.0, 50.0))
    # Historical high throughput for low-throughput cells to change AVG for M016
    for cell_id in ["CELL_5G_C01", "CELL_5G_D01"]:
        peak_records.append(make_peak_row(cell_id, "HNI", "AREA_1", "DIST_HK", "2026-08-01-00", 45.0, 50.0))
    # Historical dates for CELL_5G_INCOMP_01 so total dates >= 7 for H044
    for h_day in ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05"]:
        peak_records.append(make_peak_row("CELL_5G_INCOMP_01", "DNG", "AREA_2", "DIST_HC", f"{h_day}-00", 25.0, 30.0))

    # Add duplicate measurements (carrier aggregation / dual carrier) so COUNT(*) > COUNT(DISTINCT object_id)
    # Ensure traffic > 20 so DROP_DISTINCT on M019 is killed
    dup_records = []
    for r in peak_records[:50]:
        dup_row = dict(r)
        orig_traffic = float(r.get('nr_ps_traffic_total_gb', 0))
        dup_row['nr_ps_traffic_total_gb'] = str(round(orig_traffic + 10.0, 2)) if orig_traffic > 15.0 else str(round(orig_traffic * 0.5, 2))
        dup_records.append(dup_row)
    peak_records.extend(dup_records)

    # Add cells in HPG (Hai Phong) that have 100% good throughput (0 bad days) for LEFT vs INNER join test
    for i in range(1, 3):
        cell_id = f"CELL_5G_HPG_{i:02d}"
        for day_str in DATES_7DAYS:
            dt_hr = f"{day_str}-00"
            peak_records.append(make_peak_row(cell_id, "HPG", "AREA_1", "DIST_HB", dt_hr, 35.0, 40.0))
    # Anomaly records for H043 (negative throughput or > 1000)
    peak_records.append(make_peak_row("CELL_5G_ANOM_01", "HNI", "AREA_1", "DIST_HK", f"{ETL_DATE}-00", -2.5, 10.0))
    peak_records.append(make_peak_row("CELL_5G_ANOM_02", "HCM", "AREA_3", "DIST_Q1", f"{ETL_DATE}-00", 1500.0, 10.0))

    # Incomplete records for H044 (reported for only 3 days instead of 7)
    for day_str in DATES_7DAYS[:3]:
        peak_records.append(make_peak_row("CELL_5G_INCOMP_01", "DNG", "AREA_2", "DIST_HC", f"{day_str}-00", 12.0, 25.0))
    # Duplicate measurement on same date for CELL_5G_INCOMP_01 so COUNT(DISTINCT date) != COUNT(date) for H044
    peak_records.append(make_peak_row("CELL_5G_INCOMP_01", "DNG", "AREA_2", "DIST_HC", f"{DATES_7DAYS[0]}-12", 14.0, 20.0))

    # Insert peak records in chunks
    chunk_size = 500
    for idx in range(0, len(peak_records), chunk_size):
        insert_records(con, "hive__npms__kpi_access5g_5g_cell_peak_view", peak_records[idx:idx + chunk_size])
    print(f"Inserted {len(peak_records)} rows into kpi_access5g_5g_cell_peak_view.")

    # 5. Network KPI 4G (hive__npms__kpi_access4g_all_day_normal)
    print("Populating kpi_access4g_all_day_normal...")
    kpi4g_cols = [c[0] for c in get_table_columns(con, "hive__npms__kpi_access4g_all_day_normal")]
    kpi4g_records = []
    for p in provinces_master:
        if p[4] == "PRV_ORPHAN":
            continue
        for day_str in DATES_7DAYS:
            row = {c: "0" for c in kpi4g_cols}
            row["province_code"] = p[4]
            row["area_code"] = p[2]
            row["date"] = day_str
            row["date_hour"] = f"{day_str}-00"
            row["dl_cell_throughput_mbps"] = str(round(random.uniform(15.0, 45.0), 2))
            row["ul_cell_throughput_mbps"] = str(round(random.uniform(5.0, 15.0), 2))
            row["celldltrafficvolume_bit"] = str(random.randint(1000000000, 5000000000))
            kpi4g_records.append(row)
    insert_records(con, "hive__npms__kpi_access4g_all_day_normal", kpi4g_records)

    # 6. GNOC Domain (hive__gnoc__cat_department, hive__gnoc__gnoc, hive__gnoc__icms_maintain_calendar, hive__gnoc__od_history)
    print("Populating GNOC Alarm & Maintenance domain...")
    dept_cols = get_table_columns(con, "hive__gnoc__cat_department")
    dept_records = [
        make_row_for_table(dept_cols, {"department_id": "101", "dept_code": "NOC_CORE", "dept_name": "Phong Van Hanh Core", "location_id": "AREA_1", "date_hour": f"{ETL_DATE}-00"}),
        make_row_for_table(dept_cols, {"department_id": "102", "dept_code": "NOC_RAN", "dept_name": "Phong Van Hanh Vo Tuyen", "location_id": "AREA_2", "date_hour": f"{ETL_DATE}-00"}),
        make_row_for_table(dept_cols, {"department_id": "103", "dept_code": "NOC_TRANS", "dept_name": "Phong Truyen Dan", "location_id": "AREA_3", "date_hour": f"{ETL_DATE}-00"}),
        make_row_for_table(dept_cols, {"department_id": "104", "dept_code": "NOC_POWER", "dept_name": "Phong Nguon & Ha Tang", "location_id": "AREA_4", "date_hour": f"{ETL_DATE}-00"}),
        make_row_for_table(dept_cols, {"department_id": "105", "dept_code": "FIN_DEPT", "dept_name": "Phong Tai Chinh", "location_id": "HQ_FIN", "date_hour": f"{ETL_DATE}-00"}),
        make_row_for_table(dept_cols, {"department_id": "106", "dept_code": "HR_DEPT", "dept_name": "Phong Nhan Su", "location_id": "HQ_HR", "date_hour": f"{ETL_DATE}-00"}),
        make_row_for_table(dept_cols, {"department_id": "999", "dept_code": "", "dept_name": "Phong Chua Phan Loai", "location_id": "AREA_1", "date_hour": f"{ETL_DATE}-00"}),
    ]
    insert_records(con, "hive__gnoc__cat_department", dept_records)

    gnoc_cols = get_table_columns(con, "hive__gnoc__gnoc")
    gnoc_records = [
        make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_AAA_01", "station_code": "SITE_AAA_001", "vendor": "Huawei", "region": "AREA_1", "network_type": "5G", "level_important": "CRITICAL", "date_hour": "2026-08-20-00", "uptime_date": "2026-08-20 15:00:00", "last_date": "2026-08-20 00:00:00"}),
        make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_AAA_02", "station_code": "SITE_AAA_001", "vendor": "Huawei", "region": "AREA_1", "network_type": "5G", "level_important": "CRITICAL", "date_hour": "2026-08-20-01", "uptime_date": "2026-08-20 15:00:00", "last_date": "2026-08-20 00:00:00"}),
        make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_AAA_03", "station_code": "SITE_AAA_001", "vendor": "Huawei", "region": "AREA_1", "network_type": "5G", "level_important": "CRITICAL", "date_hour": "2026-08-20-02", "uptime_date": "2026-08-20 15:00:00", "last_date": "2026-08-20 00:00:00"}),
    ]
    severities = ["CRITICAL", "MAJOR", "MINOR", "WARNING"]
    vendors = ["Huawei", "Ericsson", "ZTE", "Nokia"]
    net_types = ["5G", "4G", "3G", "FBB"]

    # Đưa vào 100 cảnh báo với nhiều cảnh báo trên cùng 1 trạm (Fanout trap)
    # SITE_HNI_001 có 3 cảnh báo (2 CRITICAL, 1 MAJOR)
    # SITE_HCM_001 có 4 cảnh báo (1 CRITICAL, 2 MAJOR, 1 MINOR)
    # SITE_DNG_001 có 2 cảnh báo (1 CRITICAL, 1 WARNING)
    # SITE_ORPHAN_999 có 2 cảnh báo nhưng không có trong inventory
    # Một số cảnh báo ở khung giờ giao ngày (2026-08-19-23, 2026-08-20-00, 2026-08-20-01) cho H005
    for i in range(1, 101):
        if i <= 3:
            st_code = "SITE_HNI_001"
            reg = "AREA_1"
            sev = "CRITICAL" if i <= 2 else "MAJOR"
        elif i <= 7:
            st_code = "SITE_HCM_001"
            reg = "AREA_3"
            sev = "CRITICAL" if i <= 5 else "MAJOR"
        elif i <= 9:
            st_code = "SITE_DNG_001"
            reg = "AREA_2"
            sev = "CRITICAL" if i == 8 else "WARNING"
        elif i <= 11:
            st_code = "SITE_ORPHAN_999"
            reg = "AREA_1"
            sev = "CRITICAL"
        else:
            p = provinces_master[i % len(provinces_master)]
            st_code = f"SITE_{p[4]}_{i:03d}"
            reg = p[2]
            sev = severities[i % 4]

        ven = vendors[i % 4]
        net = net_types[i % 4]

        # Khung giờ: 10 cảnh báo rơi vào khung giờ giao ngày
        if i in (1, 2, 3, 4):
            dt_hr = "2026-08-19-23"
        elif i in (5, 6, 7):
            dt_hr = "2026-08-20-00"
        elif i in (8, 9, 10):
            dt_hr = "2026-08-20-01"
        else:
            dt_hr = f"2026-08-{14 + (i % 7):02d}-{8 + (i % 12):02d}"

        # Uptime date: 35 cảnh báo chưa đóng (None/NULL) cho H004
        up_time = None if (i % 3 == 0) else f"2026-08-20 15:{i % 60:02d}:00"

        gnoc_records.append(make_row_for_table(gnoc_cols, {
            "schedule_id": f"SCHED_{i:05d}",
            "station_code": st_code,
            "vendor": ven,
            "region": reg,
            "network_type": net,
            "level_important": sev,
            "date_hour": dt_hr,
            "uptime_date": up_time,
            "last_date": f"2026-08-{14 + (i % 7):02d} 00:00:00",
        }))

    # Alarms for blacklist enodebs (1001, 2001) matching SUBSTR(station_code, -4)
    # STA_1001 has 2 CRITICAL and 1 MINOR alarms (kills DROP_WHERE on H015, H022)
    gnoc_records.append(make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_BL_01", "station_code": "STA_1001", "vendor": "Huawei", "region": "AREA_1", "network_type": "4G", "level_important": "CRITICAL", "date_hour": f"{ETL_DATE}-00"}))
    gnoc_records.append(make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_BL_02", "station_code": "STA_1001", "vendor": "Huawei", "region": "AREA_1", "network_type": "4G", "level_important": "CRITICAL", "date_hour": f"{ETL_DATE}-01"}))
    gnoc_records.append(make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_BL_03", "station_code": "STA_1001", "vendor": "Huawei", "region": "AREA_1", "network_type": "4G", "level_important": "MINOR", "date_hour": f"{ETL_DATE}-02"}))
    # STA_2001 has 1 MINOR alarm (0 CRITICAL)
    gnoc_records.append(make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_BL_04", "station_code": "STA_2001", "vendor": "Huawei", "region": "AREA_1", "network_type": "4G", "level_important": "MINOR", "date_hour": f"{ETL_DATE}-00"}))
    # Empty station code for H009 (kills DROP_WHERE on H009)
    gnoc_records.append(make_row_for_table(gnoc_cols, {"schedule_id": "SCHED_EMPTY_01", "station_code": "", "vendor": "Huawei", "region": "AREA_1", "network_type": "5G", "level_important": "MINOR", "date_hour": f"{ETL_DATE}-00"}))

    insert_records(con, "hive__gnoc__gnoc", gnoc_records)

    # ICMS Maintain Calendar (40 records)
    # SITE_HNI_001 có 2 phiếu bảo dưỡng (1 COMPLETED, 1 IN_PROGRESS) -> kết hợp với 3 cảnh báo tạo fanout x6 nếu join sai!
    icms_cols = get_table_columns(con, "hive__gnoc__icms_maintain_calendar")
    icms_records = []
    statuses = ["COMPLETED", "IN_PROGRESS", "PENDING", "CANCELLED"]
    for i in range(1, 41):
        if i == 1:
            st_code = "SITE_HNI_001"
            st_stat = "IN_PROGRESS"
            a_code, a_name = "AREA_1", "Khu vuc 1"
        elif i == 2:
            st_code = "SITE_HNI_001"
            st_stat = "COMPLETED"
            a_code, a_name = "AREA_1", "Khu vuc 1"
        elif i == 3:
            st_code = "SITE_HCM_001"
            st_stat = "IN_PROGRESS"
            a_code, a_name = "AREA_3", "Khu vuc 3"
        elif i == 4:
            st_code = "SITE_DNG_001"
            st_stat = "COMPLETED"
            a_code, a_name = "AREA_2", "Khu vuc 2"
        else:
            p = provinces_master[i % len(provinces_master)]
            st_code = f"SITE_{p[4]}_{i:03d}"
            st_stat = statuses[i % 4]
            a_code, a_name = p[2], p[3]

        icms_records.append(make_row_for_table(icms_cols, {
            "maintain_calendar_id": f"MC_{i:05d}",
            "station_code": st_code,
            "area_code": a_code,
            "area_name": a_name,
            "wo_status": st_stat,
            "cycle": "MONTHLY",
            "date_hour": f"{ETL_DATE}-00",
            "maintain_date_nearrest": "2026-08-18 09:00:00",
        }))

    # Empty station code for H009
    icms_records.append(make_row_for_table(icms_cols, {
        "maintain_calendar_id": "MC_EMPTY_01",
        "station_code": "",
        "area_code": "AREA_1",
        "area_name": "Khu vuc 1",
        "wo_status": "COMPLETED",
        "cycle": "MONTHLY",
        "date_hour": f"{ETL_DATE}-00",
        "maintain_date_nearrest": "2026-08-18 09:00:00",
    }))
    # Maintenance in AREA_5 (orphan area without alarms in GNOC for H047)
    icms_records.append(make_row_for_table(icms_cols, {
        "maintain_calendar_id": "MC_ORPHAN_AREA5",
        "station_code": "SITE_ORP_501",
        "area_code": "AREA_5",
        "area_name": "Khu vuc 5",
        "wo_status": "IN_PROGRESS",
        "cycle": "MONTHLY",
        "date_hour": f"{ETL_DATE}-00",
        "maintain_date_nearrest": "2026-08-18 09:00:00",
    }))
    insert_records(con, "hive__gnoc__icms_maintain_calendar", icms_records)

    # OD History (30 records)
    od_cols = get_table_columns(con, "hive__gnoc__od_history")
    od_records = []
    od_statuses = ["APPROVED", "REJECTED", "PENDING_APPROVAL", "CLOSED"]
    for i in range(1, 31):
        od_records.append(make_row_for_table(od_cols, {
            "id": i,
            "new_status": od_statuses[i % 4],
            "user_name": f"operator_{1 + (i % 5):02d}",
            "date_hour": f"{ETL_DATE}-00",
        }))
    insert_records(con, "hive__gnoc__od_history", od_records)

    # 7. AAA & FBB Domain
    print("Populating AAA and FBB domain with adversarial distributions...")
    aaa_cols = get_table_columns(con, "hive__aaa__ftth_account_pppoe")
    auth_cols = get_table_columns(con, "hive__aaa__authentication")
    acct_cols = get_table_columns(con, "hive__aaa__accounting")

    aaa_records = []
    auth_records = []
    acct_records = []

    # 60 FTTH accounts: phân bố groupname đa dạng, loginlimit đa dạng ('0', '1', '2', '5')
    groups = ["FTTH_VIP", "FTTH_HOME", "FTTH_BUSINESS"]
    limits = ["0", "1", "2", "5"]
    for i in range(1, 61):
        uname = f"ftth_user_{i:04d}@vtnet.vn"
        grp = groups[i % 3]
        lmt = limits[i % 4]
        # Some accounts have count 0, some 1, some 3
        cnt_val = (i * 2) % 4
        aaa_records.append(make_row_for_table(aaa_cols, {
            "username": uname,
            "groupname": grp,
            "loginlimit": lmt,
            "count": cnt_val,
            "count_time": "2026-08-20 00:00:00",
            "date_hour": f"{ETL_DATE}-00",
        }))

    # Hostnames BRAS:
    # 'bras_clean_01': Có accept = 150 nhưng reject = 0 (Anti-join / zero-reject test case!)
    # 'bras_no_acct_01': Có trong authentication nhưng không có trong accounting (Orphan test case!)
    # 'bras_hni_01', 'bras_dng_01', 'bras_hcm_01', 'bras_cto_01': normal BRAS
    bras_hosts = [
        ("bras_clean_01", "10.10.1.1", "radius_srv_01", 150, 0),
        ("bras_no_acct_01", "10.10.2.1", "radius_srv_01", 80, 5),
        ("bras_hni_01", "10.20.1.1", "radius_srv_01", 200, 15),
        ("bras_dng_01", "10.20.2.1", "radius_srv_02", 120, 8),
        ("bras_hcm_01", "10.20.3.1", "radius_srv_02", 300, 25),
        ("bras_cto_01", "10.20.4.1", "radius_srv_03", 110, 6),
    ]

    for host, ip_val, server, acc, rej in bras_hosts:
        for hr in range(8, 18):
            dt_hr = f"{ETL_DATE}-{hr:02d}"
            auth_records.append(make_row_for_table(auth_cols, {
                "hostname": host,
                "ip": ip_val,
                "sbr_server": server,
                "timestamp": f"2026-08-20 {hr:02d}:00:00",
                "date_hour": dt_hr,
                "accept": str(acc + (hr * 2)),
                "reject": str(rej),
            }))

            # Skip accounting for 'bras_no_acct_01'
            if host != "bras_no_acct_01":
                # Start differs from accept by > 10 for H040 reconciliation, EXCEPT for bras_clean_01 (discrepancy = 0 <= 10)
                if host == "bras_clean_01":
                    start_val = acc + (hr * 2)
                else:
                    start_val = (acc + (hr * 2)) - 15 if hr % 2 == 0 else (acc + (hr * 2)) - 5

                acct_records.append(make_row_for_table(acct_cols, {
                    "hostname": host,
                    "ip": ip_val,
                    "sbr_server": server,
                    "timestamp": f"2026-08-20 {hr:02d}:00:00",
                    "date_hour": dt_hr,
                    "start": str(start_val),
                    "stop": str(start_val - 2),
                    "interim": str(start_val * 2),
                }))
                # Duplicate date_hour record for H007 (so COUNT(DISTINCT date_hour) != COUNT(date_hour))
                if host == "bras_hni_01" and hr == 8:
                    acct_records.append(make_row_for_table(acct_cols, {
                        "hostname": host,
                        "ip": ip_val,
                        "sbr_server": server,
                        "timestamp": f"2026-08-20 {hr:02d}:30:00",
                        "date_hour": dt_hr,
                        "start": "50",
                        "stop": "48",
                        "interim": "100",
                    }))

    insert_records(con, "hive__aaa__ftth_account_pppoe", aaa_records)
    insert_records(con, "hive__aaa__authentication", auth_records)
    insert_records(con, "hive__aaa__accounting", acct_records)
    print(f"Inserted {len(aaa_records)} FTTH accounts, {len(auth_records)} Auth records, {len(acct_records)} Acct records.")

    # 8. Data Monitoring Domain
    print("Populating Data Monitoring domain...")
    group_cols = get_table_columns(con, "mysql_datamon__data_monitoring__groups")
    groups_records = [
        make_row_for_table(group_cols, {"id": 1, "name": "VIP_CAMPAIGN", "description": "Nhom uu tien cao"}),
        make_row_for_table(group_cols, {"id": 2, "name": "RISK_FRAUD", "description": "Nhom nghi ngo gian lan"}),
        make_row_for_table(group_cols, {"id": 3, "name": "CHURN_RISK", "description": "Nhom nguy co roi mang"}),
    ]
    insert_records(con, "mysql_datamon__data_monitoring__groups", groups_records)

    bl_cols = get_table_columns(con, "mysql_datamon__data_monitoring__usersinarea_blacklist")
    bl_records = []
    for i in range(1, 30):
        bl_records.append(make_row_for_table(bl_cols, {"id": i, "create_time": "2026-08-20 10:00:00"}))
    insert_records(con, "mysql_datamon__data_monitoring__usersinarea_blacklist", bl_records)

    # Blacklist enodeb id (H022, H038, H015, H048)
    bl_enodeb_cols = get_table_columns(con, "mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id")
    bl_enodeb_records = []
    # Enodeb 1001 matching STA_1001 (has CRITICAL alarm), with duplicate entries for DISTINCT sensitivity
    bl_enodeb_records.append(make_row_for_table(bl_enodeb_cols, {"id": 1, "enodeb_id": 1001, "zone_id": 10}))
    bl_enodeb_records.append(make_row_for_table(bl_enodeb_cols, {"id": 101, "enodeb_id": 1001, "zone_id": 10}))  # duplicate (1001, zone 10)
    bl_enodeb_records.append(make_row_for_table(bl_enodeb_cols, {"id": 102, "enodeb_id": 1001, "zone_id": 11}))  # multi-zone
    # Enodeb 2001 matching STA_2001 (silent station with 0 critical alarms)
    bl_enodeb_records.append(make_row_for_table(bl_enodeb_cols, {"id": 2, "enodeb_id": 2001, "zone_id": 20}))
    bl_enodeb_records.append(make_row_for_table(bl_enodeb_cols, {"id": 103, "enodeb_id": 2001, "zone_id": 20}))  # duplicate (2001, zone 20)
    for i in range(3, 20):
        bl_enodeb_records.append(make_row_for_table(bl_enodeb_cols, {"id": i, "enodeb_id": 3000 + i, "zone_id": 100 + i}))
    insert_records(con, "mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id", bl_enodeb_records)

    # KQI Monitor Web
    kqi_cols = get_table_columns(con, "mysql_datamon__data_monitoring__kqi_monitor_web")
    kqi_records = []
    for i in range(1, 31):
        val = 85 - (i * 2) if i <= 20 else -10  # negative anomaly
        kqi_records.append(make_row_for_table(kqi_cols, {
            "id": i,
            "ts": 1787200000 + (i * 3600),
            "name": f"KQI_HTTP_LATENCY_{i % 5}",
            "value": val,
        }))
    insert_records(con, "mysql_datamon__data_monitoring__kqi_monitor_web", kqi_records)

    # 9. Generic Population for all remaining tables
    print("Populating dummy baseline rows for remaining executable tables...")
    all_tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
    populated_counts = {}

    for tname in all_tables:
        cnt = con.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
        if cnt == 0:
            cols = get_table_columns(con, tname)
            dummy_rows = []
            for r_idx in range(1, 6):
                explicit = {
                    "id": r_idx,
                    "date_hour": f"{ETL_DATE}-00",
                    "date": ETL_DATE,
                }
                dummy_rows.append(make_row_for_table(cols, explicit))
            insert_records(con, tname, dummy_rows)

        final_cnt = con.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
        populated_counts[tname] = final_cnt

    print(f"Total tables populated: {len(populated_counts)}")
    print(f"Total rows in DuckDB: {sum(populated_counts.values())}")

    # Write counts.json
    counts_path = GENERATED_DIR / "counts.json"
    with open(counts_path, "w", encoding="utf-8") as f:
        json.dump(populated_counts, f, ensure_ascii=False, indent=2)
    print(f"Saved {counts_path}.")

    # 10. Verification: Execute Production Bad Cell Query on DuckDB!
    print("\n--- Running Production Bad Cell Verification Query on DuckDB ---")
    bad_cell_query = f"""
    WITH raw_data AS (
        SELECT
            CONCAT('{ETL_DATE}', '-00') AS date_hour,
            province_code,
            area_code,
            district_code,
            object_id,
            COUNT(*) AS no_bad_day,
            AVG(CAST(dl_user_throughput_mbps AS double)) AS dl_user_throughput_mbps
        FROM hive__npms__kpi_access5g_5g_cell_peak_view t
        WHERE country = 'VNM'
          AND date_hour >= '2026-08-14-00'
          AND date_hour <= '2026-08-20-00'
          AND CAST(nr_ps_traffic_total_gb AS double) > 0
          AND CAST(dl_user_throughput_mbps AS double) < 5
          AND CAST(dl_user_throughput_mbps AS double) > 0
          AND NOT EXISTS (
              SELECT 1
              FROM hive__npms__occean_cell c
              WHERE c.object_id = t.object_id
                AND c.date_hour = '2026-01-01-00'
          )
        GROUP BY
            province_code,
            area_code,
            district_code,
            object_id
        HAVING COUNT(*) > 3
    ),
    result AS (
        SELECT
            'VNM' AS country,
            area_code AS area_name,
            province_code,
            COUNT(object_id) AS kpi_value,
            date_hour,
            'bad_cell_throughput_5g' AS kpi_code
        FROM raw_data
        GROUP BY GROUPING SETS (
            (area_code, province_code, date_hour),
            (area_code, date_hour),
            (date_hour)
        )
    )
    SELECT
        r.country,
        r.area_name,
        r.province_code,
        f.province_name,
        r.kpi_value,
        CASE
            WHEN r.area_name IS NOT NULL AND r.province_code IS NOT NULL THEN 'province'
            WHEN r.area_name IS NOT NULL AND r.province_code IS NULL THEN 'area'
            WHEN r.area_name IS NULL AND r.province_code IS NULL THEN 'network'
        END AS location_level,
        r.date_hour,
        r.kpi_code
    FROM result r
    LEFT JOIN (SELECT DISTINCT province_code, province_name FROM hive__netbi__f_location_new) f
        ON r.province_code = f.province_code
    ORDER BY location_level, r.area_name, r.province_code;
    """

    res = con.execute(bad_cell_query).fetchall()
    print(f"Bad cell query returned {len(res)} aggregated rows:")
    for row in res:
        print(f"  Level: {row[5]:10} | Area: {str(row[1]):8} | Province: {str(row[2]):12} ({str(row[3])}) | KPI Value: {row[4]}")

    # Inspect the raw_data cell list
    raw_cells = con.execute("""
        SELECT object_id, province_code, COUNT(*) as bad_days, AVG(CAST(dl_user_throughput_mbps AS double))
        FROM hive__npms__kpi_access5g_5g_cell_peak_view t
        WHERE country = 'VNM'
          AND date_hour >= '2026-08-14-00'
          AND date_hour <= '2026-08-20-00'
          AND CAST(nr_ps_traffic_total_gb AS double) > 0
          AND CAST(dl_user_throughput_mbps AS double) < 5
          AND CAST(dl_user_throughput_mbps AS double) > 0
          AND NOT EXISTS (
              SELECT 1
              FROM hive__npms__occean_cell c
              WHERE c.object_id = t.object_id
                AND c.date_hour = '2026-01-01-00'
          )
        GROUP BY object_id, province_code
        HAVING COUNT(*) > 3
        ORDER BY object_id
    """).fetchall()

    passed_cell_ids = [r[0] for r in raw_cells]
    print(f"\nPassed bad cells ({len(passed_cell_ids)}): {passed_cell_ids}")

    # Validation checks
    group_a_ok = all(f"CELL_5G_A{i:02d}" in passed_cell_ids for i in range(1, 11))
    group_h_ok = all(f"CELL_5G_H{i:02d}" in passed_cell_ids for i in range(1, 4))
    excluded_ok = not any(
        f"CELL_5G_{grp}" in cell
        for grp in ("B", "C", "D", "E", "F", "G")
        for cell in passed_cell_ids
    )

    print(f"Check Group A (Valid bad cells): {'PASSED' if group_a_ok else 'FAILED'}")
    print(f"Check Group H (Left join missing province): {'PASSED' if group_h_ok else 'FAILED'}")
    print(f"Check Trap Groups B-G (Exclusions): {'PASSED' if excluded_ok else 'FAILED'}")

    assert group_a_ok and group_h_ok and excluded_ok, "Trap verification failed!"

    # 11. Write validation_report.json
    validation_report = {
        "status": "PASSED",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "seed": SEED,
        "database_file": str(DUCKDB_PATH.name),
        "total_tables": len(populated_counts),
        "total_rows": sum(populated_counts.values()),
        "test_results": {
            "group_a_valid_bad_cells": {
                "expected": 10,
                "passed": sum(1 for i in range(1, 11) if f"CELL_5G_A{i:02d}" in passed_cell_ids),
                "status": "PASS",
            },
            "group_b_exactly_3_days_excluded": {
                "expected_excluded": 10,
                "actually_excluded": sum(1 for i in range(1, 11) if f"CELL_5G_B{i:02d}" not in passed_cell_ids),
                "status": "PASS",
            },
            "group_c_zero_throughput_excluded": {
                "expected_excluded": 5,
                "actually_excluded": sum(1 for i in range(1, 6) if f"CELL_5G_C{i:02d}" not in passed_cell_ids),
                "status": "PASS",
            },
            "group_d_zero_traffic_excluded": {
                "expected_excluded": 5,
                "actually_excluded": sum(1 for i in range(1, 6) if f"CELL_5G_D{i:02d}" not in passed_cell_ids),
                "status": "PASS",
            },
            "group_e_high_throughput_excluded": {
                "expected_excluded": 10,
                "actually_excluded": sum(1 for i in range(1, 11) if f"CELL_5G_E{i:02d}" not in passed_cell_ids),
                "status": "PASS",
            },
            "group_f_ocean_cells_excluded": {
                "expected_excluded": 5,
                "actually_excluded": sum(1 for i in range(1, 6) if f"CELL_5G_F{i:02d}" not in passed_cell_ids),
                "status": "PASS",
            },
            "group_g_laos_cells_excluded": {
                "expected_excluded": 5,
                "actually_excluded": sum(1 for i in range(1, 6) if f"CELL_5G_G{i:02d}" not in passed_cell_ids),
                "status": "PASS",
            },
            "group_h_missing_province_left_joined": {
                "expected": 3,
                "passed": sum(1 for i in range(1, 4) if f"CELL_5G_H{i:02d}" in passed_cell_ids),
                "status": "PASS",
            },
        },
    }

    report_path = GENERATED_DIR / "validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(validation_report, f, ensure_ascii=False, indent=2)
    print(f"Validation report saved to {report_path}.")
    print(f"Done in {round(time.time() - t0, 2)}s.")


if __name__ == "__main__":
    main()
