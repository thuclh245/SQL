# VTNet Mini — Review & Kế hoạch V1.1

Ngày review: 2026-09-24
Đối tượng: `sample data/synthetic/vtnet-mini/` và `sample data/synthetic/vtnet-mini-plan/` (nhánh `read_mini_viettel`, commit `42d65de`)

## Kết luận một đoạn

VTNet Mini đạt phần **khung**: 148 bảng, mỗi domain bắt buộc ≥ 20 bảng, tên bảng/cột lấy từ OM thật, bẫy A–H cài đúng, 100/100 gold chạy được, đã có gói ingest OM. Tuy vậy nó **chưa đủ để đo NL2SQL một cách đáng tin**. Dữ liệu nhỏ hơn plan khoảng 1.000 lần, 84% cell trong bảng KPI chính là cell bẫy, câu hỏi bị lộ schema, không có câu no-answer/ambiguous, và gold SQL có lỗi tiềm ẩn mà dữ liệu hiện tại không phát hiện được. Nguyên nhân gốc là **cùng một agent thiết kế dữ liệu, bẫy, câu hỏi và gold mà không có bước kiểm tra chéo**. Kế hoạch V1.1 sửa đúng chỗ đó, đồng thời biến VTNet Mini thành testbed cho đóng góp chính của dự án: **quy ước dữ liệu ngầm + độ tin cậy của metadata + biết từ chối trả lời**.

## Cách đọc

| File | Nội dung | Ai nên đọc |
|---|---|---|
| [01_plan_vs_actual.md](01_plan_vs_actual.md) | So plan V1 với thứ đã build | Tất cả |
| [02_benchmark_findings.md](02_benchmark_findings.md) | Các phát hiện kèm bằng chứng tái lập | DE reviewer, người viết gold |
| [03_plan_v1_1.md](03_plan_v1_1.md) | Kế hoạch chi tiết V1.1 theo phase, deliverable và điều kiện hoàn thành | Người thực hiện |
| [04_conventions_template.yaml](04_conventions_template.yaml) | Template registry quy ước dữ liệu, có ví dụ VTNet | Người làm Phase 2 |
| [05_case_schema_v2.md](05_case_schema_v2.md) | Format case benchmark v2 | Người làm Phase 3 |
| [06_de_review_checklist.md](06_de_review_checklist.md) | Checklist duyệt từng case | DE reviewer |
| [07_v1_1_execution_status.md](07_v1_1_execution_status.md) | Trạng thái thực hiện V1.1, cách kiểm chứng, phát hiện F10–F16, việc còn lại | Tất cả |
| [scripts/reproduce_review_checks.py](scripts/reproduce_review_checks.py) | Tái lập mọi con số trong review | Ai cần kiểm chứng |
| [outputs/review_checks.json](outputs/review_checks.json) | Output của lần chạy script trên | — |

## Tái lập

```bash
pip install duckdb
python "sample data/synthetic/vtnet-mini-review/scripts/reproduce_review_checks.py"
```

Script chỉ đọc `vtnet.duckdb` ở chế độ read-only.

## Tóm tắt phát hiện

| # | Phát hiện | Mức độ | Chi tiết |
|---|---|---|---|
| F1 | Dữ liệu 1.770 dòng (plan: 1M–3M), 63 cell, 20 ngày, 2 khung giờ | Cao | 01, 02 §1 |
| F2 | 53/63 cell (84%) trong `kpi_access5g_5g_cell_peak_view` là cell bẫy | Cao | 02 §1 |
| F3 | Gold H002 sai khi có ngày trống hoặc nhiều khung giờ/ngày, nhưng dữ liệu hiện tại không lộ ra | Cao | 02 §2 |
| F4 | H012: câu hỏi hỏi theo từng phòng ban, gold trả tổng toàn bảng cho mọi phòng ban | Cao | 02 §3 |
| F5 | 39/100 câu chứa tên bảng/cột; 9 câu chứa gợi ý cú pháp SQL | Trung bình–Cao | 02 §4 |
| F6 | Không có câu no-answer/ambiguous (plan có 5 + 5) | Cao | 02 §5 |
| F7 | EX 93% là **mô phỏng** (`simulate_nl2sql_predictions.py`), lõi `src/t2s` không chạy trên VTNet | Cao | 02 §6 |
| F8 | Mô tả cột: 58% AI sinh, 42% trống, 7 cột khác; có mô tả AI sai (`object_id`) | Cơ hội nghiên cứu | 02 §7 |
| F9 | Generator có 14 chỗ chèn dữ liệu riêng cho từng case (có chỗ "kills DROP_WHERE on H009"); `peak_view` có 50 khóa cell-giờ trùng, mâu thuẫn với grain 1 dòng/cell/ngày của query production | Cao | 02 §8 |
| F10–F16 | Phát hiện trong đợt thực hiện V1.1 (chỉ 99/5.865 cột có dữ liệu thật, gold lệch câu hỏi, gold vi phạm quy ước bad-cell…) | Xem 07 | 07 |
