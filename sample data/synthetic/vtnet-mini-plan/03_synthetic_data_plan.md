# Synthetic Data Plan

## Mục Tiêu Dữ Liệu

Dữ liệu synthetic phải giúp chấm NL2SQL bằng result thật. Vì vậy không sinh random hoàn toàn. Mỗi domain cần có dữ liệu nền, dữ liệu biên và dữ liệu bẫy để bắt các lỗi SQL thường gặp.

Các lỗi cần bắt:

- Chọn sai bảng.
- Chọn sai metric.
- Quên filter thời gian.
- Quên `country = 'VNM'`.
- Quên cast string metric sang số.
- Đếm raw rows thay vì đếm object sau grouping.
- Quên anti-join blacklist/exclusion.
- Sai cấp aggregation province/area/network.
- Join dimension gây duplicate.

## Time Range

V1 nên dùng khoảng thời gian đủ dài để có weekly/monthly case:

```text
date range: 2026-06-01 đến 2026-08-31
primary ETL_DATE cho hard case: 2026-08-20
timezone giả định: Asia/Bangkok
date_hour format production-like: YYYY-MM-DD-HH
```

Query mẫu dùng `${ETL_DATE}` và window 7 ngày. Vì vậy generator phải tạo dữ liệu rõ ràng cho:

```text
2026-08-14-00 đến 2026-08-20-00
```

## Location Data

Dimension địa bàn cần đủ nhiều để test aggregate:

```text
country: VNM
area: 4 khu vực
province: 12-20 tỉnh
district: 60-120 huyện
site: 1k-5k sites
cell: 5k-20k cells
```

`hive.netbi.f_location_new` phải unique theo `province_code` trong v1 để tránh duplicate kết quả sau join.

Các cột tối thiểu:

```text
country
area_code
area_name
province_code
province_name
district_code
district_name
```

## Network KPI/5G Data

`hive.npms.kpi_access5g_5g_cell_peak_view` là bảng quan trọng nhất.

Cột tối thiểu:

```text
country
date_hour
province_code
area_code
district_code
site_id
object_id
cell_name
vendor
technology
nr_ps_traffic_total_gb
dl_user_throughput_mbps
ul_user_throughput_mbps
availability_pct
latency_ms
packet_loss_pct
handover_success_rate
drop_call_rate
```

Các metric numeric nên lưu dạng text ở một số bảng production-style để test `CAST`:

```text
nr_ps_traffic_total_gb: text
dl_user_throughput_mbps: text
```

### Trap Cases Cho Query Mẫu

Generator phải cài sẵn các nhóm cell:

| Nhóm | Điều kiện | Expected |
| --- | --- | --- |
| A | throughput < 5 trong 4/7 ngày, traffic > 0 | được tính |
| B | throughput < 5 đúng 3/7 ngày | không tính |
| C | throughput = 0 | không tính |
| D | traffic = 0 | không tính |
| E | throughput >= 5 | không tính |
| F | nằm trong `occean_cell` | không tính |
| G | `country != 'VNM'` | không tính |
| H | thiếu province mapping | vẫn giữ row do left join |

## Alarm Data

Alarm domain cần tạo event lifecycle:

```text
alarm raised -> acknowledged -> cleared
alarm -> ticket -> work_order -> root_cause
```

Cột tối thiểu cho `hive.gnoc.network_alarm`:

```text
alarm_id
country
date_hour
province_code
area_code
district_code
site_id
cell_id
alarm_code
alarm_name
severity
vendor
raised_time
cleared_time
status
```

Trap cases:

- Alarm chưa clear.
- Alarm quá SLA.
- Alarm severity high nhưng đã clear đúng hạn.
- Nhiều alarm cùng site để test count distinct site/cell.
- Ticket không có work order.
- Work order closed nhưng alarm chưa clear.

## FBB Data

FBB cần mô phỏng thuê bao, account PPPoE, session và QoE.

Cột tối thiểu:

```text
subscriber_id
customer_id
account_id
province_code
area_code
district_code
package_code
status
activation_date
account_name
session_start
session_end
traffic_gb
download_mbps
upload_mbps
qoe_score
```

Trap cases:

- Thuê bao active nhưng không có session 7 ngày.
- PPPoE account có nhiều session trong ngày.
- Speed test thấp nhưng package thấp, không phải anomaly.
- Billing overdue nhưng vẫn active.
- Churn signal do QoE giảm nhiều ngày.

## Data Monitoring Data

Data Monitoring cần test câu hỏi về freshness, null rate, error và campaign.

Cột tối thiểu:

```text
table_fqn
job_name
run_id
run_date
status
started_at
finished_at
row_count
expected_row_count
freshness_hours
null_rate
error_code
owner
```

Trap cases:

- Job failed nhưng retry success.
- Freshness vi phạm SLA.
- Null rate tăng bất thường.
- Table có access cao nhưng metadata thiếu owner.
- Campaign active nhưng không có result.

## Data Volume V1

Khuyến nghị:

| Nhóm | Rows |
| --- | ---: |
| Location/dimension | 1k-20k |
| Network KPI | 500k-1.5M |
| Alarm | 100k-500k |
| FBB | 200k-800k |
| Data Monitoring | 50k-200k |
| Noisy tables | ít hoặc metadata-only |

Tổng v1:

```text
1M-3M rows
```

## Reproducibility

Generator cần cố định seed:

```text
seed = 20260923
```

Mọi expected result trong benchmark phải sinh lại được từ cùng seed.

## Output Dự Kiến

```text
sample data/synthetic/vtnet-mini/generated/
  vtnet.duckdb
  ddl_duckdb.sql
  ddl_trino_reference.sql
  counts.json
  validation_report.json
  data/
    hive/npms/*.csv
    hive/netbi/*.csv
    hive/gnoc/*.csv
    hive/fbb/*.csv
    mysql_datamon/data_monitoring/*.csv
  metadata/
    catalog.json
    schema_catalog.json
    relationships.json
```
