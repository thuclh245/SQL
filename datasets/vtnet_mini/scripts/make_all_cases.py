import sys
from pathlib import Path
import duckdb

PROJECT_DIR = Path(__file__).resolve().parents[1]
DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"

EASY_CASES = [
    (
        "E001",
        "Đếm tổng số tỉnh duy nhất trong danh mục địa bàn f_location_new.",
        "common_location",
        "SELECT COUNT(DISTINCT province_code) AS total_provinces FROM hive__netbi__f_location_new;",
        ["hive.netbi.f_location_new"],
        ["count_distinct", "simple_lookup"],
    ),
    (
        "E002",
        "Liệt kê danh sách mã tỉnh và tên tỉnh thuộc Khu vực 1 (AREA_1) từ bảng địa bàn f_location_new.",
        "common_location",
        "SELECT DISTINCT province_code, province_name FROM hive__netbi__f_location_new WHERE area_code = 'AREA_1' ORDER BY province_code;",
        ["hive.netbi.f_location_new"],
        ["filtering", "simple_lookup"],
    ),
    (
        "E003",
        "Đếm số lượng cell 5G có trong danh sách loại trừ occean_cell.",
        "network_kpi_5g",
        "SELECT COUNT(*) AS total_ocean_cells FROM hive__npms__occean_cell WHERE cell_type = '5G_NR';",
        ["hive.npms.occean_cell"],
        ["filtering", "aggregation"],
    ),
    (
        "E004",
        "Đếm số lượng tài khoản FTTH PPPoE thuộc nhóm khách hàng VIP (groupname = 'FTTH_VIP').",
        "fbb",
        "SELECT COUNT(*) AS total_vip_users FROM hive__aaa__ftth_account_pppoe WHERE groupname = 'FTTH_VIP';",
        ["hive.aaa.ftth_account_pppoe"],
        ["filtering", "aggregation"],
    ),
    (
        "E005",
        "Liệt kê mã phòng ban và tên phòng ban thuộc khối NOC trong danh mục GNOC.",
        "alarm",
        "SELECT dept_code, dept_name FROM hive__gnoc__cat_department WHERE dept_code LIKE 'NOC_%' ORDER BY dept_code;",
        ["hive.gnoc.cat_department"],
        ["pattern_matching", "simple_lookup"],
    ),
    (
        "E006",
        "Lấy danh sách các nhóm giám sát dữ liệu có mã id nhỏ hơn hoặc bằng 2 trong bảng groups.",
        "data_monitoring",
        "SELECT id, name FROM mysql_datamon__data_monitoring__groups WHERE id <= 2 ORDER BY id;",
        ["mysql_datamon.data_monitoring.groups"],
        ["filtering", "simple_lookup"],
    ),
    (
        "E007",
        "Đếm tổng số bản ghi trong danh sách đen người dùng theo khu vực có id <= 15.",
        "data_monitoring",
        "SELECT COUNT(*) AS total_blacklist FROM mysql_datamon__data_monitoring__usersinarea_blacklist WHERE id <= 15;",
        ["mysql_datamon.data_monitoring.usersinarea_blacklist"],
        ["filtering", "aggregation"],
    ),
    (
        "E008",
        "Đếm số lượng bản ghi KPI 5G tại tỉnh Hà Nội (HNI) trong ngày 2026-08-20.",
        "network_kpi_5g",
        "SELECT COUNT(*) AS total_records FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE province_code = 'HNI' AND date_hour = '2026-08-20-00';",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["filtering", "aggregation"],
    ),
    (
        "E009",
        "Lấy 5 cell 5G có thông lượng người dùng tải xuống cao nhất trong ngày 2026-08-20.",
        "network_kpi_5g",
        "SELECT object_id, CAST(dl_user_throughput_mbps AS DOUBLE) AS throughput FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE date_hour = '2026-08-20-00' ORDER BY throughput DESC, object_id ASC LIMIT 5;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["sorting", "limit"],
    ),
    (
        "E010",
        "Đếm tổng số sự kiện cảnh báo sự cố nghiêm trọng (CRITICAL) được ghi nhận trong bảng gnoc.",
        "alarm",
        "SELECT COUNT(*) AS total_alarms FROM hive__gnoc__gnoc WHERE level_important = 'CRITICAL';",
        ["hive.gnoc.gnoc"],
        ["filtering", "aggregation"],
    ),
    (
        "E011",
        "Lấy danh sách các máy chủ xác thực sbr_server duy nhất trong bảng authentication.",
        "fbb",
        "SELECT DISTINCT sbr_server FROM hive__aaa__authentication ORDER BY sbr_server;",
        ["hive.aaa.authentication"],
        ["distinct", "simple_lookup"],
    ),
    (
        "E012",
        "Đếm số lượng sự kiện xác thực có số lượt chấp thuận (accept) lớn hơn 150.",
        "fbb",
        "SELECT COUNT(*) AS total_events FROM hive__aaa__authentication WHERE CAST(accept AS INT) > 150;",
        ["hive.aaa.authentication"],
        ["filtering", "type_cast"],
    ),
    (
        "E013",
        "Liệt kê các nhà cung cấp thiết bị (vendor) khác nhau trong bảng sự kiện gnoc có tên nhà cung cấp không rỗng.",
        "alarm",
        "SELECT DISTINCT vendor FROM hive__gnoc__gnoc WHERE vendor IN ('Huawei', 'Ericsson') ORDER BY vendor;",
        ["hive.gnoc.gnoc"],
        ["distinct", "filtering"],
    ),
    (
        "E014",
        "Tính thông lượng tải xuống trung bình của mạng 4G trong ngày 2026-08-20.",
        "network_kpi_4g",
        "SELECT ROUND(AVG(CAST(dl_cell_throughput_mbps AS DOUBLE)), 2) AS avg_4g_throughput FROM hive__npms__kpi_access4g_all_day_normal WHERE date = '2026-08-20';",
        ["hive.npms.kpi_access4g_all_day_normal"],
        ["aggregation", "type_cast"],
    ),
    (
        "E015",
        "Đếm số lượng cảnh báo có mức độ quan trọng là CRITICAL trong bảng gnoc.",
        "alarm",
        "SELECT COUNT(*) AS critical_count FROM hive__gnoc__gnoc WHERE level_important = 'CRITICAL';",
        ["hive.gnoc.gnoc"],
        ["filtering", "aggregation"],
    ),
    (
        "E016",
        "Liệt kê các mã khu vực (area_code) duy nhất có trong bảng f_location_new.",
        "common_location",
        "SELECT DISTINCT area_code FROM hive__netbi__f_location_new ORDER BY area_code;",
        ["hive.netbi.f_location_new"],
        ["distinct", "simple_lookup"],
    ),
    (
        "E017",
        "Đếm số tài khoản FTTH có giới hạn đăng nhập (loginlimit) bằng 1.",
        "fbb",
        "SELECT COUNT(*) AS count_limit_1 FROM hive__aaa__ftth_account_pppoe WHERE loginlimit = '1';",
        ["hive.aaa.ftth_account_pppoe"],
        ["filtering", "aggregation"],
    ),
    (
        "E018",
        "Lấy 5 địa chỉ IP duy nhất đầu tiên được ghi nhận trong bảng accounting.",
        "fbb",
        "SELECT DISTINCT ip FROM hive__aaa__accounting ORDER BY ip LIMIT 5;",
        ["hive.aaa.accounting"],
        ["distinct", "limit"],
    ),
    (
        "E019",
        "Đếm số cell trong occean_cell có loại cell là '5G_NR'.",
        "network_kpi_5g",
        "SELECT COUNT(*) AS count_5g_ocean FROM hive__npms__occean_cell WHERE cell_type = '5G_NR';",
        ["hive.npms.occean_cell"],
        ["filtering", "aggregation"],
    ),
    (
        "E020",
        "Lấy danh sách 5 mã trạm phát sóng (station_code) duy nhất đầu tiên trong bảng gnoc có mức cảnh báo CRITICAL.",
        "alarm",
        "SELECT DISTINCT station_code FROM hive__gnoc__gnoc WHERE level_important = 'CRITICAL' ORDER BY station_code LIMIT 5;",
        ["hive.gnoc.gnoc"],
        ["distinct", "filtering", "limit"],
    ),
]

MEDIUM_CASES = [
    (
        "M001",
        "Thống kê số lượng tỉnh thành duy nhất theo từng khu vực (area_code) từ bảng f_location_new.",
        "common_location",
        "SELECT area_code, COUNT(DISTINCT province_code) AS province_count FROM hive__netbi__f_location_new GROUP BY area_code ORDER BY area_code;",
        ["hive.netbi.f_location_new"],
        ["group_by", "count_distinct"],
    ),
    (
        "M002",
        "Tính lưu lượng 5G tải xuống trung bình theo từng tỉnh trong ngày 2026-08-20.",
        "network_kpi_5g",
        "SELECT province_code, ROUND(AVG(CAST(nr_ps_traffic_total_gb AS DOUBLE)), 2) AS avg_traffic FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE date_hour = '2026-08-20-00' GROUP BY province_code ORDER BY avg_traffic DESC, province_code ASC;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["group_by", "aggregation", "type_cast"],
    ),
    (
        "M003",
        "Thống kê số lượng cảnh báo trong bảng gnoc theo mức độ CRITICAL và MAJOR.",
        "alarm",
        "SELECT level_important, COUNT(*) AS alarm_count FROM hive__gnoc__gnoc WHERE level_important IN ('CRITICAL', 'MAJOR') GROUP BY level_important ORDER BY alarm_count DESC;",
        ["hive.gnoc.gnoc"],
        ["filtering", "group_by"],
    ),
    (
        "M004",
        "Liệt kê số lượng cảnh báo mạng gnoc theo từng nhà sản xuất thiết bị (Huawei, Ericsson).",
        "alarm",
        "SELECT vendor, COUNT(*) AS alarm_count FROM hive__gnoc__gnoc WHERE vendor IN ('Huawei', 'Ericsson') GROUP BY vendor ORDER BY alarm_count DESC;",
        ["hive.gnoc.gnoc"],
        ["filtering", "group_by"],
    ),
    (
        "M005",
        "Tính tổng số phiên bắt đầu (start) và kết thúc (stop) trong bảng accounting theo máy chủ sbr_server.",
        "fbb",
        "SELECT sbr_server, SUM(CAST(start AS BIGINT)) AS total_start, SUM(CAST(stop AS BIGINT)) AS total_stop FROM hive__aaa__accounting GROUP BY sbr_server ORDER BY sbr_server;",
        ["hive.aaa.accounting"],
        ["group_by", "aggregation", "type_cast"],
    ),
    (
        "M006",
        "Đếm số tài khoản FTTH PPPoE theo từng nhóm gói cước (groupname).",
        "fbb",
        "SELECT groupname, COUNT(*) AS user_count FROM hive__aaa__ftth_account_pppoe GROUP BY groupname ORDER BY user_count DESC;",
        ["hive.aaa.ftth_account_pppoe"],
        ["group_by", "aggregation"],
    ),
    (
        "M007",
        "Thống kê số lượng cảnh báo mức CRITICAL theo từng vùng (region) trong bảng gnoc.",
        "alarm",
        "SELECT region, COUNT(*) AS alarm_count FROM hive__gnoc__gnoc WHERE level_important = 'CRITICAL' GROUP BY region ORDER BY region;",
        ["hive.gnoc.gnoc"],
        ["filtering", "group_by"],
    ),
    (
        "M008",
        "Lấy thông lượng 4G tải xuống trung bình và tối đa theo từng khu vực trong ngày 2026-08-20.",
        "network_kpi_4g",
        "SELECT area_code, ROUND(AVG(CAST(dl_cell_throughput_mbps AS DOUBLE)), 2) AS avg_tp, ROUND(MAX(CAST(dl_cell_throughput_mbps AS DOUBLE)), 2) AS max_tp FROM hive__npms__kpi_access4g_all_day_normal WHERE date = '2026-08-20' GROUP BY area_code ORDER BY area_code;",
        ["hive.npms.kpi_access4g_all_day_normal"],
        ["group_by", "aggregation", "type_cast"],
    ),
    (
        "M009",
        "Đếm số lượng bản ghi KPI 5G theo từng ngày trong khoảng thời gian từ 2026-08-14 đến 2026-08-17.",
        "network_kpi_5g",
        "SELECT date, COUNT(*) AS record_count FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE date BETWEEN '2026-08-14' AND '2026-08-17' GROUP BY date ORDER BY date;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["filtering", "group_by"],
    ),
    (
        "M010",
        "Tìm các tỉnh có từ 2 cell 5G trở lên được ghi nhận trong ngày 2026-08-20.",
        "network_kpi_5g",
        "SELECT province_code, COUNT(DISTINCT object_id) AS cell_count FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE date_hour = '2026-08-20-00' GROUP BY province_code HAVING COUNT(DISTINCT object_id) >= 2 ORDER BY cell_count DESC, province_code ASC;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["group_by", "having", "count_distinct"],
    ),
    (
        "M011",
        "Lấy danh sách tên tỉnh kèm số lượng cell 5G tương ứng bằng cách join bảng KPI 5G với f_location_new.",
        "network_kpi_5g",
        "SELECT l.province_name, COUNT(DISTINCT k.object_id) AS cell_count FROM (SELECT DISTINCT province_code, province_name FROM hive__netbi__f_location_new) l INNER JOIN hive__npms__kpi_access5g_5g_cell_peak_view k ON l.province_code = k.province_code WHERE k.date_hour = '2026-08-20-00' GROUP BY l.province_name ORDER BY cell_count DESC, l.province_name ASC;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view", "hive.netbi.f_location_new"],
        ["inner_join", "group_by", "count_distinct"],
    ),
    (
        "M012",
        "Thống kê số lượt xác thực thành công (accept) và từ chối (reject) theo từng khung giờ trong authentication.",
        "fbb",
        "SELECT date_hour, SUM(CAST(accept AS BIGINT)) AS total_accept, SUM(CAST(reject AS BIGINT)) AS total_reject FROM hive__aaa__authentication GROUP BY date_hour ORDER BY date_hour;",
        ["hive.aaa.authentication"],
        ["group_by", "aggregation", "type_cast"],
    ),
    (
        "M013",
        "Liệt kê các tỉnh có lưu lượng dữ liệu 4G lớn hơn 3 tỷ bit trong ngày 2026-08-20.",
        "network_kpi_4g",
        "SELECT province_code, COUNT(*) AS high_traffic_cells FROM hive__npms__kpi_access4g_all_day_normal WHERE CAST(celldltrafficvolume_bit AS BIGINT) > 3000000000 AND date = '2026-08-20' GROUP BY province_code ORDER BY high_traffic_cells DESC, province_code ASC;",
        ["hive.npms.kpi_access4g_all_day_normal"],
        ["filtering", "group_by", "type_cast"],
    ),
    (
        "M014",
        "Tìm danh sách các mã trạm (station_code) duy nhất có cảnh báo mức CRITICAL trong bảng gnoc.",
        "alarm",
        "SELECT DISTINCT station_code FROM hive__gnoc__gnoc WHERE level_important = 'CRITICAL' ORDER BY station_code;",
        ["hive.gnoc.gnoc"],
        ["filtering", "distinct"],
    ),
    (
        "M015",
        "Thống kê số lượng cảnh báo mức CRITICAL theo từng ngày từ cột date_hour trong bảng gnoc.",
        "alarm",
        "SELECT SUBSTR(date_hour, 1, 10) AS dt, COUNT(*) AS alarm_count FROM hive__gnoc__gnoc WHERE level_important = 'CRITICAL' GROUP BY SUBSTR(date_hour, 1, 10) ORDER BY dt;",
        ["hive.gnoc.gnoc"],
        ["filtering", "group_by", "string_functions"],
    ),
    (
        "M016",
        "Tìm các cell 5G có throughput tải xuống trung bình trong 7 ngày nhỏ hơn 5 Mbps.",
        "network_kpi_5g",
        "SELECT object_id, ROUND(AVG(CAST(dl_user_throughput_mbps AS DOUBLE)), 2) AS avg_dl_tp FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE date_hour BETWEEN '2026-08-14-00' AND '2026-08-20-00' GROUP BY object_id HAVING AVG(CAST(dl_user_throughput_mbps AS DOUBLE)) < 5.0 ORDER BY avg_dl_tp ASC, object_id ASC;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["filtering", "group_by", "having"],
    ),
    (
        "M017",
        "Đếm số cảnh báo thuộc vendor Huawei theo từng mức độ quan trọng trong bảng gnoc.",
        "alarm",
        "SELECT vendor, level_important, COUNT(*) AS alarm_count FROM hive__gnoc__gnoc WHERE vendor = 'Huawei' GROUP BY vendor, level_important ORDER BY level_important;",
        ["hive.gnoc.gnoc"],
        ["filtering", "group_by"],
    ),
    (
        "M018",
        "Lấy tên tỉnh và lưu lượng 4G trung bình của tỉnh đó trong ngày 2026-08-20 qua phép INNER JOIN với f_location_new.",
        "network_kpi_4g",
        "SELECT l.province_name, ROUND(AVG(CAST(k.dl_cell_throughput_mbps AS DOUBLE)), 2) AS avg_4g_tp FROM (SELECT DISTINCT province_code, province_name FROM hive__netbi__f_location_new) l INNER JOIN hive__npms__kpi_access4g_all_day_normal k ON l.province_code = k.province_code WHERE k.date = '2026-08-20' GROUP BY l.province_name ORDER BY avg_4g_tp DESC, l.province_name ASC;",
        ["hive.npms.kpi_access4g_all_day_normal", "hive.netbi.f_location_new"],
        ["inner_join", "group_by", "aggregation"],
    ),
    (
        "M019",
        "Đếm số lượng cell 5G có lưu lượng nr_ps_traffic_total_gb lớn hơn 20 GB theo từng tỉnh.",
        "network_kpi_5g",
        "SELECT province_code, COUNT(DISTINCT object_id) AS heavy_cells FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE CAST(nr_ps_traffic_total_gb AS DOUBLE) > 20.0 AND date_hour = '2026-08-20-00' GROUP BY province_code ORDER BY heavy_cells DESC, province_code ASC;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["filtering", "group_by", "count_distinct"],
    ),
    (
        "M020",
        "Thống kê số lượng cell trong occean_cell theo từng loại cell (cell_type).",
        "network_kpi_5g",
        "SELECT cell_type, COUNT(*) AS cell_count FROM hive__npms__occean_cell GROUP BY cell_type ORDER BY cell_type;",
        ["hive.npms.occean_cell"],
        ["group_by", "aggregation"],
    ),
    (
        "M021",
        "Lấy danh sách tài khoản FTTH kèm số kết nối (count) cho nhóm FTTH_VIP có số kết nối >= 1.",
        "fbb",
        "SELECT username, count FROM hive__aaa__ftth_account_pppoe WHERE groupname = 'FTTH_VIP' AND count >= 1 ORDER BY username;",
        ["hive.aaa.ftth_account_pppoe"],
        ["filtering", "simple_lookup"],
    ),
    (
        "M022",
        "Tính thông lượng tải lên (ul_user_throughput_mbps) trung bình của các cell 5G tại Hà Nội (HNI) trong ngày 2026-08-20.",
        "network_kpi_5g",
        "SELECT ROUND(AVG(CAST(ul_user_throughput_mbps AS DOUBLE)), 2) AS avg_ul_tp FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE province_code = 'HNI' AND date_hour = '2026-08-20-00';",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["filtering", "aggregation", "type_cast"],
    ),
    (
        "M023",
        "Tính tổng lưu lượng 4G (Gbit) theo từng khu vực (area_code) trong ngày 2026-08-20.",
        "network_kpi_4g",
        "SELECT area_code, ROUND(SUM(CAST(celldltrafficvolume_bit AS DOUBLE)) / 1000000000, 2) AS total_traffic_gbit FROM hive__npms__kpi_access4g_all_day_normal WHERE date = '2026-08-20' GROUP BY area_code ORDER BY total_traffic_gbit DESC;",
        ["hive.npms.kpi_access4g_all_day_normal"],
        ["group_by", "aggregation", "type_cast"],
    ),
    (
        "M024",
        "Đếm số lượng máy chủ BRAS (hostname) duy nhất tham gia xác thực AAA.",
        "fbb",
        "SELECT COUNT(DISTINCT hostname) AS unique_bras FROM hive__aaa__authentication;",
        ["hive.aaa.authentication"],
        ["count_distinct"],
    ),
    (
        "M025",
        "Thống kê tổng số phiên kế toán bắt đầu theo máy chủ hostname và sbr_server trong accounting.",
        "fbb",
        "SELECT hostname, sbr_server, SUM(CAST(start AS BIGINT)) AS total_start FROM hive__aaa__accounting GROUP BY hostname, sbr_server ORDER BY total_start DESC, hostname ASC;",
        ["hive.aaa.accounting"],
        ["group_by", "aggregation", "type_cast"],
    ),
    (
        "M026",
        "Lấy danh sách các cell 5G có thông lượng nhỏ hơn 5 Mbps nhưng lưu lượng lớn hơn 10 GB trong ngày 2026-08-20.",
        "network_kpi_5g",
        "SELECT object_id, CAST(dl_user_throughput_mbps AS DOUBLE) AS tp, CAST(nr_ps_traffic_total_gb AS DOUBLE) AS traffic FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE date_hour = '2026-08-20-00' AND CAST(dl_user_throughput_mbps AS DOUBLE) < 5.0 AND CAST(nr_ps_traffic_total_gb AS DOUBLE) > 10.0 ORDER BY tp ASC, object_id ASC;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["filtering", "type_cast", "sorting"],
    ),
    (
        "M027",
        "Thống kê số lượng cell duy nhất theo từng huyện (district_code) trong ngày 2026-08-20.",
        "network_kpi_5g",
        "SELECT district_code, COUNT(DISTINCT object_id) AS cell_count FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE date_hour = '2026-08-20-00' GROUP BY district_code ORDER BY cell_count DESC, district_code ASC;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["group_by", "count_distinct"],
    ),
    (
        "M028",
        "Lấy tên khu vực (area_name) và số lượng tỉnh duy nhất tương ứng thuộc khu vực đó.",
        "common_location",
        "SELECT area_name, COUNT(DISTINCT province_code) AS total_provinces FROM hive__netbi__f_location_new GROUP BY area_name ORDER BY total_provinces DESC, area_name ASC;",
        ["hive.netbi.f_location_new"],
        ["group_by", "count_distinct"],
    ),
    (
        "M029",
        "Tìm các cảnh báo gnoc thuộc vendor Huawei có mức độ CRITICAL hoặc MAJOR.",
        "alarm",
        "SELECT schedule_id, station_code, level_important FROM hive__gnoc__gnoc WHERE vendor = 'Huawei' AND level_important IN ('CRITICAL', 'MAJOR') ORDER BY schedule_id;",
        ["hive.gnoc.gnoc"],
        ["filtering", "sorting"],
    ),
    (
        "M030",
        "Đếm số cell 5G có mặt trong bảng KPI nhưng không thuộc nhà mạng Lào (country != 'LAO') theo quốc gia.",
        "network_kpi_5g",
        "SELECT country, COUNT(DISTINCT object_id) AS cell_count FROM hive__npms__kpi_access5g_5g_cell_peak_view WHERE country != 'LAO' GROUP BY country ORDER BY country;",
        ["hive.npms.kpi_access5g_5g_cell_peak_view"],
        ["filtering", "group_by", "count_distinct"],
    ),
]

def make_trino_sql(sql_d):
    s = sql_d
    replacements = [
        ("hive__npms__kpi_access5g_5g_cell_peak_view", "hive.npms.kpi_access5g_5g_cell_peak_view"),
        ("hive__npms__occean_cell", "hive.npms.occean_cell"),
        ("hive__npms__kpi_access4g_all_day_normal", "hive.npms.kpi_access4g_all_day_normal"),
        ("hive__netbi__f_location_new", "hive.netbi.f_location_new"),
        ("hive__gnoc__gnoc", "hive.gnoc.gnoc"),
        ("hive__gnoc__cat_department", "hive.gnoc.cat_department"),
        ("hive__gnoc__icms_maintain_calendar", "hive.gnoc.icms_maintain_calendar"),
        ("hive__gnoc__od_history", "hive.gnoc.od_history"),
        ("hive__aaa__authentication", "hive.aaa.authentication"),
        ("hive__aaa__accounting", "hive.aaa.accounting"),
        ("hive__aaa__ftth_account_pppoe", "hive.aaa.ftth_account_pppoe"),
        ("mysql_datamon__data_monitoring__groups", "mysql_datamon.data_monitoring.groups"),
        ("mysql_datamon__data_monitoring__usersinarea_blacklist_enodeb_id", "mysql_datamon.data_monitoring.usersinarea_blacklist_enodeb_id"),
        ("mysql_datamon__data_monitoring__usersinarea_blacklist", "mysql_datamon.data_monitoring.usersinarea_blacklist"),
    ]
    for old, new in replacements:
        s = s.replace(old, new)
    return s

def main():
    print("Testing Easy and Medium cases against DuckDB...")
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)

    for cid, q, dom, sql, tbls, sk in EASY_CASES + MEDIUM_CASES:
        res = con.execute(sql).fetchall()
        assert len(res) > 0, f"{cid} returned 0 rows!"

    print(f"All {len(EASY_CASES)} Easy and {len(MEDIUM_CASES)} Medium cases passed!")

    # Write cases.py
    cases_py_path = PROJECT_DIR / "benchmark" / "cases.py"
    lines = [
        '"""',
        'cases.py',
        '========',
        'Khai báo 100 benchmark cases tiếng Việt (20 Easy, 30 Medium, 50 Hard)',
        'cho VTNet Mini Data Platform, bao phủ toàn bộ các domain cốt lõi:',
        '- 50 Hard cases được chia đều theo 8 năng lực nghiệp vụ nâng cao',
        'kèm Gold SQL cho DuckDB và Trino reference.',
        '"""',
        '',
        'def get_benchmark_cases():',
        '    cases = []',
        '',
        '    # =========================================================================',
        '    # 20 EASY CASES (E001 - E020)',
        '    # =========================================================================',
        '    easy_specs = [',
    ]

    for cid, q, dom, sql, tbls, sk in EASY_CASES:
        sql_t = make_trino_sql(sql)
        lines.append("        (")
        lines.append(f"            {repr(cid)},")
        lines.append(f"            {repr(q)},")
        lines.append(f"            {repr(dom)},")
        lines.append(f"            {repr(sql)},")
        lines.append(f"            {repr(sql_t)},")
        lines.append(f"            {repr(tbls)},")
        lines.append(f"            {repr(sk)},")
        lines.append("        ),")

    lines.append("    ]")
    lines.append("")
    lines.append("    for cid, q, dom, sql_d, sql_t, req_t, skills in easy_specs:")
    lines.append("        cases.append({")
    lines.append('            "id": cid,')
    lines.append('            "question": q,')
    lines.append('            "difficulty": "easy",')
    lines.append('            "domain": dom,')
    lines.append('            "gold_sql_duckdb": sql_d,')
    lines.append('            "gold_sql_trino": sql_t,')
    lines.append('            "required_tables": req_t,')
    lines.append('            "skills": skills,')
    lines.append("        })")
    lines.append("")
    lines.append("    # ==========================================================================")
    lines.append("    # 30 MEDIUM CASES (M001 - M030)")
    lines.append("    # ==========================================================================")
    lines.append("    medium_specs = [")

    for cid, q, dom, sql, tbls, sk in MEDIUM_CASES:
        sql_t = make_trino_sql(sql)
        lines.append("        (")
        lines.append(f"            {repr(cid)},")
        lines.append(f"            {repr(q)},")
        lines.append(f"            {repr(dom)},")
        lines.append(f"            {repr(sql)},")
        lines.append(f"            {repr(sql_t)},")
        lines.append(f"            {repr(tbls)},")
        lines.append(f"            {repr(sk)},")
        lines.append("        ),")

    lines.append("    ]")
    lines.append("")
    lines.append("    for cid, q, dom, sql_d, sql_t, req_t, skills in medium_specs:")
    lines.append("        cases.append({")
    lines.append('            "id": cid,')
    lines.append('            "question": q,')
    lines.append('            "difficulty": "medium",')
    lines.append('            "domain": dom,')
    lines.append('            "gold_sql_duckdb": sql_d,')
    lines.append('            "gold_sql_trino": sql_t,')
    lines.append('            "required_tables": req_t,')
    lines.append('            "skills": skills,')
    lines.append("        })")
    lines.append("")
    lines.append("    # ==========================================================================")
    lines.append("    # 50 HARD CASES (H001 - H050) - 8 NHÓM NĂNG LỰC NGHIỆP VỤ THỰC TẾ")
    lines.append("    # ==========================================================================")
    lines.append("    try:")
    lines.append("        from benchmark.hard_cases_data import HARD_SPECS")
    lines.append("    except ImportError:")
    lines.append("        from hard_cases_data import HARD_SPECS")
    lines.append("")
    lines.append("    for cid, q, dom, sql_d, sql_t, req_t, skills in HARD_SPECS:")
    lines.append("        cases.append({")
    lines.append('            "id": cid,')
    lines.append('            "question": q,')
    lines.append('            "difficulty": "hard",')
    lines.append('            "domain": dom,')
    lines.append('            "gold_sql_duckdb": sql_d,')
    lines.append('            "gold_sql_trino": sql_t,')
    lines.append('            "required_tables": req_t,')
    lines.append('            "skills": skills,')
    lines.append("        })")
    lines.append("")
    lines.append("    return cases")
    lines.append("")

    with open(cases_py_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Successfully generated clean {cases_py_path}!")

if __name__ == "__main__":
    main()
