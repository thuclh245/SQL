# VTNet Mini — Data Engineering Review Guide

## Mục tiêu review

Gói này phục vụ đánh giá độc lập benchmark NL2SQL VTNet Mini theo năm trục:

1. Tính đại diện và độ sạch của metadata/schema.
2. Tính tái lập của dữ liệu synthetic.
3. Chất lượng, độ phủ và độ khó của 100 benchmark cases.
4. Tính đúng đắn của gold SQL, expected answers và evaluator.
5. Khả năng chống `lucky match` thông qua adversarial data và mutation tests.

## Thống kê nhanh

- 148 bảng, 5.864 cột, 17 join paths.
- 1.770 dòng dữ liệu synthetic trong DuckDB.
- 100 câu hỏi: 20 easy, 30 medium, 50 hard.
- Seed sinh dữ liệu: `20260923`.
- Validation dữ liệu hiện tại: `PASSED`.
- Evaluation hiện tại: 93/100, nhưng đây là kết quả của `predictions.jsonl`, không phải chứng nhận chất lượng benchmark.

## Thứ tự review khuyến nghị

### 1. Đọc thiết kế và phạm vi

- `design/README.md`
- `design/01_architecture.md`
- `design/02_schema_table_plan.md`
- `design/03_synthetic_data_plan.md`
- `design/04_benchmark_plan.md`
- `design/06_implementation_checklist.md`

### 2. Kiểm tra schema và metadata

- `metadata/catalog.json`: catalog đầy đủ, mô tả bảng/cột và key candidates.
- `metadata/schema_catalog.json`: schema catalog phục vụ grounding.
- `generated/ddl_duckdb.sql`: DDL có thể thực thi.
- `generated/ddl_trino_reference.sql`: SQL dialect tham chiếu cho môi trường đích.
- `generated/relationships.json`: 17 join paths được khai báo.
- `generated/table_name_mapping.json`: ánh xạ production FQN sang bảng DuckDB.

Các câu hỏi chính: schema có đại diện cho workload thực không; kiểu dữ liệu có bị đơn giản hóa quá mức không; join path có đúng cardinality và business grain không; 25 bảng `is_executable=false` có gây nhiễu hợp lý không.

### 3. Kiểm tra dữ liệu synthetic

- `generated/vtnet.duckdb`: database thực thi chuẩn.
- `scripts/generate_synthetic_data.py`: logic và seed sinh dữ liệu.
- `generated/counts.json`: số dòng từng bảng.
- `generated/validation_report.json`: kiểm tra các nhóm bẫy A–H.

Các câu hỏi chính: dữ liệu có deterministic không; giá trị NULL/duplicate/zero/boundary có đủ; từng filter/join/aggregation quan trọng có làm thay đổi kết quả; kích thước mẫu có tạo ra shortcut ngoài ý muốn không.

### 4. Kiểm tra benchmark và gold set

- `benchmark/cases.jsonl`: artifact chuẩn gồm câu hỏi, độ khó, domain, gold SQL DuckDB/Trino và bảng bắt buộc.
- `benchmark/questions.csv`: danh sách câu hỏi thuận tiện cho review thủ công.
- `benchmark/answers.jsonl`: expected schema, row count, sample và SHA-256 kết quả.
- `benchmark/cases.py` cùng `benchmark/hard_cases_data.py`: source tạo cases.
- `scripts/build_benchmark.py`: cách sinh gold answers.

Nên lấy mẫu ít nhất 10 case mỗi mức độ và kiểm tra độc lập: câu hỏi có một nghĩa rõ ràng; gold SQL có đúng business intent; DuckDB và Trino SQL tương đương; nhãn độ khó và skills hợp lý; không có data leakage từ tên bảng/cột hoặc template lặp.

### 5. Audit evaluator

- `scripts/evaluate_benchmark.py`: evaluator chính.
- `benchmark/predictions.jsonl`: predictions đã được chấm.
- `benchmark/evaluation_report.json`: kết quả chi tiết.
- `reports/nl2sql_error_analysis.md`: phân tích 7 lỗi hiện tại.
- `scripts/test_benchmark_mutations.py` và `reports/mutation_test_report.json`: mutation testing.

Đặc biệt cần kiểm tra chuẩn hóa kết quả: evaluator hiện giữ nguyên thứ tự/tên cột, chuyển mọi giá trị sang chuỗi rồi sắp xếp row. Cần xác nhận quy tắc này phù hợp với mục tiêu benchmark đối với float precision, NULL, duplicate rows, column aliases và queries có yêu cầu `ORDER BY`.

## Chạy lại tối thiểu

Yêu cầu Python 3. Cài dependency bằng `python3 -m pip install duckdb`.

```bash
python3 scripts/build_benchmark.py
python3 scripts/evaluate_benchmark.py \
  --predictions benchmark/predictions.jsonl \
  --output benchmark/evaluation_report.reproduced.json
python3 scripts/test_benchmark_mutations.py
```

Muốn tái tạo database từ đầu, chạy `python3 scripts/generate_synthetic_data.py` trước. Thao tác này ghi đè `generated/vtnet.duckdb`; nên thực hiện trên bản sao của gói review.

## Tiêu chí chấp nhận đề xuất

- 100% gold SQL DuckDB chạy thành công và kết quả tái lập từ cùng seed.
- Mọi gold SQL Trino đã được parse/lint hoặc chạy trên môi trường Trino tương thích.
- Mọi phép biến đổi làm sai business intent quan trọng đều bị mutation tests phát hiện.
- Không có câu hỏi mơ hồ hoặc có nhiều gold result hợp lệ nhưng evaluator chỉ chấp nhận một biểu diễn.
- Phân bố domain, difficulty, SQL operators và join depth phản ánh workload mục tiêu.
- Không dùng accuracy của một file predictions duy nhất để kết luận benchmark tốt.

## Toàn vẹn gói

Đối chiếu mọi file với `MANIFEST.sha256` trước khi review. `PACKAGE_CONTENTS.txt` liệt kê toàn bộ artifact và kích thước byte.
