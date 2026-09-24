# Implementation Checklist

## Phase 0: Chốt Scope

- [x] Chốt tên thư mục triển khai: `sample data/synthetic/vtnet-mini/`
- [x] Chốt engine local: DuckDB.
- [x] Chốt benchmark: 100 cases (20 Easy / 30 Medium / 50 Hard).
- [x] Chốt domains: Network KPI/5G, Alarm, FBB, Data Monitoring.
- [x] Chốt ETL_DATE mặc định: `2026-08-20`.
- [x] Chốt seed generator: `20260923`.

## Phase 1: Parse Excel OM

- [x] Đọc workbook `VTNet-presto-OM.xlsx`.
- [x] Trích `database`, `databaseSchema`, `table`, `column`.
- [x] Tạo table inventory theo domain.
- [x] Tạo thống kê tables/schema.
- [x] Chọn 120-160 tables cho v1. (Đã chọn 148 tables: 123 executable, 25 metadata-only).
- [x] Đánh dấu bảng executable và metadata-only.
- [x] Xuất `metadata/source_om_inventory.json`.

Output:

```text
metadata/source_om_inventory.json
metadata/selected_tables.csv
metadata/selected_columns.csv
```

## Phase 2: Thiết Kế Schema Và DDL

- [x] Tạo DDL DuckDB cho bảng core. (Đã tạo 148 bảng và verify 148/148 pass trên DuckDB in-memory).
- [x] Tạo DDL Trino reference. (Đã tạo cú pháp 3 phần catalog.schema.table format PARQUET).
- [x] Chuẩn hóa naming cho DuckDB nếu cần, ví dụ `hive__npms__table`. (Chuẩn catalog__schema__table).
- [x] Lưu mapping giữa FQN production và table name local. (Đã tạo table_name_mapping.json).
- [x] Khai báo primary grain cho từng bảng. (Đầy đủ grain theo giờ, ngày, dimension, event).
- [x] Khai báo join path chính. (Đã xây dựng relationships.json với 20 join paths chính).

Output:

```text
generated/ddl_duckdb.sql
generated/ddl_trino_reference.sql
generated/table_name_mapping.json
generated/relationships.json
```

## Phase 3: Synthetic Data Generator

- [x] Sinh location dimensions. (Đã nạp 16 tỉnh, 4 khu vực vào f_location_new).
- [x] Sinh cell/site inventory. (Đã nạp site, cell inventory và occean_cell exclusion).
- [x] Sinh KPI 5G/4G. (Đầy đủ kpi_access5g_5g_cell_peak_view và kpi_access4g_all_day_normal).
- [x] Sinh alarm lifecycle. (GNOC alarms, departments, maintenance calendar, od_history).
- [x] Sinh FBB subscriber/session/billing/QoE. (AAA PPPoE accounts, authentication, accounting logs).
- [x] Sinh Data Monitoring jobs/freshness/DQ. (Blacklist, groups, monitoring configs).
- [x] Cài trap cases cho hard benchmark. (Cài đặt hoàn chỉnh 8 nhóm trap A-H, test ground-truth 100% pass).
- [x] Load vào DuckDB. (Tạo thành công file vtnet.duckdb 56MB cho 148 bảng).
- [x] Validate row counts và join integrity. (Đã xuất counts.json và validation_report.json với kết quả PASS).

Output:

```text
generated/vtnet.duckdb
generated/counts.json
generated/validation_report.json
generated/data/
```

## Phase 4: Metadata Package

- [x] Tạo catalog metadata từ Excel OM + curated descriptions. (Đã tạo metadata/catalog.json và schema_catalog.json).
- [x] Tạo tags/glossary. (Đã tạo tags.jsonl và glossary_terms.jsonl).
- [x] Tạo owners/domains giả nhưng hợp lý. (Đã tạo domains.jsonl và owners.jsonl với 4 team chủ quản và 6 domain viễn thông).
- [x] Tạo OM ingest package. (Đầy đủ om_ingest/ với 8 file .jsonl, service.json, manifest.json, ingest_config_template.yaml).
- [x] Tạo README hướng dẫn chuyển lên VM. (Đã tạo om_ingest/README.md chi tiết 3 bước import).

Output:

```text
metadata/catalog.json
metadata/schema_catalog.json
om_ingest/*.jsonl
om_ingest/ingest_config_template.yaml
```

## Phase 5: Benchmark 100 Cases

- [x] Viết 20 easy cases.
- [x] Viết 30 medium cases.
- [x] Viết 50 hard cases.
- [x] Mỗi case có `gold_sql_duckdb`.
- [x] Mỗi case hard có `skills`.
- [x] Chạy build để tạo expected answers.
- [x] Chạy evaluator với gold SQL, yêu cầu 100/100 pass.
- [x] Chạy Mutation Testing (152 mutations across 5 types), đạt 100.0% Kill Rate (0 survived).

Output:

```text
benchmark/questions.csv
benchmark/cases.jsonl
benchmark/answers.jsonl
benchmark/report.json
reports/mutation_test_report.json
```

## Phase 6: OpenMetadata VM Integration

- [x] Copy `om_ingest/` lên VM.
- [x] Import service/database/schema/table/column.
- [x] Import tags/glossary.
- [x] Validate search queries.
- [x] Ghi lại endpoint/config cần cho NL2SQL system.

Output:

```text
reports/openmetadata_search_validation.md
reports/openmetadata_ingest_result.json
```

## Phase 7: NL2SQL Evaluation

- [x] Chạy hệ thống NL2SQL với 100 câu hỏi.
- [x] Lưu predictions.
- [x] Chạy evaluator.
- [x] Phân loại lỗi:
  - sai table retrieval
  - sai column
  - sai filter date
  - sai aggregation grain
  - sai anti-join
  - SQL dialect error
- [x] Tạo report cải tiến.

Output:

```text
benchmark/predictions.jsonl
benchmark/evaluation_report.json
reports/nl2sql_error_analysis.md
```

## Milestone

| Milestone | Kết quả |
| --- | --- |
| M0 | Plan docs hoàn tất |
| M1 | Parse Excel OM và chọn table inventory |
| M2 | DuckDB schema + generator chạy được |
| M3 | 100 benchmark cases pass với gold SQL |
| M4 | OM ingest package sẵn sàng |
| M5 | OM VM search validation pass |
| M6 | NL2SQL evaluation report đầu tiên |

## Ưu Tiên Làm Trước

Thứ tự nên làm:

1. Network KPI/5G với query hard mẫu.
2. Location dimensions.
3. Alarm.
4. Data Monitoring.
5. FBB.
6. Noisy metadata.

Lý do: Network KPI/5G là domain có query production-style rõ nhất, giúp kiểm tra nhanh toàn bộ pipeline từ data đến benchmark.
