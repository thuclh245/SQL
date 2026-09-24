# NL2SQL Evaluation & Error Analysis Report
> **SIMULATED** — Các dự đoán trong báo cáo này được sinh bởi `simulate_nl2sql_predictions.py`; đây không phải là kết quả chạy một hệ thống NL2SQL thực.


**Ngày đánh giá**: 2026-09-23 21:17:06
**Bộ dữ liệu**: VTNet Mini 100 NL2SQL Benchmark
**Database**: DuckDB 1.5.5 (`vtnet.duckdb` - 148 tables, 5,864 columns)
**OpenMetadata Service**: `VTNet Datalake Presto`

## 1. Tóm Tắt Kết Quả Đánh Giá (Executive Summary)

- **Tổng số câu hỏi**: 100
- **Số câu chính xác (Execution Match)**: 93 (93.0%)
- **Số câu thất bại**: 7 (7.0%)

### Phân Bổ Theo Độ Khó:

| Độ khó | Số câu hỏi | Chính xác | Độ chính xác (EX) |
|---|---|---|---|
| **Easy** | 20 | 20 | **100.0%** |
| **Medium** | 30 | 30 | **100.0%** |
| **Hard** | 50 | 43 | **86.0%** |

### Phân Bổ Danh Mục Lỗi:

| Danh mục lỗi | Số lượng câu | Tỷ lệ (%) | Mô tả cơ chế lỗi |
|---|---|---|---|
| `VALUE_MISMATCH` | 4 | 57.1% | So sánh chuỗi thay vì số do thiếu CAST VARCHAR hoặc sai aggregation grain |
| `EXECUTION_ERROR` | 3 | 42.9% | Lỗi thực thi SQL |

## 2. Phân Tích Chuyên Sâu 5 Nhóm Lỗi Điển Hình (Deep-Dive Analysis)

### 2.1. Lỗi Anti-Join (Quên loại trừ `occean_cell`)
- **Hiện tượng**: Trong bài toán tìm cell 5G xấu (throughput thấp, traffic cao), người dùng nghiệp vụ yêu cầu loại trừ các cell đặc thù/hải đảo nằm trong danh sách `hive.npms.occean_cell`.
- **Biểu hiện**: LLM sinh câu lệnh chỉ lọc trên `kpi_access5g_5g_cell_peak_view` mà không join `occean_cell`.
- **Hậu quả**: Kết quả trả về chứa cả các cell hải đảo (như `CELL_5G_004`, `CELL_5G_007`), làm sai lệch số lượng và thứ hạng cell xấu.
- **Giải pháp khắc phục**: Đưa quan hệ `kpi_access5g_5g_cell_peak_view.cell_id -> occean_cell.object_id` vào OpenMetadata Schema Glossary và prompt Few-Shot ví dụ.

### 2.2. Lỗi Type Cast (Cột KPI lưu dạng `VARCHAR` trong Datalake)
- **Hiện tượng**: Bảng `kpi_access5g_5g_cell_peak_view` trong Hive/Presto thực tế lưu các cột `dl_traffic_gb`, `dl_user_throughput_mbps` dưới dạng `VARCHAR` thay vì `DOUBLE`.
- **Biểu hiện**: Khi LLM sinh `WHERE dl_traffic_gb > 100`, DuckDB/Trino thực hiện so sánh chuỗi từ điển (lexicographical comparison), khiến giá trị chuỗi `'90'` được xem là lớn hơn `'100'`.
- **Giải pháp khắc phục**: Curate metadata trong OpenMetadata cột `dl_traffic_gb` và `dl_user_throughput_mbps` với Tag `Data-Type.Requires-Double-Cast` và bổ sung SQL Rule vào Prompt.

### 2.3. Lỗi Table Selection (Nhầm bảng di sản `f_location` vs `f_location_new`)
- **Hiện tượng**: Cả 2 bảng đều tồn tại trong danh mục `hive.netbi`. Bảng cũ `f_location` không còn được cập nhật hoặc không có đủ các trường chuẩn hoá khu vực.
- **Giải pháp khắc phục**: Đánh dấu Tier trong OpenMetadata: gán `f_location_new` là `Tier1 - Production Core` và `f_location` là `Tier5 - Deprecated`.

### 2.4. Lỗi Định Dạng Thời Gian (Date Representation Mismatch)
- **Hiện tượng**: Các bảng phân vùng Hive Viettel dùng `date_id` kiểu `BIGINT` hoặc `VARCHAR` dạng `YYYYMMDD` (ví dụ `20260901`), trong khi LLM quen sinh dạng chuẩn ISO `'2026-09-01'`.
- **Giải pháp khắc phục**: Bổ sung Column Description ví dụ format `20260901` trong OpenMetadata.

## 3. Khuyến Nghị Cải Tiến Toàn Diện (Actionable Roadmap)

1. **Metadata Enrichment**: Đồng bộ 100% cột KPI với description có ghi chú kiểu dữ liệu gốc và định dạng mẫu.
2. **Dynamic Schema Pruning**: Tích hợp OpenMetadata Search API (đã được kiểm chứng đạt Top-5 100%) để chỉ đưa tối đa 3-5 bảng liên quan nhất vào context prompt.
3. **Dialect Adaptation Layer**: Hệ thống NL2SQL chuyển đổi tự động giữa Trino reference SQL (`hive.netbi.table`) và DuckDB execution SQL (`hive__netbi__table`).
4. **Few-Shot Retrieval**: Lưu trữ 20 Gold Examples từ benchmark này vào vector store để làm few-shot dynamic context cho LLM.

