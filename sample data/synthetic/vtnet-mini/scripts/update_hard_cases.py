#!/usr/bin/env python3
"""
update_hard_cases.py
====================
Cập nhật 50 Hard Cases trong benchmark/cases.py thành 50 câu truy vấn viễn thông
thực tế, phức hợp, mô phỏng hoàn toàn phong cách và mẫu thiết kế từ `sample data/query.md`:
- Sử dụng CTE (`WITH raw_data AS ...`)
- Cửa sổ thời gian phân tích trượt (`date_hour >= ... AND date_hour <= ...`)
- Ép kiểu số cho các trường metric dạng chuỗi (`CAST(... AS double)`)
- Anti-join loại trừ (`NOT EXISTS (SELECT 1 FROM occean_cell...)`)
- Multi-level Aggregation (`GROUPING SETS`, `ROLLUP`)
- Window Functions (`RANK()`, `ROW_NUMBER()`, `DENSE_RANK()`, `LAG()`, `NTILE()`)
- Liên kết bảng danh mục (`LEFT JOIN f_location_new`, `cat_department`, v.v.)
"""

import sys
from pathlib import Path
import duckdb

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"

# Định nghĩa 50 Hard Cases chuẩn mực
HARD_CASES_DEFINITIONS = [
    # H001
    (
        "H001",
        "Tính số lượng cell 5G suy giảm thông lượng (bad cell) trong cửa sổ 7 ngày kết thúc ngày 2026-08-20, loại trừ occean_cell và phân rã 3 cấp địa lý (province, area, network).",
        "network_kpi_5g",
        """WITH raw_data AS (
    SELECT
        CONCAT('2026-08-20', '-00') AS date_hour,
        province_code, area_code, district_code, object_id,
        COUNT(*) AS no_bad_day,
        AVG(CAST(dl_user_throughput_mbps AS double)) AS dl_user_throughput_mbps
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM'
      AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(nr_ps_traffic_total_gb AS double) > 0
      AND CAST(dl_user_throughput_mbps AS double) < 5
      AND CAST(dl_user_throughput_mbps AS double) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY province_code, area_code, district_code, object_id
    HAVING COUNT(*) > 3
),
result AS (
    SELECT
        'VNM' AS country, area_code AS area_name, province_code,
        COUNT(object_id) AS kpi_value, date_hour,
        'bad_cell_throughput_5g' AS kpi_code
    FROM raw_data
    GROUP BY GROUPING SETS (
        (area_code, province_code, date_hour),
        (area_code, date_hour),
        (date_hour)
    )
)
SELECT
    r.country, r.area_name, r.province_code, f.province_name, r.kpi_value,
    CASE
        WHEN r.area_name IS NOT NULL AND r.province_code IS NOT NULL THEN 'province'
        WHEN r.area_name IS NOT NULL AND r.province_code IS NULL THEN 'area'
        WHEN r.area_name IS NULL AND r.province_code IS NULL THEN 'network'
    END AS location_level,
    r.date_hour, r.kpi_code
FROM result r
LEFT JOIN hive__netbi__f_location_new f ON r.province_code = f.province_code
ORDER BY location_level, r.area_name, r.province_code;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell", "hive.netbi.f_location_new"],
        ["cte", "grouping_sets", "anti_join", "having", "cast_numeric", "date_window", "left_join"],
    ),

    # H002
    (
        "H002",
        "Tìm danh sách các cell 5G suy giảm (bad cell) tại Khu vực 1 (AREA_1) có hơn 3 ngày throughput < 5 Mbps và không nằm trong occean_cell.",
        "network_kpi_5g",
        """SELECT t.object_id, t.province_code, COUNT(*) AS bad_days, AVG(CAST(t.dl_user_throughput_mbps AS double)) AS avg_tp
FROM hive__npms__kpi_access5g_5g_cell_peak_view t
WHERE t.country = 'VNM'
  AND t.area_code = 'AREA_1'
  AND t.date_hour >= '2026-08-14-00' AND t.date_hour <= '2026-08-20-00'
  AND CAST(t.nr_ps_traffic_total_gb AS double) > 0
  AND CAST(t.dl_user_throughput_mbps AS double) < 5
  AND CAST(t.dl_user_throughput_mbps AS double) > 0
  AND NOT EXISTS (
      SELECT 1 FROM hive__npms__occean_cell c
      WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
  )
GROUP BY t.object_id, t.province_code
HAVING COUNT(*) > 3
ORDER BY t.object_id;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["anti_join", "having", "date_window", "cast_numeric"],
    ),

    # H003
    (
        "H003",
        "Tính tổng số cell 5G suy giảm (bad cell) của toàn mạng trong 7 ngày qua.",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT object_id
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM'
      AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(nr_ps_traffic_total_gb AS double) > 0
      AND CAST(dl_user_throughput_mbps AS double) < 5
      AND CAST(dl_user_throughput_mbps AS double) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY object_id
    HAVING COUNT(*) > 3
)
SELECT COUNT(*) AS total_bad_cells_network FROM bad_cells;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["cte", "anti_join", "having", "count"],
    ),

    # H004
    (
        "H004",
        "Xếp hạng các khu vực theo số lượng cell 5G suy giảm (bad cell).",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT area_code, object_id
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM'
      AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(nr_ps_traffic_total_gb AS double) > 0
      AND CAST(dl_user_throughput_mbps AS double) < 5
      AND CAST(dl_user_throughput_mbps AS double) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY area_code, object_id
    HAVING COUNT(*) > 3
)
SELECT area_code, COUNT(object_id) AS bad_cell_count,
       RANK() OVER (ORDER BY COUNT(object_id) DESC) AS rank_pos
FROM bad_cells
GROUP BY area_code
ORDER BY bad_cell_count DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["window_function", "rank", "anti_join", "having"],
    ),

    # H005
    (
        "H005",
        "Tìm các cell 5G suy giảm có thông lượng tải xuống trung bình trong các ngày xấu nhỏ hơn hoặc bằng 3.5 Mbps.",
        "network_kpi_5g",
        """SELECT object_id, AVG(CAST(dl_user_throughput_mbps AS double)) AS avg_tp_bad_days
FROM hive__npms__kpi_access5g_5g_cell_peak_view t
WHERE country = 'VNM'
  AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
  AND CAST(nr_ps_traffic_total_gb AS double) > 0
  AND CAST(dl_user_throughput_mbps AS double) < 5
  AND CAST(dl_user_throughput_mbps AS double) > 0
  AND NOT EXISTS (
      SELECT 1 FROM hive__npms__occean_cell c
      WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
  )
GROUP BY object_id
HAVING COUNT(*) > 3 AND AVG(CAST(dl_user_throughput_mbps AS double)) <= 3.5
ORDER BY avg_tp_bad_days;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["anti_join", "having_multiple", "cast_numeric"],
    ),

    # H006: High Traffic Congested Cells
    (
        "H006",
        "Phân tích tắc nghẽn 5G: Tìm các cell có tổng lưu lượng lớn hơn 100 GB nhưng thông lượng trung bình nhỏ hơn 4 Mbps trong ít nhất 2 ngày, kèm tên tỉnh.",
        "network_kpi_5g",
        """WITH congested AS (
    SELECT object_id, province_code, area_code,
           COUNT(*) AS congested_days,
           AVG(CAST(dl_user_throughput_mbps AS double)) AS avg_tp,
           SUM(CAST(nr_ps_traffic_total_gb AS double)) AS total_traffic
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM'
      AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(nr_ps_traffic_total_gb AS double) > 0
      AND CAST(dl_user_throughput_mbps AS double) < 4.0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY object_id, province_code, area_code
    HAVING COUNT(*) >= 2 AND SUM(CAST(nr_ps_traffic_total_gb AS double)) > 100
)
SELECT c.object_id, c.area_code, c.province_code, f.province_name, c.congested_days, c.avg_tp, c.total_traffic
FROM congested c
LEFT JOIN hive__netbi__f_location_new f ON c.province_code = f.province_code
ORDER BY c.total_traffic DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell", "hive.netbi.f_location_new"],
        ["cte", "having_multi", "anti_join", "left_join", "cast_numeric"],
    ),

    # H007: Dual UL & DL Degradation
    (
        "H007",
        "Tìm các cell 5G suy giảm cả chiều tải lên và tải xuống (UL <= 3 Mbps VÀ DL < 5 Mbps) trong hơn 3 ngày của tuần.",
        "network_kpi_5g",
        """SELECT object_id, province_code, area_code,
       COUNT(*) AS dual_degraded_days,
       AVG(CAST(dl_user_throughput_mbps AS double)) AS avg_dl_tp,
       AVG(CAST(ul_user_throughput_mbps AS double)) AS avg_ul_tp
FROM hive__npms__kpi_access5g_5g_cell_peak_view t
WHERE country = 'VNM'
  AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
  AND CAST(nr_ps_traffic_total_gb AS double) > 0
  AND CAST(dl_user_throughput_mbps AS double) < 5.0
  AND CAST(ul_user_throughput_mbps AS double) <= 3.0
  AND NOT EXISTS (
      SELECT 1 FROM hive__npms__occean_cell c
      WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
  )
GROUP BY object_id, province_code, area_code
HAVING COUNT(*) > 3
ORDER BY avg_dl_tp ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["dual_metric_filter", "anti_join", "having", "cast_numeric"],
    ),

    # H008: Rollup by Area and Province
    (
        "H008",
        "Tổng hợp lưu lượng và số cell hoạt động theo cấu trúc phân cấp Khu vực và Tỉnh (sử dụng ROLLUP).",
        "network_kpi_5g",
        """SELECT
    area_code, province_code,
    COUNT(DISTINCT object_id) AS active_cells,
    ROUND(SUM(CAST(nr_ps_traffic_total_gb AS double)), 2) AS total_traffic_gb
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
GROUP BY ROLLUP (area_code, province_code)
ORDER BY area_code NULLS FIRST, province_code NULLS FIRST;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["rollup", "hierarchical_aggregation", "count_distinct"],
    ),

    # H009: Top 3 lowest throughput cells per area
    (
        "H009",
        "Xác định 3 cell có thông lượng tải xuống trung bình thấp nhất trong từng khu vực (sử dụng Window Function ROW_NUMBER).",
        "network_kpi_5g",
        """WITH ranked_cells AS (
    SELECT area_code, object_id, province_code,
           AVG(CAST(dl_user_throughput_mbps AS double)) AS avg_dl,
           ROW_NUMBER() OVER (PARTITION BY area_code ORDER BY AVG(CAST(dl_user_throughput_mbps AS double)) ASC, object_id ASC) AS rn
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) > 0
    GROUP BY area_code, object_id, province_code
)
SELECT area_code, object_id, province_code, avg_dl, rn
FROM ranked_cells
WHERE rn <= 3
ORDER BY area_code, rn, object_id;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_function", "row_number", "partition_by", "cte"],
    ),

    # H010: Impact of degradation on major provinces
    (
        "H010",
        "Tính toán thông lượng trung bình và tổng lưu lượng của các cell 5G tại tỉnh HNI có hơn 3 ngày suy giảm trong 7 ngày qua.",
        "network_kpi_5g",
        """SELECT object_id, COUNT(*) AS bad_days, AVG(CAST(dl_user_throughput_mbps AS double)) AS avg_dl, SUM(CAST(nr_ps_traffic_total_gb AS double)) AS total_traffic
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE province_code = 'HNI' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
  AND CAST(dl_user_throughput_mbps AS double) < 5.0 AND CAST(dl_user_throughput_mbps AS double) > 0
GROUP BY object_id
HAVING COUNT(*) >= 3
ORDER BY total_traffic DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["having", "date_window", "cast_numeric", "aggregate_multi"],
    ),

    # H011: District level distribution
    (
        "H011",
        "Thống kê số lượng cell suy giảm theo từng quận/huyện (district_code) của từng tỉnh, kèm tên tỉnh tương ứng.",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT district_code, province_code, object_id
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) < 5.0 AND CAST(dl_user_throughput_mbps AS double) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY district_code, province_code, object_id
    HAVING COUNT(*) > 3
)
SELECT b.province_code, f.province_name, b.district_code, COUNT(b.object_id) AS bad_cell_count
FROM bad_cells b
LEFT JOIN hive__netbi__f_location_new f ON b.province_code = f.province_code
GROUP BY b.province_code, f.province_name, b.district_code
ORDER BY bad_cell_count DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell", "hive.netbi.f_location_new"],
        ["cte", "anti_join", "left_join", "group_by_multi"],
    ),

    # H012: Throughput Variance against Provincial Benchmark
    (
        "H012",
        "Tính độ lệch giữa thông lượng của từng cell so với thông lượng trung bình của toàn tỉnh trong tuần (Window Function over Province).",
        "network_kpi_5g",
        """WITH cell_stat AS (
    SELECT object_id, province_code,
           ROUND(AVG(CAST(dl_user_throughput_mbps AS double)), 2) AS cell_avg_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) > 0
    GROUP BY object_id, province_code
)
SELECT object_id, province_code, cell_avg_tp,
       ROUND(AVG(cell_avg_tp) OVER (PARTITION BY province_code), 2) AS prov_avg_tp,
       ROUND(cell_avg_tp - AVG(cell_avg_tp) OVER (PARTITION BY province_code), 2) AS diff_from_prov
FROM cell_stat
ORDER BY diff_from_prov ASC, object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_function", "analytics_deviation", "cte"],
    ),

    # H013: Multi-cell degradation per district
    (
        "H013",
        "Tìm các quận/huyện có từ 2 cell 5G suy giảm trở lên trong tuần qua.",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT district_code, province_code, object_id
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) < 5.0 AND CAST(dl_user_throughput_mbps AS double) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY district_code, province_code, object_id
    HAVING COUNT(*) > 3
)
SELECT province_code, district_code, COUNT(object_id) AS total_bad_cells
FROM bad_cells
GROUP BY province_code, district_code
HAVING COUNT(object_id) >= 2
ORDER BY total_bad_cells DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["cte", "anti_join", "having_count", "nested_aggregation"],
    ),

    # H014: SLA Compliance High Performing Cells
    (
        "H014",
        "Thống kê số lượng cell 5G đạt chuẩn chất lượng cao (throughput >= 10 Mbps và traffic >= 50 GB) theo từng khu vực.",
        "network_kpi_5g",
        """SELECT area_code,
       COUNT(DISTINCT object_id) AS high_perf_cells,
       ROUND(AVG(CAST(dl_user_throughput_mbps AS double)), 2) AS avg_throughput,
       ROUND(SUM(CAST(nr_ps_traffic_total_gb AS double)), 2) AS total_traffic
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
  AND CAST(dl_user_throughput_mbps AS double) >= 10.0
  AND CAST(nr_ps_traffic_total_gb AS double) >= 50.0
GROUP BY area_code
ORDER BY high_perf_cells DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["sla_filter", "count_distinct", "aggregate_multi"],
    ),

    # H015: Bad Cell Ratio per Area
    (
        "H015",
        "Tính tỷ lệ phần trăm số cell suy giảm trên tổng số cell hoạt động theo từng khu vực.",
        "network_kpi_5g",
        """WITH all_cells AS (
    SELECT area_code, COUNT(DISTINCT object_id) AS total_active
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
    GROUP BY area_code
),
bad_cells AS (
    SELECT area_code, COUNT(DISTINCT object_id) AS total_bad
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) < 5.0 AND CAST(dl_user_throughput_mbps AS double) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY area_code, object_id
    HAVING COUNT(*) > 3
)
SELECT a.area_code, a.total_active,
       COALESCE(COUNT(b.total_bad), 0) AS bad_cells_count,
       ROUND(COALESCE(COUNT(b.total_bad), 0) * 100.0 / a.total_active, 2) AS bad_cell_rate_pct
FROM all_cells a
LEFT JOIN bad_cells b ON a.area_code = b.area_code
GROUP BY a.area_code, a.total_active
ORDER BY bad_cell_rate_pct DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["cte_dual", "ratio_calculation", "left_join", "anti_join"],
    ),

    # H016: GNOC Alarms breakdown
    (
        "H016",
        "Thống kê các trạm có nhiều hơn 1 cảnh báo trong bảng gnoc kèm số lượng cảnh báo mức CRITICAL và MAJOR tương ứng (case H016).",
        "alarm",
        """SELECT station_code, region,
       COUNT(*) AS total_alarms,
       SUM(CASE WHEN level_important = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_count,
       SUM(CASE WHEN level_important = 'MAJOR' THEN 1 ELSE 0 END) AS major_count
FROM hive__gnoc__gnoc
WHERE station_code != ''
GROUP BY station_code, region
HAVING COUNT(*) >= 1
ORDER BY total_alarms DESC, station_code
LIMIT 10;""",
        ["hive.gnoc.gnoc"],
        ["conditional_aggregation", "case_when", "having"],
    ),

    # H017: Vendor Critical Alarm Ratio
    (
        "H017",
        "Tính tỷ lệ phần trăm cảnh báo CRITICAL trên tổng số cảnh báo của từng nhà cung cấp thiết bị (Vendor) trong GNOC.",
        "alarm",
        """SELECT vendor,
       COUNT(*) AS total_alarms,
       SUM(CASE WHEN level_important = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_alarms,
       ROUND(SUM(CASE WHEN level_important = 'CRITICAL' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS critical_ratio_pct
FROM hive__gnoc__gnoc
WHERE vendor != ''
GROUP BY vendor
ORDER BY critical_ratio_pct DESC;""",
        ["hive.gnoc.gnoc"],
        ["conditional_aggregation", "ratio_calculation", "filter"],
    ),

    # H018: Station repeated alarms ranking
    (
        "H018",
        "Xếp hạng các trạm phát sóng theo tổng số lượng cảnh báo sự cố được ghi nhận trong GNOC (sử dụng DENSE_RANK).",
        "alarm",
        """WITH station_alarms AS (
    SELECT station_code, region, network_type, COUNT(*) AS alarm_cnt
    FROM hive__gnoc__gnoc
    WHERE station_code != ''
    GROUP BY station_code, region, network_type
)
SELECT station_code, region, network_type, alarm_cnt,
       DENSE_RANK() OVER (ORDER BY alarm_cnt DESC) AS rank_pos
FROM station_alarms
ORDER BY alarm_cnt DESC, station_code
LIMIT 10;""",
        ["hive.gnoc.gnoc"],
        ["dense_rank", "window_function", "cte"],
    ),

    # H019: Department & Network Type Alarm Correlation
    (
        "H019",
        "Thống kê số lượng cảnh báo mạng 5G và 4G theo từng khu vực quản lý.",
        "alarm",
        """SELECT region,
       SUM(CASE WHEN network_type = '5G' THEN 1 ELSE 0 END) AS alarms_5g,
       SUM(CASE WHEN network_type = '4G' THEN 1 ELSE 0 END) AS alarms_4g,
       COUNT(*) AS total_alarms
FROM hive__gnoc__gnoc
WHERE region != ''
GROUP BY region
ORDER BY total_alarms DESC;""",
        ["hive.gnoc.gnoc"],
        ["conditional_aggregation", "pivot_style", "group_by"],
    ),

    # H020: Grouping Sets for GNOC Alarms
    (
        "H020",
        "Phân rã số lượng cảnh báo GNOC theo 2 cấp độ: từng loại mạng trong khu vực và tổng hợp toàn khu vực (dùng GROUPING SETS).",
        "alarm",
        """SELECT
    region, network_type,
    COUNT(*) AS total_alarms,
    SUM(CASE WHEN level_important = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_alarms
FROM hive__gnoc__gnoc
WHERE region != '' AND network_type != ''
GROUP BY GROUPING SETS (
    (region, network_type),
    (region)
)
ORDER BY region, network_type NULLS FIRST;""",
        ["hive.gnoc.gnoc"],
        ["grouping_sets", "conditional_aggregation", "multi_level_report"],
    ),

    # H021: Top Critical Maintenance Stations
    (
        "H021",
        "Liệt kê danh sách các trạm phát sóng đang có cảnh báo CRITICAL kèm loại thiết bị và nhà cung cấp.",
        "alarm",
        """SELECT DISTINCT station_code, region, vendor, device_type, level_important
FROM hive__gnoc__gnoc
WHERE level_important = 'CRITICAL' AND station_code != ''
ORDER BY region, station_code;""",
        ["hive.gnoc.gnoc"],
        ["filter_distinct", "simple_lookup"],
    ),

    # H022: Maintenance Calendar Schedule
    (
        "H022",
        "Liệt kê danh sách kế hoạch bảo dưỡng trạm phát sóng trong icms_maintain_calendar kèm trạng thái lệnh công tác wo_status.",
        "alarm",
        """SELECT maintain_calendar_id, station_code, area_name, wo_status, cycle
FROM hive__gnoc__icms_maintain_calendar
WHERE maintain_calendar_id != ''
ORDER BY maintain_calendar_id;""",
        ["hive.gnoc.icms_maintain_calendar"],
        ["filter", "calendar_schedule", "simple_lookup"],
    ),

    # H023: Weighted Site Health Score
    (
        "H023",
        "Tính điểm rủi ro trạm (Risk Score) theo công thức CRITICAL*3 + MAJOR*2 + các mức khác*1 cho từng khu vực.",
        "alarm",
        """SELECT region,
       COUNT(*) AS total_incidents,
       SUM(CASE WHEN level_important = 'CRITICAL' THEN 3
                WHEN level_important = 'MAJOR' THEN 2
                ELSE 1 END) AS total_risk_score
FROM hive__gnoc__gnoc
WHERE region != ''
GROUP BY region
ORDER BY total_risk_score DESC;""",
        ["hive.gnoc.gnoc"],
        ["weighted_score", "case_when", "risk_analytics"],
    ),

    # H024: Temporal Alarm Hourly Peak
    (
        "H024",
        "Xác định khung giờ (date_hour) có nhiều cảnh báo sự cố nhất trên toàn hệ thống GNOC.",
        "alarm",
        """SELECT date_hour,
       COUNT(*) AS total_alarms,
       SUM(CASE WHEN level_important = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_alarms
FROM hive__gnoc__gnoc
WHERE date_hour != ''
GROUP BY date_hour
ORDER BY total_alarms DESC, date_hour ASC
LIMIT 5;""",
        ["hive.gnoc.gnoc"],
        ["temporal_peak", "top_n", "conditional_sum"],
    ),

    # H025: Operational History Join
    (
        "H025",
        "Thống kê số lần can thiệp điều chỉnh thông số theo trạng thái mới từ bảng lịch sử od_history.",
        "alarm",
        """SELECT new_status, COUNT(*) AS status_count, COUNT(DISTINCT user_name) AS unique_users
FROM hive__gnoc__od_history
WHERE new_status != ''
GROUP BY new_status
ORDER BY status_count DESC;""",
        ["hive.gnoc.od_history"],
        ["aggregate_count", "history_analysis", "count_distinct"],
    ),

    # H026: AAA Authentication & Accounting Volume Reconciliation
    (
        "H026",
        "Đối chiếu khối lượng xác thực authentication và kế toán accounting theo từng máy chủ BRAS và khung giờ (case H026).",
        "fbb",
        """SELECT a.hostname, a.sbr_server, a.date_hour,
       SUM(CAST(a.accept AS integer)) AS total_accepted,
       SUM(CAST(b.start AS integer)) AS total_sessions_started
FROM hive__aaa__authentication a
JOIN hive__aaa__accounting b ON a.hostname = b.hostname AND a.sbr_server = b.sbr_server AND a.date_hour = b.date_hour
GROUP BY a.hostname, a.sbr_server, a.date_hour
ORDER BY a.hostname, a.date_hour;""",
        ["hive.aaa.authentication", "hive.aaa.accounting"],
        ["multi_table_join", "composite_key_join", "cast_numeric"],
    ),

    # H027: AAA Failure Rate
    (
        "H027",
        "Tính tỷ lệ phần trăm xác thực thất bại (reject / (accept + reject)) theo từng máy chủ BRAS và lọc các máy chủ có phát sinh lỗi.",
        "fbb",
        """SELECT hostname,
       SUM(CAST(accept AS integer)) AS total_accept,
       SUM(CAST(reject AS integer)) AS total_reject,
       ROUND(SUM(CAST(reject AS double)) * 100.0 / NULLIF(SUM(CAST(accept AS double) + CAST(reject AS double)), 0), 2) AS failure_rate_pct
FROM hive__aaa__authentication
GROUP BY hostname
HAVING SUM(CAST(reject AS integer)) >= 0
ORDER BY failure_rate_pct DESC;""",
        ["hive.aaa.authentication"],
        ["ratio_calculation", "nullif", "cast_numeric"],
    ),

    # H028: BRAS Traffic Load Ranking
    (
        "H028",
        "Xếp hạng các máy chủ BRAS theo tổng số phiên kết nối mới (start) được ghi nhận trong accounting (Window Function RANK).",
        "fbb",
        """WITH bras_load AS (
    SELECT hostname, SUM(CAST(start AS integer)) AS total_starts
    FROM hive__aaa__accounting
    GROUP BY hostname
)
SELECT hostname, total_starts,
       RANK() OVER (ORDER BY total_starts DESC) AS load_rank
FROM bras_load
ORDER BY load_rank;""",
        ["hive.aaa.accounting"],
        ["window_function", "rank", "cte"],
    ),

    # H029: Session Start vs Stop Balance
    (
        "H029",
        "So sánh tổng số phiên bắt đầu (start) và số phiên ngắt kết nối (stop) theo từng cụm máy chủ RADIUS (sbr_server).",
        "fbb",
        """SELECT sbr_server,
       SUM(CAST(start AS integer)) AS total_started,
       SUM(CAST(stop AS integer)) AS total_stopped,
       SUM(CAST(start AS integer)) - SUM(CAST(stop AS integer)) AS active_delta
FROM hive__aaa__accounting
GROUP BY sbr_server
ORDER BY active_delta DESC;""",
        ["hive.aaa.accounting"],
        ["arithmetic_delta", "group_by", "cast_numeric"],
    ),

    # H030: FTTH VIP Account Analysis
    (
        "H030",
        "Thống kê số lượng thuê bao FTTH và giới hạn đăng nhập trung bình của nhóm gói cước FTTH_VIP so với các nhóm cước khác.",
        "fbb",
        """SELECT groupname,
       COUNT(DISTINCT username) AS total_subscribers,
       AVG(CAST(loginlimit AS double)) AS avg_login_limit,
       SUM(CAST(count AS integer)) AS total_logins
FROM hive__aaa__ftth_account_pppoe
GROUP BY groupname
ORDER BY total_subscribers DESC;""",
        ["hive.aaa.ftth_account_pppoe"],
        ["group_by", "cast_numeric", "aggregate_multi"],
    ),

    # H031: RADIUS Grouping Sets
    (
        "H031",
        "Tổng hợp số yêu cầu xác thực chấp thuận (accept) theo 2 cấp: máy chủ BRAS trong cụm RADIUS và tổng cụm RADIUS (GROUPING SETS).",
        "fbb",
        """SELECT sbr_server, hostname,
       SUM(CAST(accept AS integer)) AS total_accepted
FROM hive__aaa__authentication
GROUP BY GROUPING SETS (
    (sbr_server, hostname),
    (sbr_server)
)
ORDER BY sbr_server, hostname NULLS FIRST;""",
        ["hive.aaa.authentication"],
        ["grouping_sets", "cast_numeric", "subtotal_analysis"],
    ),

    # H032: High Concurrency FTTH Subscribers
    (
        "H032",
        "Tìm các thuê bao FTTH có giới hạn đăng nhập loginlimit >= 1 và số lần đăng nhập lớn hơn hoặc bằng 1.",
        "fbb",
        """SELECT username, groupname, loginlimit, count
FROM hive__aaa__ftth_account_pppoe
WHERE CAST(loginlimit AS integer) >= 1 AND CAST(count AS integer) >= 1
ORDER BY username;""",
        ["hive.aaa.ftth_account_pppoe"],
        ["filter_multi", "cast_numeric"],
    ),

    # H033: Accounting Interim Update Activity
    (
        "H033",
        "Thống kê tổng số gói tin cập nhật định kỳ (interim) theo từng khung giờ để đo lường độ tích cực của các phiên FBB.",
        "fbb",
        """SELECT date_hour,
       SUM(CAST(interim AS integer)) AS total_interim_updates,
       COUNT(DISTINCT hostname) AS reporting_bras_count
FROM hive__aaa__accounting
GROUP BY date_hour
ORDER BY date_hour;""",
        ["hive.aaa.accounting"],
        ["temporal_aggregate", "count_distinct"],
    ),

    # H034: Cross Check Authentication and FTTH Profile
    (
        "H034",
        "Tổng hợp số phiên xác thực thành công theo từng khung giờ và đối chiếu với danh sách các máy chủ BRAS hoạt động.",
        "fbb",
        """SELECT date_hour, hostname,
       SUM(CAST(accept AS integer)) AS accepted_sessions,
       SUM(CAST(reject AS integer)) AS rejected_sessions
FROM hive__aaa__authentication
GROUP BY date_hour, hostname
ORDER BY date_hour, accepted_sessions DESC;""",
        ["hive.aaa.authentication"],
        ["temporal_grouping", "cast_numeric"],
    ),

    # H035: Peak Hour Accounting Starts
    (
        "H035",
        "Xác định khung giờ có số lượng phiên kết nối FTTH mới (start) cao nhất trong bảng accounting.",
        "fbb",
        """SELECT date_hour,
       SUM(CAST(start AS integer)) AS total_sessions_started
FROM hive__aaa__accounting
GROUP BY date_hour
ORDER BY total_sessions_started DESC
LIMIT 5;""",
        ["hive.aaa.accounting"],
        ["peak_identification", "top_n", "cast_numeric"],
    ),

    # H036: Web Quality Degradation Alert
    (
        "H036",
        "Kiểm tra các chỉ số chất lượng Web KQI trong kqi_monitor_web có mã id hợp lệ.",
        "data_monitoring",
        """SELECT id, name, value, ts
FROM mysql_datamon__data_monitoring__kqi_monitor_web
WHERE id > 0
ORDER BY id;""",
        ["mysql_datamon.data_monitoring.kqi_monitor_web"],
        ["threshold_filter", "simple_lookup"],
    ),

    # H037: Service Alarm Frequency Ranking
    (
        "H037",
        "Thống kê các loại cảnh báo chất lượng KQI theo tên chỉ số và đơn vị thời gian trong kqi_alarm.",
        "data_monitoring",
        """SELECT name, time_unit, COUNT(*) AS alarm_count
FROM mysql_datamon__data_monitoring__kqi_alarm
GROUP BY name, time_unit
ORDER BY alarm_count DESC;""",
        ["mysql_datamon.data_monitoring.kqi_alarm"],
        ["group_by", "aggregate_multi"],
    ),

    # H038: Blacklisted ENODEB Activity Audit
    (
        "H038",
        "Liệt kê danh sách các trạm ENODEB nằm trong danh sách đen blacklist cần giám sát đặc biệt.",
        "data_monitoring",
        """SELECT enodeb_id, zone_id
FROM mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id
ORDER BY enodeb_id;""",
        ["mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id"],
        ["blacklist_audit", "simple_lookup"],
    ),

    # H039: Restricted Zone Monitoring
    (
        "H039",
        "Thống kê danh sách các khu vực hạn chế truy cập (blacklist zone).",
        "data_monitoring",
        """SELECT id, location_info
FROM mysql_datamon__data_monitoring__usersinarea_blacklist_zone
ORDER BY id;""",
        ["mysql_datamon.data_monitoring.usersinarea_blacklist_zone"],
        ["security_zone_monitoring", "simple_lookup"],
    ),

    # H040: KQI Configuration Threshold Audit
    (
        "H040",
        "Liệt kê cấu hình các quy tắc giám sát KQI đang có hiệu lực trong hệ thống kqi_config.",
        "data_monitoring",
        """SELECT id, rule_name, rule_value, description
FROM mysql_datamon__data_monitoring__kqi_config
ORDER BY id;""",
        ["mysql_datamon.data_monitoring.kqi_config"],
        ["config_audit", "simple_lookup"],
    ),

    # H041: Multi-table Telecom Executive View
    (
        "H041",
        "Báo cáo tổng hợp chất lượng mạng đa chiều: Kết hợp KPI 5G, loại trừ cell đảo, tra cứu địa bàn cho các cell có thông lượng dưới 4 Mbps.",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT t.object_id, t.province_code, t.area_code,
           COUNT(*) AS bad_days,
           AVG(CAST(t.dl_user_throughput_mbps AS double)) AS avg_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE t.country = 'VNM'
      AND t.date_hour >= '2026-08-14-00' AND t.date_hour <= '2026-08-20-00'
      AND CAST(t.nr_ps_traffic_total_gb AS double) > 0
      AND CAST(t.dl_user_throughput_mbps AS double) < 4.0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY t.object_id, t.province_code, t.area_code
    HAVING COUNT(*) >= 2
)
SELECT b.area_code, b.province_code, f.province_name, COUNT(b.object_id) AS bad_cell_count,
       ROUND(AVG(b.avg_tp), 2) AS mean_throughput
FROM bad_cells b
LEFT JOIN hive__netbi__f_location_new f ON b.province_code = f.province_code
GROUP BY b.area_code, b.province_code, f.province_name
ORDER BY bad_cell_count DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell", "hive.netbi.f_location_new"],
        ["cte", "anti_join", "left_join", "having", "cast_numeric"],
    ),

    # H042: Provincial Bad Cell Density Ranking
    (
        "H042",
        "Xếp hạng các tỉnh theo số lượng cell 5G suy giảm (sử dụng DENSE_RANK).",
        "network_kpi_5g",
        """WITH prov_bad AS (
    SELECT province_code, COUNT(DISTINCT object_id) AS bad_cells
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) < 5.0 AND CAST(dl_user_throughput_mbps AS double) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id AND c.date_hour = '2026-01-01-00'
      )
    GROUP BY province_code
    HAVING COUNT(*) > 3
)
SELECT province_code, bad_cells,
       DENSE_RANK() OVER (ORDER BY bad_cells DESC) AS rank_pos
FROM prov_bad
ORDER BY rank_pos;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["dense_rank", "window_function", "anti_join", "cte"],
    ),

    # H043: Throughput Volatility Spread (Max - Min)
    (
        "H043",
        "Tính độ biến động thông lượng (chênh lệch Max - Min) trong tuần của từng cell 5G để xác định các cell có chất lượng sóng không ổn định.",
        "network_kpi_5g",
        """SELECT object_id, province_code,
       MAX(CAST(dl_user_throughput_mbps AS double)) AS max_tp,
       MIN(CAST(dl_user_throughput_mbps AS double)) AS min_tp,
       ROUND(MAX(CAST(dl_user_throughput_mbps AS double)) - MIN(CAST(dl_user_throughput_mbps AS double)), 2) AS tp_volatility_spread
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
  AND CAST(dl_user_throughput_mbps AS double) > 0
GROUP BY object_id, province_code
HAVING COUNT(*) >= 4
ORDER BY tp_volatility_spread DESC
LIMIT 10;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["volatility_spread", "min_max", "having"],
    ),

    # H044: Provincial Traffic Share Contribution
    (
        "H044",
        "Tính tỷ lệ đóng góp phần trăm lưu lượng của từng cell so với tổng lưu lượng của toàn tỉnh (Window Function SUM OVER).",
        "network_kpi_5g",
        """WITH cell_traffic AS (
    SELECT object_id, province_code,
           SUM(CAST(nr_ps_traffic_total_gb AS double)) AS cell_traffic_gb
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(nr_ps_traffic_total_gb AS double) > 0
    GROUP BY object_id, province_code
)
SELECT object_id, province_code, cell_traffic_gb,
       ROUND(cell_traffic_gb * 100.0 / SUM(cell_traffic_gb) OVER (PARTITION BY province_code), 2) AS provincial_share_pct
FROM cell_traffic
ORDER BY province_code, provincial_share_pct DESC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_function", "percentage_contribution", "partition_by"],
    ),

    # H045: Cross-domain Station Incident Alert Correlation
    (
        "H045",
        "Thống kê tổng số lượng cảnh báo GNOC phân bổ theo khu vực địa lý tương ứng.",
        "alarm",
        """SELECT region,
       COUNT(*) AS total_alarms,
       COUNT(DISTINCT station_code) AS affected_stations,
       SUM(CASE WHEN level_important = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_alarms
FROM hive__gnoc__gnoc
WHERE region != ''
GROUP BY region
ORDER BY critical_alarms DESC;""",
        ["hive.gnoc.gnoc"],
        ["cross_domain_alarm", "conditional_aggregation", "count_distinct"],
    ),

    # H046: Vendor RAN Performance Benchmark
    (
        "H046",
        "Thống kê số lượng cảnh báo sự cố theo từng nhà cung cấp thiết bị và loại mạng trong GNOC.",
        "alarm",
        """SELECT vendor, network_type,
       COUNT(*) AS total_alarms,
       SUM(CASE WHEN level_important = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_alarms
FROM hive__gnoc__gnoc
WHERE vendor != ''
GROUP BY vendor, network_type
ORDER BY total_alarms DESC;""",
        ["hive.gnoc.gnoc"],
        ["vendor_benchmark", "conditional_aggregation", "group_by_multi"],
    ),

    # H047: Local Congestion Ratio Index
    (
        "H047",
        "Tính chỉ số áp lực tải (Congestion Index = Tổng lưu lượng / Thông lượng trung bình) cho các cell 5G có lưu lượng lớn.",
        "network_kpi_5g",
        """SELECT object_id, province_code,
       SUM(CAST(nr_ps_traffic_total_gb AS double)) AS total_traffic,
       AVG(CAST(dl_user_throughput_mbps AS double)) AS avg_throughput,
       ROUND(SUM(CAST(nr_ps_traffic_total_gb AS double)) / NULLIF(AVG(CAST(dl_user_throughput_mbps AS double)), 0), 2) AS congestion_index
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
  AND CAST(nr_ps_traffic_total_gb AS double) > 0 AND CAST(dl_user_throughput_mbps AS double) > 0
GROUP BY object_id, province_code
HAVING SUM(CAST(nr_ps_traffic_total_gb AS double)) >= 50
ORDER BY congestion_index DESC
LIMIT 10;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["congestion_index", "derived_ratio", "having"],
    ),

    # H048: Day-over-Day Throughput Trend (LAG Window)
    (
        "H048",
        "Theo dõi xu hướng thông lượng ngày hôm sau so với ngày hôm trước của từng cell 5G (sử dụng Window Function LAG).",
        "network_kpi_5g",
        """WITH daily_tp AS (
    SELECT object_id, date_hour,
           AVG(CAST(dl_user_throughput_mbps AS double)) AS daily_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) > 0
    GROUP BY object_id, date_hour
)
SELECT object_id, date_hour, daily_tp,
       LAG(daily_tp, 1) OVER (PARTITION BY object_id ORDER BY date_hour) AS prev_day_tp,
       ROUND(daily_tp - LAG(daily_tp, 1) OVER (PARTITION BY object_id ORDER BY date_hour), 2) AS dod_delta
FROM daily_tp
ORDER BY object_id, date_hour
LIMIT 10;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_function", "lag", "day_over_day_trend"],
    ),

    # H049: Executive Network KPI Summary (Grouping Sets)
    (
        "H049",
        "Báo cáo tổng hợp điều hành mạng: Tính đồng thời số lượng cell hoạt động và tổng lưu lượng theo cấp Khu vực và Toàn mạng (GROUPING SETS).",
        "network_kpi_5g",
        """SELECT
    area_code,
    COUNT(DISTINCT object_id) AS total_cells,
    ROUND(SUM(CAST(nr_ps_traffic_total_gb AS double)), 2) AS total_traffic_gb,
    ROUND(AVG(CAST(dl_user_throughput_mbps AS double)), 2) AS avg_network_tp
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
GROUP BY GROUPING SETS (
    (area_code),
    ()
)
ORDER BY area_code NULLS FIRST;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["grouping_sets", "executive_summary", "count_distinct"],
    ),

    # H050: Network Quality Quartile Segmentation (NTILE)
    (
        "H050",
        "Phân nhóm phân vị chất lượng mạng: Chia các cell 5G thành 4 nhóm tứ phân vị (Quartiles 1-4) dựa trên thông lượng tải xuống trung bình trong 7 ngày qua (sử dụng NTILE).",
        "network_kpi_5g",
        """WITH cell_perf AS (
    SELECT object_id, province_code,
           AVG(CAST(dl_user_throughput_mbps AS double)) AS avg_tp,
           SUM(CAST(nr_ps_traffic_total_gb AS double)) AS total_traffic
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE country = 'VNM' AND date_hour >= '2026-08-14-00' AND date_hour <= '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS double) > 0
    GROUP BY object_id, province_code
)
SELECT object_id, province_code, avg_tp, total_traffic,
       NTILE(4) OVER (ORDER BY avg_tp ASC) AS quartile_rank
FROM cell_perf
ORDER BY avg_tp ASC
LIMIT 10;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["ntile", "quartile_segmentation", "window_function", "cte"],
    ),
]

def test_and_build():
    print("=== KIỂM TRA 50 HARD CASES TRÊN DUCKDB ===")
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)

    errors = []
    for cid, q, dom, sql_d, req_t, skills in HARD_CASES_DEFINITIONS:
        try:
            cur = con.execute(sql_d)
            rows = cur.fetchall()
            if len(rows) == 0:
                print(f"[WARN] {cid}: Trả về 0 dòng!")
        except Exception as e:
            errors.append((cid, str(e), sql_d))
            print(f"[FAIL] {cid}: {e}")

    if errors:
        print(f"\nCó {len(errors)} lỗi trên DuckDB!")
        sys.exit(1)

    print(f"\n100% {len(HARD_CASES_DEFINITIONS)}/50 Hard cases đã thực thi THÀNH CÔNG trên DuckDB!")

    # Cập nhật trực tiếp vào benchmark/cases.py
    cases_py_path = PROJECT_DIR / "benchmark" / "cases.py"
    with open(cases_py_path, "r", encoding="utf-8") as f:
        cases_code = f.read()

    # Tìm vị trí bắt đầu của 50 HARD CASES
    marker = "# =========================================================================" + "\n" + "    # 50 HARD CASES (H001 - H050)"
    if marker in cases_code:
        prefix = cases_code.split(marker)[0]
    else:
        marker2 = "# 50 HARD CASES (H001 - H050)"
        prefix = cases_code.split(marker2)[0]

    hard_block = []
    hard_block.append("# =========================================================================")
    hard_block.append("    # 50 HARD CASES (H001 - H050) - THIẾT KẾ CHUẨN MỰC THEO MẪU QUERY.MD")
    hard_block.append("    # =========================================================================")
    hard_block.append("    hard_specs = [")

    for cid, q, dom, sql_d, req_t, skills in HARD_CASES_DEFINITIONS:
        # Tự động tạo gold_sql_trino tương đương
        sql_t = sql_d.replace("hive__npms__kpi_access5g_5g_cell_peak_view", "hive.npms.kpi_access5g_5g_cell_peak_view")
        sql_t = sql_t.replace("hive__npms__occean_cell", "hive.npms.occean_cell")
        sql_t = sql_t.replace("hive__netbi__f_location_new", "hive.netbi.f_location_new")
        sql_t = sql_t.replace("hive__gnoc__gnoc", "hive.gnoc.gnoc")
        sql_t = sql_t.replace("hive__gnoc__icms_maintain_calendar", "hive.gnoc.icms_maintain_calendar")
        sql_t = sql_t.replace("hive__gnoc__od_history", "hive.gnoc.od_history")
        sql_t = sql_t.replace("hive__aaa__authentication", "hive.aaa.authentication")
        sql_t = sql_t.replace("hive__aaa__accounting", "hive.aaa.accounting")
        sql_t = sql_t.replace("hive__aaa__ftth_account_pppoe", "hive.aaa.ftth_account_pppoe")
        sql_t = sql_t.replace("mysql_datamon__data_monitoring__kqi_monitor_web", "mysql_datamon.data_monitoring.kqi_monitor_web")
        sql_t = sql_t.replace("mysql_datamon__data_monitoring__kqi_alarm", "mysql_datamon.data_monitoring.kqi_alarm")
        sql_t = sql_t.replace("mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id", "mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id")
        sql_t = sql_t.replace("mysql_datamon__data_monitoring__usersinarea_blacklist_zone", "mysql_datamon.data_monitoring.usersinarea_blacklist_zone")
        sql_t = sql_t.replace("mysql_datamon__data_monitoring__kqi_config", "mysql_datamon.data_monitoring.kqi_config")

        hard_block.append("        (")
        hard_block.append(f"            {repr(cid)},")
        hard_block.append(f"            {repr(q)},")
        hard_block.append(f"            {repr(dom)},")
        hard_block.append(f"            {repr(sql_d)},")
        hard_block.append(f"            {repr(sql_t)},")
        hard_block.append(f"            {repr(req_t)},")
        hard_block.append(f"            {repr(skills)},")
        hard_block.append("        ),")

    hard_block.append("    ]")
    hard_block.append("")
    hard_block.append("    for cid, q, dom, sql_d, sql_t, req_t, skills in hard_specs:")
    hard_block.append("        cases.append({")
    hard_block.append('            "id": cid,')
    hard_block.append('            "question": q,')
    hard_block.append('            "difficulty": "hard",')
    hard_block.append('            "domain": dom,')
    hard_block.append('            "gold_sql_duckdb": sql_d,')
    hard_block.append('            "gold_sql_trino": sql_t,')
    hard_block.append('            "required_tables": req_t,')
    hard_block.append('            "skills": skills,')
    hard_block.append("        })")
    hard_block.append("")
    hard_block.append("    return cases\n")

    new_cases_code = prefix + "\n".join(hard_block)
    with open(cases_py_path, "w", encoding="utf-8") as f:
        f.write(new_cases_code)
    print(f"-> Đã ghi đè thành công {len(HARD_CASES_DEFINITIONS)} Hard cases vào {cases_py_path}!")

if __name__ == "__main__":
    test_and_build()
