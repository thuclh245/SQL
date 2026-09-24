# Benchmark Plan

## Mục Tiêu

Benchmark v1 gồm 100 câu hỏi tiếng Việt để đánh giá NL2SQL trên dữ liệu synthetic gần production.

Tỉ lệ:

```text
20 easy
30 medium
50 hard
```

Benchmark phải chấm bằng kết quả thực thi, không chỉ so chuỗi SQL. Một SQL khác gold nhưng trả đúng result vẫn được chấp nhận, miễn không vi phạm policy benchmark.

## Format Case

Mỗi case nên có cấu trúc:

```json
{
  "id": "HARD_NETWORK_001",
  "question": "Tính số cell 5G có throughput user thấp hơn 5 Mbps...",
  "difficulty": "hard",
  "domain": "network_kpi_5g",
  "gold_sql_presto": "...",
  "gold_sql_duckdb": "...",
  "required_tables": [
    "hive.npms.kpi_access5g_5g_cell_peak_view",
    "hive.npms.occean_cell",
    "hive.netbi.f_location_new"
  ],
  "skills": [
    "date_window",
    "cast_numeric",
    "anti_join",
    "having",
    "grouping_sets",
    "location_rollup"
  ],
  "expected_result_sha256": "..."
}
```

## Easy Cases

20 easy cases kiểm tra query đơn giản:

| Nhóm | Số câu | Ví dụ |
| --- | ---: | --- |
| Count/filter | 5 | Đếm số cell 5G tại một tỉnh |
| Top N | 4 | Top 10 cell có traffic cao nhất ngày X |
| Basic aggregate | 4 | Trung bình throughput theo province |
| Simple lookup | 3 | Liệt kê province thuộc area |
| Metadata-aware simple | 4 | Tìm bảng/cột dùng cho throughput hoặc alarm |

Điều kiện easy:

- 1 bảng hoặc join đơn giản 2 bảng.
- Không có nested query.
- Không có window nhiều ngày phức tạp.

## Medium Cases

30 medium cases kiểm tra join và aggregate thật:

| Nhóm | Số câu | Ví dụ |
| --- | ---: | --- |
| Join KPI + location | 6 | Throughput trung bình theo tỉnh |
| Group by nhiều chiều | 5 | Traffic theo ngày và area |
| Alarm + ticket | 5 | Số alarm chưa xử lý theo severity |
| FBB session/billing | 5 | Thuê bao có session thấp và overdue |
| Data monitoring | 5 | Table vi phạm freshness SLA |
| Metric comparison | 4 | So sánh traffic 5G hôm nay và hôm trước |

Điều kiện medium:

- 2-4 bảng.
- Có aggregate.
- Có filter date.
- Có một vài điều kiện business.

## Hard Cases

50 hard cases là phần quan trọng nhất. Cần giống query production-style bạn đưa.

Nhóm hard:

| Nhóm | Số câu | Kỹ năng kiểm tra |
| --- | ---: | --- |
| Bad cell KPI 5G | 12 | 7-day window, having, cast, anti-join |
| Multi-level rollup | 7 | province/area/network, grouping sets hoặc union |
| Alarm SLA/root cause | 8 | lifecycle, SLA, unresolved logic |
| FBB QoE/churn | 7 | multi-day degradation, join subscriber/session/package |
| Data monitoring anomaly | 6 | freshness, retry, null-rate anomaly |
| Ambiguous metric/table | 5 | chọn đúng bảng giữa bảng gần nghĩa |
| No-answer/insufficient | 5 | câu hỏi thiếu dữ kiện hoặc metric không tồn tại |

## Hard Case Template Từ Query Mẫu

Câu hỏi:

```text
Tính số lượng cell 5G có throughput user thấp hơn 5 Mbps trong hơn 3 ngày của 7 ngày gần nhất, có phát sinh traffic, loại trừ cell trong bảng occean_cell, tổng hợp theo tỉnh, khu vực và toàn mạng cho ngày ${ETL_DATE}.
```

SQL production-like dùng pattern:

```text
refresh table
CTE raw_data
date window 7 ngày
CAST metric string sang double
NOT EXISTS exclusion
GROUP BY object_id
HAVING COUNT(*) > 3
GROUPING SETS province/area/network
LEFT JOIN location
```

Skills:

```text
date_window
cast_numeric
anti_join
having_after_group_by_cell
count_bad_cells_not_bad_rows
location_rollup
left_join_dimension
```

## Domain Allocation

| Domain | Easy | Medium | Hard | Total |
| --- | ---: | ---: | ---: | ---: |
| Network KPI/5G | 7 | 10 | 22 | 39 |
| Alarm | 4 | 7 | 10 | 21 |
| FBB | 4 | 6 | 8 | 18 |
| Data Monitoring | 3 | 5 | 7 | 15 |
| Cross-domain/metadata | 2 | 2 | 3 | 7 |
| Total | 20 | 30 | 50 | 100 |

## Evaluation Rules

Evaluator nên chấm:

- SQL chạy thành công.
- Result set đúng, không phụ thuộc thứ tự nếu câu hỏi không yêu cầu order.
- Numeric tolerance cho float.
- Không phạt alias khác tên nếu value đúng.
- Có thể kiểm tra required table usage ở chế độ diagnostic, nhưng điểm chính là result.

Nên lưu thêm diagnostic:

```text
used_tables
missing_required_tables
wrong_grain_risk
empty_result
runtime_error
row_count_mismatch
value_mismatch
```

## Output Files

```text
sample data/synthetic/vtnet-mini/benchmark/
  README.md
  questions.csv
  cases.jsonl
  answers.jsonl
  report.json
  cases.py
  build.py
  evaluate.py
```

## Success Criteria

- 100/100 gold SQL DuckDB chạy được.
- Không có expected result rỗng trừ các no-answer cases có chủ đích.
- Mỗi hard case ghi rõ skills được test.
- Có ít nhất 10 hard cases rất gần query production mẫu.
- Có ít nhất 5 case kiểm tra chọn sai bảng do metadata nhiễu.
