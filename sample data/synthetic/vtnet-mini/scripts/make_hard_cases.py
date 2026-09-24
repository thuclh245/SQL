import sys
from pathlib import Path
import duckdb

PROJECT_DIR = Path(__file__).resolve().parents[1]
DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"
OUT_FILE = PROJECT_DIR / "benchmark" / "hard_cases_data.py"

HARD_CASES = [
    # -------------------------------------------------------------------------
    # NHÓM 1: TEMPORAL / WINDOW / DATE BOUNDARY (8 cases: H001 - H008)
    # -------------------------------------------------------------------------
    (
        "H001",
        "Tính số lượng cell 5G suy giảm thông lượng (bad cell) trong cửa sổ 7 ngày kết thúc ngày 2026-08-20, loại trừ occean_cell và phân rã 3 cấp địa lý (province, area, network) bằng GROUPING SETS (Production Query Variant 1).",
        "network_kpi_5g",
        """WITH raw_data AS (
    SELECT
        '2026-08-20-00' AS date_hour,
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
LEFT JOIN (SELECT DISTINCT province_code, province_name FROM hive__netbi__f_location_new) f
    ON r.province_code = f.province_code
ORDER BY location_level, r.area_name, r.province_code;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell", "hive.netbi.f_location_new"],
        ["rolling_window", "grouping_sets", "anti_join", "cte", "left_join"],
    ),
    (
        "H002",
        "Tìm danh sách các cell 5G có chuỗi ít nhất 3 ngày liên tiếp (streak >= 3) bị suy giảm thông lượng (dl_user_throughput_mbps < 4 Mbps và traffic > 0) trong cửa sổ 7 ngày kết thúc ngày 2026-08-20.",
        "network_kpi_5g",
        """WITH daily_status AS (
    SELECT
        object_id,
        date,
        CAST(dl_user_throughput_mbps AS DOUBLE) AS tp,
        LAG(CAST(dl_user_throughput_mbps AS DOUBLE), 1) OVER (PARTITION BY object_id ORDER BY date) AS lag1_tp,
        LAG(CAST(dl_user_throughput_mbps AS DOUBLE), 2) OVER (PARTITION BY object_id ORDER BY date) AS lag2_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
      AND CAST(nr_ps_traffic_total_gb AS DOUBLE) > 0
)
SELECT DISTINCT object_id
FROM daily_status
WHERE tp < 4.0 AND lag1_tp < 4.0 AND lag2_tp < 4.0
ORDER BY object_id;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_lag", "streak_detection", "temporal"],
    ),
    (
        "H003",
        "So sánh thông lượng tải xuống trung bình 3 ngày đầu tuần (2026-08-14 đến 2026-08-16) so với 3 ngày cuối tuần (2026-08-18 đến 2026-08-20) của từng cell 5G; lọc các cell có mức tăng trưởng thông lượng vượt bậc (>= 10 Mbps).",
        "network_kpi_5g",
        """WITH early_week AS (
    SELECT object_id, AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS avg_early
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date BETWEEN '2026-08-14' AND '2026-08-16'
    GROUP BY object_id
),
late_week AS (
    SELECT object_id, AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS avg_late
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date BETWEEN '2026-08-18' AND '2026-08-20'
    GROUP BY object_id
    HAVING AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) >= 15.0
)
SELECT
    l.object_id,
    ROUND(e.avg_early, 2) AS early_tp,
    ROUND(l.avg_late, 2) AS late_tp,
    ROUND(l.avg_late - COALESCE(e.avg_early, 0.0), 2) AS tp_gain
FROM late_week l
INNER JOIN early_week e ON l.object_id = e.object_id
ORDER BY tp_gain DESC, l.object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["temporal_comparison", "cte", "metric_growth"],
    ),
    (
        "H004",
        "Xác định các sự cố cảnh báo trong gnoc đang diễn ra hoặc chưa đóng (uptime_date IS NULL) tính đến ngày 2026-08-20 kèm mã trạm và mức độ quan trọng.",
        "alarm",
        """SELECT
    schedule_id,
    station_code,
    level_important,
    vendor,
    date_hour
FROM hive__gnoc__gnoc
WHERE uptime_date IS NULL
  AND date_hour <= '2026-08-20-10'
ORDER BY schedule_id;""",
        ["hive.gnoc.gnoc"],
        ["null_handling", "temporal_filtering", "alarm_lifecycle"],
    ),
    (
        "H005",
        "Thống kê số lượng cảnh báo sự cố GNOC xảy ra tại thời khắc chuyển ngày (khung giờ từ 23:00 ngày 2026-08-19 đến 01:00 ngày 2026-08-20) theo từng mức độ nghiêm trọng.",
        "alarm",
        """SELECT
    level_important,
    COUNT(*) AS alarm_count
FROM hive__gnoc__gnoc
WHERE date_hour IN ('2026-08-19-23', '2026-08-20-00', '2026-08-20-01')
GROUP BY level_important
ORDER BY alarm_count DESC, level_important ASC;""",
        ["hive.gnoc.gnoc"],
        ["date_boundary", "group_by", "aggregation"],
    ),
    (
        "H006",
        "So sánh thông lượng tải xuống trung bình 3 ngày gần nhất (2026-08-18 đến 2026-08-20) so với trung bình cả tuần (7 ngày) của từng cell 5G; lọc các cell có độ lệch thông lượng từ 5 Mbps trở lên.",
        "network_kpi_5g",
        """WITH week_avg AS (
    SELECT object_id, AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS avg_7d
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
    GROUP BY object_id
    HAVING AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) >= 10.0
),
last3_avg AS (
    SELECT object_id, AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS avg_3d
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date BETWEEN '2026-08-18' AND '2026-08-20'
    GROUP BY object_id
)
SELECT
    w.object_id,
    ROUND(w.avg_7d, 2) AS weekly_avg,
    ROUND(l.avg_3d, 2) AS last3_avg,
    ROUND(ABS(w.avg_7d - COALESCE(l.avg_3d, 0.0)), 2) AS tp_diff
FROM week_avg w
INNER JOIN last3_avg l ON w.object_id = l.object_id
ORDER BY tp_diff DESC, w.object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["multi_window", "cte", "metric_deviation"],
    ),
    (
        "H007",
        "Tìm các máy chủ BRAS có hoạt động kế toán accounting liên tục trong khung giờ cao điểm từ 08:00 đến 12:00 ngày 2026-08-20 kèm tổng số phiên bắt đầu.",
        "fbb",
        """SELECT
    hostname,
    sbr_server,
    COUNT(DISTINCT date_hour) AS active_hours,
    SUM(CAST(start AS BIGINT)) AS total_started
FROM hive__aaa__accounting
WHERE date_hour >= '2026-08-20-08'
  AND date_hour <= '2026-08-20-12'
GROUP BY hostname, sbr_server
ORDER BY total_started DESC, hostname ASC;""",
        ["hive.aaa.accounting"],
        ["session_boundary", "group_by", "aggregation"],
    ),
    (
        "H008",
        "So sánh tổng lưu lượng 5G giữa 4 ngày đầu tuần (2026-08-14 đến 2026-08-17) và 3 ngày cuối tuần (2026-08-18 đến 2026-08-20) theo từng khu vực (area_code).",
        "network_kpi_5g",
        """SELECT
    area_code,
    ROUND(SUM(CASE WHEN date BETWEEN '2026-08-14' AND '2026-08-17' THEN CAST(nr_ps_traffic_total_gb AS DOUBLE) ELSE 0 END), 2) AS early_week_traffic,
    ROUND(SUM(CASE WHEN date BETWEEN '2026-08-18' AND '2026-08-20' THEN CAST(nr_ps_traffic_total_gb AS DOUBLE) ELSE 0 END), 2) AS late_week_traffic
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
GROUP BY area_code
ORDER BY area_code;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["conditional_aggregation", "temporal_split", "group_by"],
    ),

    # -------------------------------------------------------------------------
    # NHÓM 2: MULTI-JOIN & GRAIN/FANOUT PREVENTION (8 cases: H009 - H016)
    # -------------------------------------------------------------------------
    (
        "H009",
        "Thống kê tổng số lượng cảnh báo sự cố GNOC và tổng số lệnh bảo dưỡng ICMS của từng trạm phát sóng (station_code) trong tuần, tránh nhân bản bản ghi giữa 2 bảng bằng cách gom nhóm CTE trước khi JOIN.",
        "alarm",
        """WITH alarm_stat AS (
    SELECT station_code, COUNT(schedule_id) AS alarm_count
    FROM hive__gnoc__gnoc
    GROUP BY station_code
),
maintain_stat AS (
    SELECT station_code, COUNT(maintain_calendar_id) AS maintain_count
    FROM hive__gnoc__icms_maintain_calendar
    GROUP BY station_code
)
SELECT
    COALESCE(a.station_code, m.station_code) AS station_code,
    COALESCE(a.alarm_count, 0) AS alarm_count,
    COALESCE(m.maintain_count, 0) AS maintain_count
FROM alarm_stat a
FULL OUTER JOIN maintain_stat m ON a.station_code = m.station_code
WHERE COALESCE(a.station_code, m.station_code) != ''
ORDER BY station_code;""",
        ["hive.gnoc.gnoc", "hive.gnoc.icms_maintain_calendar"],
        ["fanout_prevention", "cte_aggregation", "full_outer_join"],
    ),
    (
        "H010",
        "Đối soát khối lượng xác thực (Authentication) và phiên kế toán (Accounting) theo từng máy chủ BRAS (hostname): tính tổng số yêu cầu xác thực chấp thuận (accept) và tổng số phiên bắt đầu (start) mà không nhân bản chéo.",
        "fbb",
        """WITH auth_agg AS (
    SELECT hostname, SUM(CAST(accept AS BIGINT)) AS total_accept
    FROM hive__aaa__authentication
    GROUP BY hostname
),
acct_agg AS (
    SELECT hostname, SUM(CAST(start AS BIGINT)) AS total_start
    FROM hive__aaa__accounting
    GROUP BY hostname
)
SELECT
    COALESCE(au.hostname, ac.hostname) AS hostname,
    COALESCE(au.total_accept, 0) AS total_accept,
    COALESCE(ac.total_start, 0) AS total_start
FROM auth_agg au
FULL OUTER JOIN acct_agg ac ON au.hostname = ac.hostname
ORDER BY hostname;""",
        ["hive.aaa.authentication", "hive.aaa.accounting"],
        ["fanout_prevention", "cte_aggregation", "reconciliation"],
    ),
    (
        "H011",
        "Báo cáo tích hợp chất lượng 4G và 5G cấp tỉnh trong tuần: Tính đồng thời thông lượng 4G trung bình và số cell 5G hoạt động của từng tỉnh mà không tạo tích Đề-các.",
        "network_kpi_5g",
        """WITH kpi_4g AS (
    SELECT province_code, ROUND(AVG(CAST(dl_cell_throughput_mbps AS DOUBLE)), 2) AS avg_4g_tp
    FROM hive__npms__kpi_access4g_all_day_normal
    GROUP BY province_code
),
kpi_5g AS (
    SELECT province_code, COUNT(DISTINCT object_id) AS cell_5g_count
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    GROUP BY province_code
)
SELECT
    l.province_code,
    l.province_name,
    COALESCE(g4.avg_4g_tp, 0.0) AS avg_4g_tp,
    COALESCE(g5.cell_5g_count, 0) AS cell_5g_count
FROM (SELECT DISTINCT province_code, province_name FROM hive__netbi__f_location_new) l
LEFT JOIN kpi_4g g4 ON l.province_code = g4.province_code
LEFT JOIN kpi_5g g5 ON l.province_code = g5.province_code
WHERE g4.avg_4g_tp IS NOT NULL OR g5.cell_5g_count IS NOT NULL
ORDER BY l.province_code;""",
        ["hive.npms.kpi_access4g_all_day_normal", "hive.npms.kpi_access5g_5g_cell_peak_view", "hive.netbi.f_location_new"],
        ["fanout_prevention", "multi_domain", "cte_aggregation"],
    ),
    (
        "H012",
        "Thống kê khối lượng công việc của từng phòng ban GNOC: Số lượng cảnh báo thuộc địa bàn quản lý và số lượt điều chỉnh thông số trong od_history.",
        "alarm",
        """WITH alarm_agg AS (
    SELECT region, COUNT(*) AS alarm_count
    FROM hive__gnoc__gnoc
    GROUP BY region
),
od_agg AS (
    SELECT COUNT(*) AS total_od_actions
    FROM hive__gnoc__od_history
)
SELECT
    d.dept_code,
    d.dept_name,
    COALESCE(a.alarm_count, 0) AS alarm_count,
    od.total_od_actions
FROM hive__gnoc__cat_department d
LEFT JOIN alarm_agg a ON d.location_id = a.region
CROSS JOIN od_agg od
WHERE d.dept_code != ''
ORDER BY d.dept_code;""",
        ["hive.gnoc.cat_department", "hive.gnoc.gnoc", "hive.gnoc.od_history"],
        ["cte_aggregation", "left_join", "cross_join", "fanout_prevention"],
    ),
    (
        "H013",
        "Báo cáo giám sát sự cố cấp Quận/Huyện: Đếm số lượng cell 5G hoạt động theo từng district_code có từ 2 cell trở lên.",
        "network_kpi_5g",
        """SELECT
    district_code,
    COUNT(DISTINCT object_id) AS cell_count
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE district_code != ''
GROUP BY district_code
HAVING COUNT(DISTINCT object_id) >= 2
ORDER BY cell_count DESC, district_code ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["district_level", "having", "count_distinct"],
    ),
    (
        "H014",
        "Đánh giá sức khỏe nhóm thuê bao FTTH: Tính tổng số tài khoản, tổng số lần kết nối và giới hạn đăng nhập trung bình theo từng nhóm cước (groupname).",
        "fbb",
        """SELECT
    groupname,
    COUNT(username) AS total_users,
    SUM(count) AS total_connections,
    ROUND(AVG(CAST(loginlimit AS DOUBLE)), 2) AS avg_login_limit
FROM hive__aaa__ftth_account_pppoe
GROUP BY groupname
ORDER BY total_users DESC;""",
        ["hive.aaa.ftth_account_pppoe"],
        ["group_by", "aggregation", "multi_metric"],
    ),
    (
        "H015",
        "Báo cáo giám sát trạm vi phạm Blacklist: Với mỗi trạm trong danh sách đen, đếm số vùng blacklist liên quan và số cảnh báo CRITICAL phát sinh.",
        "data_monitoring",
        """WITH bl_agg AS (
    SELECT enodeb_id, COUNT(DISTINCT zone_id) AS zone_count
    FROM mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id
    GROUP BY enodeb_id
),
alarm_agg AS (
    SELECT station_code, COUNT(*) AS crit_alarm_count
    FROM hive__gnoc__gnoc
    WHERE level_important = 'CRITICAL'
    GROUP BY station_code
)
SELECT
    b.enodeb_id,
    b.zone_count,
    COALESCE(a.crit_alarm_count, 0) AS crit_alarm_count
FROM bl_agg b
LEFT JOIN alarm_agg a ON CAST(b.enodeb_id AS VARCHAR) = SUBSTR(a.station_code, -4)
ORDER BY b.enodeb_id;""",
        ["mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id", "hive.gnoc.gnoc"],
        ["fanout_prevention", "cte_aggregation", "left_join"],
    ),
    (
        "H016",
        "Đối soát thiết bị theo Vendor: Tính tổng số trạm phát sóng có cảnh báo và tổng số cảnh báo tương ứng của từng Vendor.",
        "alarm",
        """SELECT
    vendor,
    COUNT(DISTINCT station_code) AS stations_with_alarms,
    COUNT(*) AS total_alarms
FROM hive__gnoc__gnoc
GROUP BY vendor
ORDER BY total_alarms DESC;""",
        ["hive.gnoc.gnoc"],
        ["vendor_audit", "group_by", "count_distinct"],
    ),

    # -------------------------------------------------------------------------
    # NHÓM 3: ANTI-JOIN / EXCLUSION (6 cases: H017 - H022)
    # -------------------------------------------------------------------------
    (
        "H017",
        "Liệt kê các cell 5G suy giảm thông lượng (throughput < 5 Mbps và traffic > 0 trong > 3 ngày) và bắt buộc KHÔNG nằm trong danh sách cell biển/đảo occean_cell (sử dụng NOT EXISTS) (Production Query Variant 2).",
        "network_kpi_5g",
        """SELECT
    t.object_id,
    COUNT(*) AS bad_days,
    ROUND(AVG(CAST(t.dl_user_throughput_mbps AS DOUBLE)), 2) AS avg_tp
FROM hive__npms__kpi_access5g_5g_cell_peak_view t
WHERE t.country = 'VNM'
  AND t.date_hour >= '2026-08-14-00'
  AND t.date_hour <= '2026-08-20-00'
  AND CAST(t.nr_ps_traffic_total_gb AS DOUBLE) > 0
  AND CAST(t.dl_user_throughput_mbps AS DOUBLE) < 5.0
  AND CAST(t.dl_user_throughput_mbps AS DOUBLE) > 0
  AND NOT EXISTS (
      SELECT 1
      FROM hive__npms__occean_cell c
      WHERE c.object_id = t.object_id
        AND c.date_hour = '2026-01-01-00'
  )
GROUP BY t.object_id
HAVING COUNT(*) > 3
ORDER BY avg_tp ASC, t.object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["anti_join", "not_exists", "exclusion"],
    ),
    (
        "H018",
        "Tìm các tỉnh thành trong danh mục địa bàn f_location_new nhưng KHÔNG có bất kỳ cell 5G nào trong bảng KPI (Anti-Join giữa location và KPI).",
        "common_location",
        """SELECT DISTINCT l.province_code, l.province_name
FROM hive__netbi__f_location_new l
WHERE NOT EXISTS (
    SELECT 1
    FROM hive__npms__kpi_access5g_5g_cell_peak_view k
    WHERE k.province_code = l.province_code
)
ORDER BY l.province_code;""",
        ["hive.netbi.f_location_new", "hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["anti_join", "not_exists", "silent_entities"],
    ),
    (
        "H019",
        "Tìm danh sách các máy chủ BRAS (hostname) có phát sinh yêu cầu xác thực nhưng KHÔNG có bất kỳ bản ghi từ chối nào (reject = '0' hoàn hảo) trong toàn bộ dữ liệu authentication.",
        "fbb",
        """SELECT DISTINCT a.hostname
FROM hive__aaa__authentication a
WHERE NOT EXISTS (
    SELECT 1
    FROM hive__aaa__authentication bad
    WHERE bad.hostname = a.hostname
      AND CAST(bad.reject AS INT) > 0
)
ORDER BY a.hostname;""",
        ["hive.aaa.authentication"],
        ["anti_join", "zero_error_servers", "not_exists"],
    ),
    (
        "H020",
        "Tìm các cell 5G trong kpi_access5g_5g_cell_peak_view có lưu lượng lớn hơn 10 GB nhưng KHÔNG nằm trong danh sách loại trừ occean_cell.",
        "network_kpi_5g",
        """SELECT DISTINCT t.object_id, t.province_code
FROM hive__npms__kpi_access5g_5g_cell_peak_view t
WHERE CAST(t.nr_ps_traffic_total_gb AS DOUBLE) > 10.0
  AND NOT EXISTS (
      SELECT 1
      FROM hive__npms__occean_cell o
      WHERE o.object_id = t.object_id
  )
ORDER BY t.object_id
LIMIT 10;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell"],
        ["anti_join", "not_exists", "traffic_filter"],
    ),
    (
        "H021",
        "Tìm các máy chủ BRAS (hostname) có xuất hiện trong bảng authentication nhưng KHÔNG hề có bản ghi phiên nào trong bảng accounting (Anti-Join).",
        "fbb",
        """SELECT DISTINCT au.hostname
FROM hive__aaa__authentication au
WHERE NOT EXISTS (
    SELECT 1
    FROM hive__aaa__accounting ac
    WHERE ac.hostname = au.hostname
)
ORDER BY au.hostname;""",
        ["hive.aaa.authentication", "hive.aaa.accounting"],
        ["anti_join", "not_exists", "data_gap"],
    ),
    (
        "H022",
        "Tìm các trạm nằm trong danh sách đen blacklist_enodeb_id nhưng KHÔNG có bất kỳ cảnh báo mức CRITICAL nào trong bảng gnoc.",
        "data_monitoring",
        """SELECT DISTINCT b.enodeb_id
FROM mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id b
WHERE NOT EXISTS (
    SELECT 1
    FROM hive__gnoc__gnoc g
    WHERE g.level_important = 'CRITICAL'
      AND SUBSTR(g.station_code, -4) = CAST(b.enodeb_id AS VARCHAR)
)
ORDER BY b.enodeb_id;""",
        ["mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id", "hive.gnoc.gnoc"],
        ["anti_join", "not_exists", "blacklist_cross"],
    ),

    # -------------------------------------------------------------------------
    # NHÓM 4: WINDOW FUNCTION / TOP-N / STREAK (6 cases: H023 - H028)
    # -------------------------------------------------------------------------
    (
        "H023",
        "Xác định Top-3 cell 5G có thông lượng tải xuống trung bình thấp nhất trong từng tỉnh (sử dụng Window Function ROW_NUMBER).",
        "network_kpi_5g",
        """WITH cell_summary AS (
    SELECT
        province_code,
        object_id,
        ROUND(AVG(CAST(dl_user_throughput_mbps AS DOUBLE)), 2) AS avg_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour BETWEEN '2026-08-14-00' AND '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0
    GROUP BY province_code, object_id
),
ranked_cells AS (
    SELECT
        province_code,
        object_id,
        avg_tp,
        ROW_NUMBER() OVER (PARTITION BY province_code ORDER BY avg_tp ASC, object_id ASC) AS rank_in_province
    FROM cell_summary
)
SELECT province_code, object_id, avg_tp, rank_in_province
FROM ranked_cells
WHERE rank_in_province <= 3
ORDER BY province_code, rank_in_province;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_row_number", "top_n", "partition_by"],
    ),
    (
        "H024",
        "Xếp hạng các máy chủ BRAS theo tổng số lượt xác thực chấp thuận (accept) sử dụng DENSE_RANK.",
        "fbb",
        """WITH bras_stats AS (
    SELECT
        hostname,
        SUM(CAST(accept AS BIGINT)) AS total_accept
    FROM hive__aaa__authentication
    GROUP BY hostname
)
SELECT
    hostname,
    total_accept,
    DENSE_RANK() OVER (ORDER BY total_accept DESC) AS bras_rank
FROM bras_stats
ORDER BY bras_rank, hostname;""",
        ["hive.aaa.authentication"],
        ["window_dense_rank", "ranking"],
    ),
    (
        "H025",
        "Theo dõi xu hướng chất lượng cell 5G: Tính chênh lệch thông lượng tải xuống giữa ngày hiện tại và ngày liền trước (sử dụng LAG).",
        "network_kpi_5g",
        """WITH cell_daily AS (
    SELECT
        object_id,
        date,
        CAST(dl_user_throughput_mbps AS DOUBLE) AS dl_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE object_id LIKE 'CELL_5G_A%'
)
SELECT
    object_id,
    date,
    dl_tp,
    LAG(dl_tp, 1) OVER (PARTITION BY object_id ORDER BY date) AS prev_day_tp,
    ROUND(dl_tp - LAG(dl_tp, 1) OVER (PARTITION BY object_id ORDER BY date), 2) AS daily_diff
FROM cell_daily
ORDER BY object_id, date;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_lag", "trend_analysis"],
    ),
    (
        "H026",
        "Tính lũy kế số lượng cảnh báo sự cố theo từng ngày trong tuần cho từng khu vực (sử dụng SUM OVER ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW).",
        "alarm",
        """WITH daily_alarms AS (
    SELECT
        region,
        SUBSTR(date_hour, 1, 10) AS dt,
        COUNT(*) AS alarm_cnt
    FROM hive__gnoc__gnoc
    GROUP BY region, SUBSTR(date_hour, 1, 10)
)
SELECT
    region,
    dt,
    alarm_cnt,
    SUM(alarm_cnt) OVER (PARTITION BY region ORDER BY dt ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_alarms
FROM daily_alarms
ORDER BY region, dt;""",
        ["hive.gnoc.gnoc"],
        ["window_running_total", "cumulative_sum"],
    ),
    (
        "H027",
        "Phân chia các cell 5G thành 4 nhóm tứ phân vị chất lượng (Quartiles 1-4) dựa trên thông lượng tải xuống trung bình sử dụng hàm NTILE(4).",
        "network_kpi_5g",
        """WITH cell_perf AS (
    SELECT
        object_id,
        ROUND(AVG(CAST(dl_user_throughput_mbps AS DOUBLE)), 2) AS avg_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour BETWEEN '2026-08-14-00' AND '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0
    GROUP BY object_id
)
SELECT
    object_id,
    avg_tp,
    NTILE(4) OVER (ORDER BY avg_tp ASC) AS quality_quartile
FROM cell_perf
ORDER BY avg_tp ASC, object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_ntile", "quartile_segmentation"],
    ),
    (
        "H028",
        "Tính tỷ lệ phần trăm đóng góp lưu lượng của từng cell 5G so với tổng lưu lượng toàn tỉnh sử dụng Window Function SUM OVER.",
        "network_kpi_5g",
        """WITH cell_vol AS (
    SELECT
        province_code,
        object_id,
        ROUND(SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)), 2) AS total_traffic
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour = '2026-08-20-00'
      AND province_code IN ('HNI', 'HCM')
    GROUP BY province_code, object_id
)
SELECT
    province_code,
    object_id,
    total_traffic,
    ROUND(total_traffic * 100.0 / SUM(total_traffic) OVER (PARTITION BY province_code), 2) AS traffic_share_pct
FROM cell_vol
ORDER BY province_code, traffic_share_pct DESC, object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["window_sum_over", "share_percentage"],
    ),

    # -------------------------------------------------------------------------
    # NHÓM 5: MULTI-STAGE AGGREGATION (6 cases: H029 - H034)
    # -------------------------------------------------------------------------
    (
        "H029",
        "Tổng hợp 3 tầng: Tính thông lượng trung bình từng ngày của cell -> lọc các cell có trên 3 ngày suy giảm -> tính tỷ lệ cell suy giảm trên tổng số cell hoạt động theo từng tỉnh.",
        "network_kpi_5g",
        """WITH cell_bad_days AS (
    SELECT
        province_code,
        object_id,
        COUNT(*) AS bad_day_count
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) < 5.0
      AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0
    GROUP BY province_code, object_id
),
prov_active AS (
    SELECT province_code, COUNT(DISTINCT object_id) AS active_cells
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    GROUP BY province_code
),
prov_bad AS (
    SELECT province_code, COUNT(DISTINCT object_id) AS bad_cells
    FROM cell_bad_days
    WHERE bad_day_count > 3
    GROUP BY province_code
)
SELECT
    a.province_code,
    a.active_cells,
    COALESCE(b.bad_cells, 0) AS bad_cells,
    ROUND(COALESCE(b.bad_cells, 0) * 100.0 / a.active_cells, 2) AS bad_cell_ratio_pct
FROM prov_active a
LEFT JOIN prov_bad b ON a.province_code = b.province_code
ORDER BY bad_cell_ratio_pct DESC, a.province_code ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["multi_stage_aggregation", "ratio_calculation", "hierarchical_filter"],
    ),
    (
        "H030",
        "Lọc ngưỡng 2 cấp: Tính tổng số phiên kế toán theo từng máy chủ và khung giờ -> lọc các khung giờ cao điểm có tổng phiên > 150 -> tính trung bình số phiên cao điểm theo máy chủ.",
        "fbb",
        """WITH hourly_traffic AS (
    SELECT
        hostname,
        date_hour,
        SUM(CAST(start AS BIGINT)) AS hr_start
    FROM hive__aaa__accounting
    GROUP BY hostname, date_hour
),
filtered_peak AS (
    SELECT hostname, date_hour, hr_start
    FROM hourly_traffic
    WHERE hr_start > 150
)
SELECT
    hostname,
    COUNT(date_hour) AS peak_hours_count,
    ROUND(AVG(hr_start), 2) AS avg_peak_traffic
FROM filtered_peak
GROUP BY hostname
ORDER BY avg_peak_traffic DESC;""",
        ["hive.aaa.accounting"],
        ["multi_stage_aggregation", "threshold_filtering"],
    ),
    (
        "H031",
        "Xác định khung giờ đỉnh điểm sự cố (date_hour có số cảnh báo lớn nhất toàn mạng) và phân tích cơ cấu các mức độ nghiêm trọng trong đúng khung giờ đó.",
        "alarm",
        """WITH peak_hour AS (
    SELECT date_hour
    FROM hive__gnoc__gnoc
    GROUP BY date_hour
    ORDER BY COUNT(*) DESC
    LIMIT 1
)
SELECT
    g.date_hour,
    g.level_important,
    COUNT(*) AS alarm_count
FROM hive__gnoc__gnoc g
JOIN peak_hour p ON g.date_hour = p.date_hour
GROUP BY g.date_hour, g.level_important
ORDER BY alarm_count DESC;""",
        ["hive.gnoc.gnoc"],
        ["multi_stage_aggregation", "peak_detection"],
    ),
    (
        "H032",
        "Tính độ lệch chuẩn thông lượng của từng cell trong tuần (STDDEV_SAMP) để lọc các cell có độ biến thiên cao (> 1.0 Mbps), sau đó tính thông lượng trung bình của nhóm này theo từng khu vực.",
        "network_kpi_5g",
        """WITH cell_variation AS (
    SELECT
        area_code,
        object_id,
        STDDEV_SAMP(CAST(dl_user_throughput_mbps AS DOUBLE)) AS tp_std,
        AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS cell_avg_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
    GROUP BY area_code, object_id
)
SELECT
    area_code,
    COUNT(object_id) AS volatile_cells,
    ROUND(AVG(cell_avg_tp), 2) AS avg_tp_of_volatile_cells
FROM cell_variation
WHERE tp_std > 1.0
GROUP BY area_code
ORDER BY area_code;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["statistical_stddev", "multi_stage_aggregation"],
    ),
    (
        "H033",
        "Tính trung bình số cảnh báo trên mỗi trạm phát sóng theo từng Vendor: Đầu tiên đếm số cảnh báo của từng trạm, sau đó tính trung bình các trạm theo từng nhà cung cấp.",
        "alarm",
        """WITH station_alarms AS (
    SELECT
        vendor,
        station_code,
        COUNT(*) AS alarms_per_station
    FROM hive__gnoc__gnoc
    GROUP BY vendor, station_code
)
SELECT
    vendor,
    COUNT(station_code) AS station_count,
    ROUND(AVG(alarms_per_station), 2) AS avg_alarms_per_station
FROM station_alarms
GROUP BY vendor
ORDER BY avg_alarms_per_station DESC;""",
        ["hive.gnoc.gnoc"],
        ["multi_stage_aggregation", "nested_averaging"],
    ),
    (
        "H034",
        "Tính tỷ lệ huyện có vấn đề: Lọc các quận/huyện có từ 2 cell 5G suy giảm trở lên, sau đó tính tỷ lệ số huyện có vấn đề trên tổng số huyện của từng tỉnh.",
        "network_kpi_5g",
        """WITH bad_districts AS (
    SELECT
        province_code,
        district_code,
        COUNT(DISTINCT object_id) AS bad_cell_count
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour = '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) < 5.0
    GROUP BY province_code, district_code
    HAVING COUNT(DISTINCT object_id) >= 2
),
all_districts AS (
    SELECT province_code, COUNT(DISTINCT district_code) AS total_districts
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE district_code != ''
    GROUP BY province_code
)
SELECT
    a.province_code,
    a.total_districts,
    COUNT(b.district_code) AS bad_districts_count,
    ROUND(COUNT(b.district_code) * 100.0 / a.total_districts, 2) AS bad_district_pct
FROM all_districts a
LEFT JOIN bad_districts b ON a.province_code = b.province_code
GROUP BY a.province_code, a.total_districts
ORDER BY bad_district_pct DESC, a.province_code ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.netbi.f_location_new"],
        ["multi_stage_aggregation", "district_ratio"],
    ),

    # -------------------------------------------------------------------------
    # NHÓM 6: GROUPING SETS / ROLLUP (5 cases: H035 - H039)
    # -------------------------------------------------------------------------
    (
        "H035",
        "Phân rã số lượng cell 5G suy giảm thông lượng theo cấu trúc phân cấp địa lý 3 tầng: Tỉnh, Khu vực và Toàn mạng sử dụng GROUPING SETS ((province_code, area_code), (area_code), ()) (Production Query Variant 3).",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT
        province_code,
        area_code,
        object_id
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour BETWEEN '2026-08-14-00' AND '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) < 5.0
      AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0
    GROUP BY province_code, area_code, object_id
    HAVING COUNT(*) > 3
)
SELECT
    area_code,
    province_code,
    COUNT(object_id) AS bad_cell_count,
    CASE
        WHEN area_code IS NOT NULL AND province_code IS NOT NULL THEN 'province'
        WHEN area_code IS NOT NULL AND province_code IS NULL THEN 'area'
        WHEN area_code IS NULL AND province_code IS NULL THEN 'network'
    END AS level
FROM bad_cells
GROUP BY GROUPING SETS (
    (area_code, province_code),
    (area_code),
    ()
)
ORDER BY level, area_code, province_code;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["grouping_sets", "hierarchical_rollup", "production_variant"],
    ),
    (
        "H036",
        "Báo cáo tổng hợp lưu lượng 5G phân cấp từ cấp Huyện -> Tỉnh -> Khu vực sử dụng cú pháp ROLLUP (area_code, province_code, district_code).",
        "network_kpi_5g",
        """SELECT
    area_code,
    province_code,
    district_code,
    ROUND(SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)), 2) AS total_traffic_gb,
    COUNT(DISTINCT object_id) AS total_cells
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE date_hour = '2026-08-20-00'
GROUP BY ROLLUP (area_code, province_code, district_code)
ORDER BY area_code, province_code, district_code;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["rollup", "multilevel_aggregation"],
    ),
    (
        "H037",
        "Lập bảng chéo đa chiều (Multi-dimensional Cross Tabulation) giữa Nhà cung cấp (vendor) và Mức độ nghiêm trọng (level_important) của cảnh báo GNOC sử dụng GROUPING SETS ((vendor, level_important), (vendor), (level_important), ()).",
        "alarm",
        """SELECT
    vendor,
    level_important,
    COUNT(*) AS alarm_count
FROM hive__gnoc__gnoc
GROUP BY GROUPING SETS (
    (vendor, level_important),
    (vendor),
    (level_important),
    ()
)
ORDER BY vendor, level_important;""",
        ["hive.gnoc.gnoc"],
        ["grouping_sets", "cross_tabulation", "cube"],
    ),
    (
        "H038",
        "Tổng hợp khối lượng xác thực AAA theo phân cấp thời gian: Khung giờ -> Ngày -> Toàn bộ tuần sử dụng ROLLUP.",
        "fbb",
        """SELECT
    SUBSTR(date_hour, 1, 10) AS dt_date,
    date_hour,
    SUM(CAST(accept AS BIGINT)) AS total_accept
FROM hive__aaa__authentication
GROUP BY ROLLUP (SUBSTR(date_hour, 1, 10), date_hour)
ORDER BY dt_date, date_hour;""",
        ["hive.aaa.authentication"],
        ["rollup", "temporal_rollup"],
    ),
    (
        "H039",
        "Phân rã kế hoạch bảo dưỡng trạm theo Đơn vị quản lý (area_name) và Trạng thái lệnh công tác (wo_status) bằng GROUPING SETS ((area_name, wo_status), (area_name), ()).",
        "alarm",
        """SELECT
    area_name,
    wo_status,
    COUNT(*) AS maintenance_count
FROM hive__gnoc__icms_maintain_calendar
WHERE wo_status IN ('COMPLETED', 'IN_PROGRESS')
GROUP BY GROUPING SETS (
    (area_name, wo_status),
    (area_name),
    ()
)
ORDER BY area_name, wo_status;""",
        ["hive.gnoc.icms_maintain_calendar"],
        ["grouping_sets", "status_rollup"],
    ),

    # -------------------------------------------------------------------------
    # NHÓM 7: DATA QUALITY / RECONCILIATION (5 cases: H040 - H044)
    # -------------------------------------------------------------------------
    (
        "H040",
        "Đối soát khối lượng bản tin AAA: Tính độ chênh lệch giữa số lượt xác thực thành công (accept) và số phiên kế toán bắt đầu (start) theo từng máy chủ BRAS; lọc các máy chủ có độ chênh lệch tuyệt đối lớn hơn 10 bản tin.",
        "fbb",
        """WITH auth_tot AS (
    SELECT hostname, SUM(CAST(accept AS BIGINT)) AS tot_accept
    FROM hive__aaa__authentication
    GROUP BY hostname
),
acct_tot AS (
    SELECT hostname, SUM(CAST(start AS BIGINT)) AS tot_start
    FROM hive__aaa__accounting
    GROUP BY hostname
)
SELECT
    au.hostname,
    au.tot_accept,
    COALESCE(ac.tot_start, 0) AS tot_start,
    ABS(au.tot_accept - COALESCE(ac.tot_start, 0)) AS discrepancy
FROM auth_tot au
INNER JOIN acct_tot ac ON au.hostname = ac.hostname
WHERE ABS(au.tot_accept - COALESCE(ac.tot_start, 0)) > 10
ORDER BY discrepancy DESC;""",
        ["hive.aaa.authentication", "hive.aaa.accounting"],
        ["reconciliation", "discrepancy_check", "data_quality"],
    ),
    (
        "H041",
        "Đối soát quy hoạch địa bàn và đo kiểm mạng: So sánh tổng số tỉnh quy hoạch trong f_location_new với số tỉnh thực tế có cell 5G đo đạc trong bảng KPI.",
        "common_location",
        """WITH configured_provinces AS (
    SELECT COUNT(DISTINCT province_code) AS cfg_prov_count
    FROM hive__netbi__f_location_new
),
measured_provinces AS (
    SELECT COUNT(DISTINCT province_code) AS meas_prov_count
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE province_code != 'UNKNOWN_PRV'
)
SELECT
    c.cfg_prov_count,
    m.meas_prov_count,
    (c.cfg_prov_count - m.meas_prov_count) AS unmeasured_provinces
FROM configured_provinces c
CROSS JOIN measured_provinces m;""",
        ["hive.netbi.f_location_new", "hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["reconciliation", "cross_join", "coverage_audit"],
    ),
    (
        "H042",
        "Phát hiện tài khoản bất thường: Tìm các tài khoản FTTH trong ftth_account_pppoe có loginlimit lớn hơn 1 nhưng số lần kết nối hiện tại (count) bằng 0.",
        "fbb",
        """SELECT
    username,
    groupname,
    loginlimit,
    count
FROM hive__aaa__ftth_account_pppoe
WHERE CAST(loginlimit AS INT) > 1
  AND count = 0
ORDER BY username;""",
        ["hive.aaa.ftth_account_pppoe"],
        ["data_quality", "anomaly_detection"],
    ),
    (
        "H043",
        "Phát hiện dị thường dữ liệu đo đạc (Data Anomaly Detection): Tìm các bản ghi KPI 5G có giá trị thông lượng người dùng không hợp lệ (nhỏ hơn 0 hoặc lớn hơn 1000 Mbps).",
        "network_kpi_5g",
        """SELECT
    object_id,
    date_hour,
    CAST(dl_user_throughput_mbps AS DOUBLE) AS invalid_throughput
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE CAST(dl_user_throughput_mbps AS DOUBLE) < 0
   OR CAST(dl_user_throughput_mbps AS DOUBLE) > 1000
ORDER BY object_id;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["anomaly_detection", "range_check", "data_quality"],
    ),
    (
        "H044",
        "Kiểm tra tính đầy đủ của dữ liệu (Data Completeness): Tìm các cell 5G có số ngày đo kiểm nhỏ hơn 7 ngày trong tuần từ 2026-08-14 đến 2026-08-20.",
        "network_kpi_5g",
        """SELECT
    object_id,
    province_code,
    COUNT(DISTINCT date) AS reported_days
FROM hive__npms__kpi_access5g_5g_cell_peak_view
WHERE date BETWEEN '2026-08-14' AND '2026-08-20'
GROUP BY object_id, province_code
HAVING COUNT(DISTINCT date) < 7
ORDER BY reported_days ASC, object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["data_completeness", "having", "count_distinct"],
    ),

    # -------------------------------------------------------------------------
    # NHÓM 8: CROSS-DOMAIN BUSINESS LOGIC (6 cases: H045 - H050)
    # -------------------------------------------------------------------------
    (
        "H045",
        "Tương quan sự cố mạng đa miền: Tìm các cell 5G suy giảm thông lượng (bad cell) mà trạm phát sóng tương ứng đang có cảnh báo CRITICAL trong GNOC (Production Query Variant 4).",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT
        object_id,
        province_code,
        AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS avg_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour BETWEEN '2026-08-14-00' AND '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) < 5.0
      AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0
    GROUP BY object_id, province_code
    HAVING COUNT(*) > 3
),
crit_stations AS (
    SELECT DISTINCT station_code
    FROM hive__gnoc__gnoc
    WHERE level_important = 'CRITICAL'
)
SELECT
    b.object_id,
    b.province_code,
    ROUND(b.avg_tp, 2) AS avg_tp,
    c.station_code
FROM bad_cells b
JOIN crit_stations c ON c.station_code LIKE '%' || b.province_code || '%'
ORDER BY b.object_id;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.gnoc.gnoc"],
        ["cross_domain", "kpi_alarm_correlation", "production_variant"],
    ),
    (
        "H046",
        "Tương quan lỗi truy cập FBB và sự cố mạng: Tìm các máy chủ BRAS có phát sinh cảnh báo lỗi xác thực (reject > 0) và đồng thời có máy chủ SBR tham gia xử lý.",
        "fbb",
        """SELECT
    a.hostname,
    a.sbr_server,
    SUM(CAST(a.reject AS BIGINT)) AS total_rejects,
    SUM(CAST(a.accept AS BIGINT)) AS total_accepts
FROM hive__aaa__authentication a
WHERE CAST(a.reject AS INT) > 0
GROUP BY a.hostname, a.sbr_server
ORDER BY total_rejects DESC, a.hostname ASC;""",
        ["hive.aaa.authentication"],
        ["cross_domain", "fbb_error_correlation"],
    ),
    (
        "H047",
        "Đánh giá ảnh hưởng của bảo dưỡng trạm: Thống kê số lượng lệnh bảo dưỡng IN_PROGRESS theo từng khu vực và đối chiếu với số lượng cảnh báo sự cố GNOC tương ứng.",
        "alarm",
        """WITH maint_prog AS (
    SELECT area_code, COUNT(*) AS in_progress_maint
    FROM hive__gnoc__icms_maintain_calendar
    WHERE wo_status = 'IN_PROGRESS'
    GROUP BY area_code
),
alarm_cnt AS (
    SELECT region, COUNT(*) AS alarm_count
    FROM hive__gnoc__gnoc
    GROUP BY region
)
SELECT
    m.area_code,
    m.in_progress_maint,
    COALESCE(a.alarm_count, 0) AS alarm_count
FROM maint_prog m
LEFT JOIN alarm_cnt a ON m.area_code = a.region
ORDER BY m.area_code;""",
        ["hive.gnoc.icms_maintain_calendar", "hive.gnoc.gnoc"],
        ["cross_domain", "maintenance_alarm_impact"],
    ),
    (
        "H048",
        "Phân tích tác động của Blacklist: Thống kê số lượng trạm enodeb nằm trong danh sách đen blacklist theo từng zone_id.",
        "data_monitoring",
        """SELECT
    zone_id,
    COUNT(DISTINCT enodeb_id) AS total_blacklisted_nodes
FROM mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id
GROUP BY zone_id
ORDER BY total_blacklisted_nodes DESC, zone_id ASC;""",
        ["mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id"],
        ["cross_domain", "zone_analysis"],
    ),
    (
        "H049",
        "Tính chỉ số áp lực tải mạng (Congestion Index = Tổng lưu lượng GB / Thông lượng trung bình Mbps) của các cell 5G có lưu lượng lớn hơn 20 GB, kèm tên tỉnh và khu vực quản lý.",
        "network_kpi_5g",
        """WITH cell_agg AS (
    SELECT
        object_id,
        province_code,
        area_code,
        SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)) AS total_traffic,
        AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) AS avg_tp
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour = '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0
    GROUP BY object_id, province_code, area_code
    HAVING SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)) > 20.0
)
SELECT
    c.object_id,
    c.area_code,
    c.province_code,
    l.province_name,
    ROUND(c.total_traffic, 2) AS traffic_gb,
    ROUND(c.avg_tp, 2) AS throughput_mbps,
    ROUND(c.total_traffic / c.avg_tp, 2) AS congestion_index
FROM cell_agg c
LEFT JOIN (SELECT DISTINCT province_code, province_name FROM hive__netbi__f_location_new) l
    ON c.province_code = l.province_code
ORDER BY congestion_index DESC, c.object_id ASC;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.netbi.f_location_new"],
        ["formula_calculation", "cross_domain", "congestion_index"],
    ),
    (
        "H050",
        "Báo cáo điều hành mạng tổng thể (Executive Scorecard): Tổng hợp số lượng cell 5G suy giảm (loại trừ occean_cell), tổng số cảnh báo CRITICAL, và tổng lưu lượng 5G theo từng khu vực quản lý (Production Query Variant 5).",
        "network_kpi_5g",
        """WITH bad_cells AS (
    SELECT
        area_code,
        COUNT(DISTINCT object_id) AS bad_cell_count
    FROM hive__npms__kpi_access5g_5g_cell_peak_view t
    WHERE country = 'VNM'
      AND date_hour BETWEEN '2026-08-14-00' AND '2026-08-20-00'
      AND CAST(dl_user_throughput_mbps AS DOUBLE) < 5.0
      AND CAST(dl_user_throughput_mbps AS DOUBLE) > 0
      AND NOT EXISTS (
          SELECT 1 FROM hive__npms__occean_cell c
          WHERE c.object_id = t.object_id
      )
    GROUP BY area_code
),
crit_alarms AS (
    SELECT region, COUNT(*) AS crit_alarm_count
    FROM hive__gnoc__gnoc
    WHERE level_important = 'CRITICAL'
    GROUP BY region
),
tot_traffic AS (
    SELECT area_code, ROUND(SUM(CAST(nr_ps_traffic_total_gb AS DOUBLE)), 2) AS traffic_gb
    FROM hive__npms__kpi_access5g_5g_cell_peak_view
    WHERE date_hour = '2026-08-20-00'
    GROUP BY area_code
)
SELECT
    t.area_code,
    t.traffic_gb,
    COALESCE(b.bad_cell_count, 0) AS bad_cell_count,
    COALESCE(a.crit_alarm_count, 0) AS crit_alarm_count
FROM tot_traffic t
LEFT JOIN bad_cells b ON t.area_code = b.area_code
LEFT JOIN crit_alarms a ON t.area_code = a.region
ORDER BY t.area_code;""",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.npms.occean_cell", "hive.gnoc.gnoc"],
        ["executive_scorecard", "cross_domain", "multi_cte", "production_variant"],
    ),
]

def main():
    print(f"Connecting to DuckDB: {DUCKDB_PATH}")
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    print(f"Testing all {len(HARD_CASES)} Hard cases against DuckDB...")

    errors = []
    zero_rows = []
    for cid, q, dom, sql_d, req_t, skills in HARD_CASES:
        try:
            res = con.execute(sql_d).fetchall()
            if len(res) == 0:
                zero_rows.append(cid)
            print(f"[{cid}] PASS ({len(res)} rows)")
        except Exception as e:
            errors.append((cid, str(e)))
            print(f"[{cid}] ERROR: {e}")

    if errors:
        print(f"\nFAILED: {len(errors)} queries had syntax/execution errors:")
        for cid, err in errors:
            print(f"  {cid}: {err}")
        sys.exit(1)

    if zero_rows:
        print(f"\nWARNING: {len(zero_rows)} queries returned 0 rows: {zero_rows}")
        sys.exit(1)

    print("\nALL 50 HARD CASES PASSED WITH NON-ZERO ROWS!")

    # Generate hard_cases_data.py
    print(f"Writing definitions to {OUT_FILE}...")
    lines = [
        '"""hard_cases_data.py - 50 Hard Cases definitions."""',
        "",
        "HARD_SPECS = [",
    ]

    for cid, q, dom, sql_d, req_t, skills in HARD_CASES:
        sql_t = sql_d.replace("hive__npms__kpi_access5g_5g_cell_peak_view", "hive.npms.kpi_access5g_5g_cell_peak_view")
        sql_t = sql_t.replace("hive__npms__occean_cell", "hive.npms.occean_cell")
        sql_t = sql_t.replace("hive__npms__kpi_access4g_all_day_normal", "hive.npms.kpi_access4g_all_day_normal")
        sql_t = sql_t.replace("hive__netbi__f_location_new", "hive.netbi.f_location_new")
        sql_t = sql_t.replace("hive__gnoc__gnoc", "hive.gnoc.gnoc")
        sql_t = sql_t.replace("hive__gnoc__cat_department", "hive.gnoc.cat_department")
        sql_t = sql_t.replace("hive__gnoc__icms_maintain_calendar", "hive.gnoc.icms_maintain_calendar")
        sql_t = sql_t.replace("hive__gnoc__od_history", "hive.gnoc.od_history")
        sql_t = sql_t.replace("hive__aaa__authentication", "hive.aaa.authentication")
        sql_t = sql_t.replace("hive__aaa__accounting", "hive.aaa.accounting")
        sql_t = sql_t.replace("hive__aaa__ftth_account_pppoe", "hive.aaa.ftth_account_pppoe")
        sql_t = sql_t.replace("mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id", "mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id")

        lines.append("    (")
        lines.append(f"        {repr(cid)},")
        lines.append(f"        {repr(q)},")
        lines.append(f"        {repr(dom)},")
        lines.append(f"        {repr(sql_d)},")
        lines.append(f"        {repr(sql_t)},")
        lines.append(f"        {repr(req_t)},")
        lines.append(f"        {repr(skills)},")
        lines.append("    ),")

    lines.append("]")
    lines.append("")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Successfully wrote {OUT_FILE}.")

if __name__ == "__main__":
    main()
