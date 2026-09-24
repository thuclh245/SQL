# VTNet Mini Data Platform Plan

Tài liệu này mô tả kế hoạch dựng một môi trường synthetic gần với `VTNet Datalake Presto` để đánh giá hệ thống NL2SQL. Mục tiêu không phải sao chép hệ thống thật, mà là tạo một lát cắt có đủ metadata, schema, dữ liệu, query pattern và hard case giống production để kiểm tra hệ thống có hiểu đúng nghiệp vụ hay không.

Nguồn định hướng chính:

- File OM export: `VTNet-presto-OM.xlsx`
- Query production-style mẫu: `sample data/query.md`
- Benchmark hiện có: `sample data/synthetic/benchmark/`
- OpenMetadata đã có sẵn trên VM, sẽ tích hợp sau

## Quyết Định Chính

| Hạng mục | Quyết định |
| --- | --- |
| Mục tiêu chính | NL2SQL benchmark |
| Lớp hỗ trợ | OpenMetadata search/RAG metadata |
| Engine local | DuckDB trước, vì nhanh và dễ kiểm soát expected result |
| OpenMetadata | Dùng OM thật trên VM sau khi dữ liệu/metadata local ổn |
| Metadata seed | Trích từ Excel OM |
| Domain bắt buộc | Network KPI/5G, Alarm, FBB, Data Monitoring |
| Benchmark v1 | 100 câu: 20 easy, 30 medium, 50 hard |
| Ngôn ngữ câu hỏi | Tiếng Việt |
| Tên catalog/schema/table/column | Giữ gần production |

## Kết Luận Từ Excel OM

Excel OM là metadata export, không phải dữ liệu business rows. Dữ liệu trong đó gồm `database`, `databaseSchema`, `table`, `column`, description, tag, glossary term và data type.

Các thống kê quan trọng từ Excel:

| Metric | Giá trị |
| --- | ---: |
| Database/catalog | 6 |
| Schema | 124 |
| Table rows trong OM | khoảng 8.8k |
| Column rows trong OM | khoảng 296k |
| Min table/schema | 0 |
| Max table/schema | 2,623 |
| Average table/schema | khoảng 70 |
| Median table/schema | 9 |
| P75 table/schema | khoảng 45 |
| P90 table/schema | khoảng 114 |

Phân bố schema thật bị lệch mạnh: đa số schema nhỏ, một số rất lớn. Vì vậy mini platform v1 nên mô phỏng đúng hình dạng này: nhiều schema nhỏ, vài schema vừa/lớn, và một schema noisy để thử khả năng retrieval.

## Bộ File Plan

| File | Nội dung |
| --- | --- |
| `01_architecture.md` | Kiến trúc tổng thể local và VM |
| `02_schema_table_plan.md` | Catalog/schema/table plan chi tiết |
| `03_synthetic_data_plan.md` | Cách sinh dữ liệu synthetic có chủ đích |
| `04_benchmark_plan.md` | Plan 100 benchmark cases |
| `05_openmetadata_plan.md` | Cách chuẩn bị package đưa vào OpenMetadata VM |
| `06_implementation_checklist.md` | Checklist triển khai theo phase |

## Scope V1

Quy mô đề xuất:

```text
4 domain chính
8-12 schema
120-160 tables
1M-3M synthetic rows
100 benchmark questions
```

Trong đó:

- Mỗi domain chính có tối thiểu 20 table.
- Network KPI/5G là domain xương sống vì có query thật mẫu.
- Alarm, FBB và Data Monitoring bổ sung các dạng câu hỏi vận hành, thuê bao và giám sát dữ liệu.
- Một phần metadata-only/noisy tables được dùng để test schema linking và table retrieval.

## Không Làm Trong V1

- Không dùng dữ liệu thật của công ty.
- Không dựng Trino/Presto local ngay từ đầu nếu DuckDB đã đủ để chấm result.
- Không yêu cầu OpenMetadata local vì OM đã có sẵn trên VM.
- Không tạo agent tự query nhiều bước trước khi benchmark NL2SQL ổn định.

## Thành Công Của V1 Là Gì?

V1 được xem là đạt khi:

- DuckDB database chạy được tất cả gold SQL DuckDB.
- Có metadata JSON/YAML đủ để import hoặc map sang OpenMetadata.
- Có 100 câu benchmark với expected result đã chạy thật.
- Hard cases có đủ query pattern như anti-join, 7-day window, cast metric, having, grouping sets hoặc equivalent union.
- Có thể chuyển package lên VM để ingest vào OpenMetadata thật.
