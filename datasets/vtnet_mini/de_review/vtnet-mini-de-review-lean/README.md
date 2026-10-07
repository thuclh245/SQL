# VTNet Mini — Lean Benchmark Review

Gói tối giản này dành cho Data Engineer review **thiết kế benchmark**, không nhằm tái lập toàn bộ pipeline.

## Nội dung

- `cases.jsonl`: 100 câu hỏi, mức độ, domain, gold SQL DuckDB/Trino, bảng cần dùng và kỹ năng SQL.
- `questions.csv`: bản câu hỏi gọn để đọc/lọc bằng spreadsheet.
- `ddl_duckdb.sql`: schema thực thi, tên bảng đã được chuẩn hóa cho DuckDB.
- `ddl_trino_reference.sql`: schema tham chiếu theo dialect Trino/production.
- `relationships.json`: 17 join paths giữa các bảng.
- `table_name_mapping.json`: ánh xạ tên production sang tên DuckDB.
- `catalog_summary.csv`: danh sách bảng, domain, grain, số cột và trạng thái executable.

## Đề nghị chuyên gia đánh giá

1. Câu hỏi có rõ nghĩa, đúng nghiệp vụ và đủ thông tin để viết SQL không?
2. Gold SQL có thực sự trả lời đúng câu hỏi không?
3. SQL DuckDB và SQL Trino có tương đương về ngữ nghĩa không?
4. Bảng, cột, join key và grain được chọn có hợp lý không?
5. Nhãn easy/medium/hard và danh sách skills có phản ánh độ khó thật không?
6. Phân bố 100 câu hỏi có đủ đa dạng về domain, join, filter, aggregation, window và time logic không?
7. Có câu nào mơ hồ hoặc có nhiều SQL đúng nhưng gold SQL đang giả định duy nhất một cách diễn giải không?

## Lưu ý phạm vi

Gói này cố ý không chứa database, dữ liệu synthetic, evaluator hay kết quả model. Nếu cần audit tính tái lập và khả năng chống `lucky match`, sử dụng gói đầy đủ `vtnet-mini-de-review-20260924`.
