# Implementation Checklist

## Phase 0: Chốt Scope

- [ ] Chốt tên thư mục triển khai: `sample data/synthetic/vtnet-mini/`
- [ ] Chốt engine local: DuckDB.
- [ ] Chốt benchmark: 100 cases.
- [ ] Chốt domains: Network KPI/5G, Alarm, FBB, Data Monitoring.
- [ ] Chốt ETL_DATE mặc định: `2026-08-20`.
- [ ] Chốt seed generator: `20260923`.

## Phase 1: Parse Excel OM

- [ ] Đọc workbook `VTNet-presto-OM.xlsx`.
- [ ] Trích `database`, `databaseSchema`, `table`, `column`.
- [ ] Tạo table inventory theo domain.
- [ ] Tạo thống kê tables/schema.
- [ ] Chọn 120-160 tables cho v1.
- [ ] Đánh dấu bảng executable và metadata-only.
- [ ] Xuất `metadata/source_om_inventory.json`.

Output:

```text
metadata/source_om_inventory.json
metadata/selected_tables.csv
metadata/selected_columns.csv
```

## Phase 2: Thiết Kế Schema Và DDL

- [ ] Tạo DDL DuckDB cho bảng core.
- [ ] Tạo DDL Trino reference.
- [ ] Chuẩn hóa naming cho DuckDB nếu cần, ví dụ `hive__npms__table`.
- [ ] Lưu mapping giữa FQN production và table name local.
- [ ] Khai báo primary grain cho từng bảng.
- [ ] Khai báo join path chính.

Output:

```text
generated/ddl_duckdb.sql
generated/ddl_trino_reference.sql
generated/table_name_mapping.json
generated/relationships.json
```

## Phase 3: Synthetic Data Generator

- [ ] Sinh location dimensions.
- [ ] Sinh cell/site inventory.
- [ ] Sinh KPI 5G/4G.
- [ ] Sinh alarm lifecycle.
- [ ] Sinh FBB subscriber/session/billing/QoE.
- [ ] Sinh Data Monitoring jobs/freshness/DQ.
- [ ] Cài trap cases cho hard benchmark.
- [ ] Load vào DuckDB.
- [ ] Validate row counts và join integrity.

Output:

```text
generated/vtnet.duckdb
generated/counts.json
generated/validation_report.json
generated/data/
```

## Phase 4: Metadata Package

- [ ] Tạo catalog metadata từ Excel OM + curated descriptions.
- [ ] Tạo tags/glossary.
- [ ] Tạo owners/domains giả nhưng hợp lý.
- [ ] Tạo OM ingest package.
- [ ] Tạo README hướng dẫn chuyển lên VM.

Output:

```text
metadata/catalog.json
metadata/schema_catalog.json
om_ingest/*.jsonl
om_ingest/ingest_config_template.yaml
```

## Phase 5: Benchmark 100 Cases

- [ ] Viết 20 easy cases.
- [ ] Viết 30 medium cases.
- [ ] Viết 50 hard cases.
- [ ] Mỗi case có `gold_sql_duckdb`.
- [ ] Mỗi case hard có `skills`.
- [ ] Chạy build để tạo expected answers.
- [ ] Chạy evaluator với gold SQL, yêu cầu 100/100 pass.

Output:

```text
benchmark/questions.csv
benchmark/cases.jsonl
benchmark/answers.jsonl
benchmark/report.json
```

## Phase 6: OpenMetadata VM Integration

- [ ] Copy `om_ingest/` lên VM.
- [ ] Import service/database/schema/table/column.
- [ ] Import tags/glossary.
- [ ] Validate search queries.
- [ ] Ghi lại endpoint/config cần cho NL2SQL system.

Output:

```text
reports/openmetadata_search_validation.md
reports/openmetadata_ingest_result.json
```

## Phase 7: NL2SQL Evaluation

- [ ] Chạy hệ thống NL2SQL với 100 câu hỏi.
- [ ] Lưu predictions.
- [ ] Chạy evaluator.
- [ ] Phân loại lỗi:
  - sai table retrieval
  - sai column
  - sai filter date
  - sai aggregation grain
  - sai anti-join
  - SQL dialect error
- [ ] Tạo report cải tiến.

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
