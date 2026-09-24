# 01 — Plan V1 so với thực tế

Nguồn plan: `vtnet-mini-plan/README.md`, `02_schema_table_plan.md`, `03_synthetic_data_plan.md`, `04_benchmark_plan.md`.
Nguồn số liệu thực tế: `outputs/review_checks.json`.

## Schema và bảng

| Hạng mục | Plan | Thực tế | Đánh giá |
|---|---|---|---|
| Tổng số bảng | 120–160 | 148 (123 executable, 25 metadata-only) | ✅ |
| Network KPI/5G | ≥ 20 (30–45) | 30 (`npms`) | ✅ |
| Alarm | ≥ 20 | 25 (`gnoc`) | ✅ |
| FBB | ≥ 20 | 25 (`fbb` 22 + `aaa` 3) | ✅ |
| Data Monitoring | ≥ 20 | 25 (`data_monitoring`) | ✅ |
| Common/Location | 15–25 | 18 (`netbi` 10 + `geolocation` 8) | ✅ |
| Noisy metadata | 20–50 | 25 (`pm_counter`) | ✅ |
| Tên bảng | Danh sách tự đặt | Tên thật từ OM (`gnoc.gnoc`, `gnoc.od_history`, `aaa.accounting`…) | ✅ Tốt hơn plan; cần cập nhật lại tài liệu plan cho khớp |
| Join paths | — | 17 trong `relationships.json` | ⚠️ Ít so với 148 bảng; cần kiểm tra cardinality |

## Dữ liệu

| Hạng mục | Plan | Thực tế | Đánh giá |
|---|---|---|---|
| Tổng dòng | 1M–3M | **1.770** | ❌ |
| Dòng/bảng | — | Trung vị 5, lớn nhất 487 | ❌ |
| Số cell | 5k–20k | **63** | ❌ |
| Khoảng thời gian | 2026-06-01 → 2026-08-31 | 2026-08-01 → 2026-08-20 | ❌ Không đủ cho câu weekly/monthly, so sánh 7 ngày với 7 ngày trước |
| Độ phân giải giờ | `YYYY-MM-DD-HH` đủ 24 giờ | 2 khung giờ | ❌ |
| Bẫy A–H | Có | Có, validation PASS | ✅ Logic đúng |
| Tỷ lệ bẫy | Không nêu | 84% số cell | ❌ Phi thực tế |
| Seed | 20260923 | 20260923 | ✅ |

## Benchmark

| Hạng mục | Plan | Thực tế | Đánh giá |
|---|---|---|---|
| 100 câu, 20/30/50 | Có | Có | ✅ |
| Gold chạy được | 100/100 | 100/100, không câu nào rỗng | ✅ |
| `gold_sql_presto` + `gold_sql_duckdb` | Có | `gold_sql_trino` + `gold_sql_duckdb` | ✅ |
| Hard: Ambiguous metric/table | 5 | Không có nhãn | ❌ |
| Hard: No-answer/insufficient | 5 | 0 | ❌ |
| Domain | KPI 39, Alarm 21, FBB 18, DM 15, Cross 7 | KPI 5G 38 + 4G 5, Alarm 23, FBB 22, **DM 5**, Location 7 | ⚠️ Data Monitoring thiếu nhiều so với plan (5 so với 15) |
| ≥ 5 case chọn sai bảng do metadata nhiễu | Có | Chưa gắn nhãn, không kiểm chứng được | ⚠️ |
| Diagnostic (`used_tables`, `wrong_grain_risk`…) | Có | Evaluator chỉ có `VALUE_MISMATCH` / `EXECUTION_ERROR` | ⚠️ |

## Đánh giá và tích hợp

| Hạng mục | Plan | Thực tế | Đánh giá |
|---|---|---|---|
| Kết quả NL2SQL | Chạy hệ thống thật | `predictions.jsonl` sinh bằng cách cài lỗi vào gold | ❌ |
| Pipeline | Retrieve → generate → execute → compare | `DuckDBRuntime` trong `backend/services/runtime_service.py`: prompt + sqlglot rewrite + self-heal, **không dùng `src/t2s`** | ❌ |
| Gói OM | Có | `om_ingest/` (service, database, schema, table, column, tag, glossary, owner, domain) | ✅ |
| Mutation test | Không có trong plan | 152/152 mutant thô bị phát hiện | ✅ Điểm cộng; cần thêm mutant tinh vi |
