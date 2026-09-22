# Benchmark text-to-SQL viễn thông

100 câu hỏi tiếng Việt: 20 dễ, 20 vừa, 30 khó, 30 cực khó. Mỗi câu có SQL chuẩn cho SQLite và bản chuyển tên bảng sang Trino/Hive, cùng đáp án **đã chạy thực tế** trên `../generated/telecom.sqlite`.

| Tệp | Nội dung |
| --- | --- |
| `questions.csv` | Danh sách câu hỏi và độ khó, tiện giao cho hệ thống cần đánh giá |
| `cases.jsonl` | Câu hỏi, SQL chuẩn hai dialect, bảng liên quan, số dòng và SHA-256 đáp án |
| `answers.jsonl` | Tên cột và toàn bộ các dòng kết quả từ SQLite |
| `report.json` | Tổng kiểm tra: 100/100 SQL chạy được, không có kết quả rỗng |
| `cases.py` | Nguồn chỉnh sửa câu hỏi và SQL |
| `build.py` | Chạy lại tất cả SQL và sinh các tệp benchmark |
| `evaluate.py` | Chấm SQL dự đoán theo kết quả thực thi |

Chạy lại sau khi sinh lại dữ liệu:

```bash
python3 'sample data/synthetic/benchmark/build.py'
```

Để chấm một hệ thống, tạo `predictions.jsonl` với mỗi dòng có `id` và `sql` SQLite, ví dụ:

```json
{"id":"E001","sql":"SELECT COUNT(*) AS n FROM customer__subscriber"}
```

```bash
python3 'sample data/synthetic/benchmark/evaluate.py' predictions.jsonl
```

Điểm là tỷ lệ câu có tập dòng đúng, không phụ thuộc thứ tự dòng hoặc tên alias; số thực được làm tròn 6 chữ số thập phân. Câu thiếu hoặc SQL lỗi được tính sai. Bộ câu hỏi dùng cả 20 schema nhưng tập trung vào 32 bảng lõi có quan hệ nghiệp vụ rõ ràng. Đây là bộ kiểm tra trên **dữ liệu tổng hợp**; giá trị và quy tắc kinh doanh cần xác nhận trước khi dùng làm chuẩn trên hệ thống công ty. Bản SQL Trino mới chuyển cách gọi tên bảng và **chưa được chạy trên Trino**; đáp án thực thi và bộ chấm dùng SQLite.
