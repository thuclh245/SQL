# VTNet Mini benchmark v2

Sinh bởi `scripts/build_v1_1_assets.py`; không sửa tay file `cases.jsonl`.

## Trạng thái

- Tổng 124 case; chấm điểm 123; loại khỏi chấm điểm 1 (H012: blocked_by_data).
- expected_outcome (chấm điểm): ambiguous 5, answer 106, unanswerable 12.
- Độ khó câu answer: easy 21, hard 52, medium 33.
- Domain câu answer: alarm 22, common_location 7, data_monitoring 12, fbb 22, network_kpi_4g 5, network_kpi_5g 38.
- **Toàn bộ case ở trạng thái `draft`.** Chưa có DE review và chưa có chú thích kép độc lập.

## Nguồn gốc từng trường

| Trường | Nguồn |
|---|---|
| `question_explicit` | Câu hỏi V1 (có thể chứa tên bảng/cột) |
| `question_natural` | `natural_questions.json`, viết tay; người viết có xem gold nên chưa phải kiểm tra chéo độc lập |
| `gold_sql_*` | V1, trừ H002/H012/H027 (xem `gold_fix_reason`) và 7 case Data Monitoring mới |
| `expected_result_sha256` | Tính lại từ DuckDB, cùng cách chuẩn hóa với V1 |
| `conventions` | Quy ước `accepted` áp dụng cho case, suy ra từ câu hỏi và bảng (không từ gold) |
| `convention_conflicts` | Gold vi phạm quy ước theo checker AST: cần DE xem gold sai hay quy ước quá rộng |
| `review_flags` | Vấn đề phát hiện khi viết lại câu hỏi và kiểm tra gold |

## Cờ review

- `de_check`: 2 case
- `duplicate_question`: 2 case
- `gold_violates_convention`: 6 case
- `grain_duplicate_rows_risk`: 5 case
- `heuristic_join`: 5 case
- `hidden_condition_in_gold`: 5 case
- `new_case_v1_1`: 7 case
- `nondeterministic_fixed`: 1 case
- `pending_de_definition`: 1 case
- `question_gold_mismatch`: 5 case
