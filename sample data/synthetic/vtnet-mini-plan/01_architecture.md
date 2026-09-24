# Kiến Trúc Mini VTNet Platform

## Mục Tiêu Kiến Trúc

Kiến trúc v1 phục vụ đánh giá NL2SQL. Hệ thống cần trả lời được câu hỏi: khi người dùng hỏi bằng tiếng Việt, model có chọn đúng bảng/cột, hiểu đúng metric, sinh SQL đúng và trả kết quả đúng không?

Vì vậy kiến trúc tách thành hai lớp:

- Local benchmark layer: chạy nhanh, kiểm soát dữ liệu và expected result.
- OpenMetadata layer trên VM: cung cấp search, semantic metadata, glossary và trải nghiệm gần production.

## Local Layer

```text
Excel OM export
    |
    v
OM metadata parser
    |
    +--> selected table inventory
    +--> table/column descriptions
    +--> tags/glossary/domain hints
    |
    v
Synthetic data generator
    |
    +--> CSV/Parquet
    +--> DuckDB database
    +--> metadata JSON
    |
    v
Benchmark builder
    |
    +--> questions.csv
    +--> cases.jsonl
    +--> answers.jsonl
    +--> report.json
    |
    v
Evaluator
```

Local layer không cần OpenMetadata để bắt đầu. Nó cần tạo được dữ liệu, chạy SQL và chấm kết quả.

## VM/OpenMetadata Layer

```text
Synthetic metadata package
    |
    v
OpenMetadata VM
    |
    +--> database service: VTNet Datalake Presto
    +--> catalogs/schemas/tables/columns
    +--> descriptions/tags/glossary
    +--> search/semantic search
    |
    v
NL2SQL system
    |
    +--> retrieve candidate tables/columns
    +--> generate SQL
    +--> execute against DuckDB/Postgres/Trino-compatible data
    +--> compare result with benchmark
```

OpenMetadata là catalog/search layer. Nó không thay thế dữ liệu chạy query. Dữ liệu query vẫn nằm ở DuckDB/Postgres/Trino tùy phase.

## Vì Sao Dùng DuckDB Trước?

DuckDB phù hợp cho v1 vì:

- Không cần service phức tạp.
- Chạy nhanh trên file local.
- Dễ sinh expected result.
- Dễ debug case sai.
- Có thể giữ `gold_sql_presto` song song với `gold_sql_duckdb`.

Những khác biệt cú pháp Presto/DuckDB sẽ được quản lý trong benchmark:

```json
{
  "gold_sql_presto": "...",
  "gold_sql_duckdb": "..."
}
```

Sau này nếu cần giống production hơn, có thể thêm Trino phase mà không phá benchmark.

## Vai Trò Của OpenMetadata

OpenMetadata dùng để kiểm tra phần hệ thống phụ thuộc metadata:

- Search table theo câu hỏi tiếng Việt.
- Search column theo metric như throughput, traffic, alarm, subscriber.
- Dùng description/tag/glossary để chọn đúng bảng.
- Phân biệt bảng gần nghĩa, ví dụ `kpi_cell_throughput_hourly` và `kpi_cell_traffic_hourly`.
- Hỗ trợ semantic context trước khi sinh SQL.

OM không phải nguồn dữ liệu thật trong v1. OM là nguồn metadata.

## Dòng Chảy Một Case NL2SQL

1. Người dùng hỏi: "Tính số cell 5G throughput thấp hơn 5 Mbps trong hơn 3 ngày của 7 ngày gần nhất..."
2. Hệ thống search metadata trong OpenMetadata.
3. Candidate tables được retrieve:
   - `hive.npms.kpi_access5g_5g_cell_peak_view`
   - `hive.npms.occean_cell`
   - `hive.netbi.f_location_new`
4. Model sinh SQL.
5. SQL được normalize hoặc viết ở dialect DuckDB.
6. DuckDB execute.
7. Evaluator so result với `answers.jsonl`.

## Deliverable Kiến Trúc

```text
sample data/synthetic/vtnet-mini/
  ddl/
  data/
  metadata/
  benchmark/
  scripts/
  om_ingest/
```

Tài liệu plan hiện tại nằm ở:

```text
sample data/synthetic/vtnet-mini-plan/
```
