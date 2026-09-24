# 05 — Format case benchmark v2

Mở rộng từ `vtnet-mini/benchmark/cases.jsonl`, và vẫn **tương thích ngược**: mọi trường cũ được giữ nguyên.

## Các trường

| Trường | Kiểu | Bắt buộc | Mới? | Ý nghĩa |
|---|---|---|---|---|
| `id` | string | ✅ | | `E001`, `M010`, `H002`, `U001` (unanswerable), `A001` (ambiguous) |
| `question` | string | ✅ | | Giữ để tương thích; bằng `question_explicit` |
| `question_explicit` | string | ✅ | ✅ | Câu hiện tại, có thể chứa tên bảng/cột |
| `question_natural` | string | ✅ | ✅ | Ngôn ngữ nghiệp vụ; **không** có tên bảng, cột hay từ khóa SQL |
| `difficulty` | enum | ✅ | | `easy` / `medium` / `hard` |
| `domain` | enum | ✅ | | `network_kpi_5g`, `network_kpi_4g`, `alarm`, `fbb`, `data_monitoring`, `common_location`, `cross_domain` |
| `expected_outcome` | enum | ✅ | ✅ | `answer` / `unanswerable` / `ambiguous` |
| `expected_outcome_reason` | string | khi ≠ `answer` | ✅ | Vì sao không trả lời được hoặc vì sao mơ hồ |
| `clarification_options` | list | khi `ambiguous` | ✅ | Các cách hiểu hợp lệ, mỗi cách kèm gold riêng nếu có |
| `gold_sql_duckdb` | string | khi `answer` | | |
| `gold_sql_trino` | string | khi `answer` | | |
| `required_tables` | list | khi `answer` | | FQN production |
| `required_columns` | list | khuyến nghị | ✅ | FQN cột; dùng để đo recall của retrieval |
| `skills` | list | ✅ | | Như hiện tại |
| `conventions` | list | ✅ | ✅ | ID trong `conventions.yaml` mà SQL đúng phải tuân theo |
| `trap_groups` | list | ✅ | ✅ | Nhóm bẫy dữ liệu mà case chạm tới (`A`–`H`, `cast`, `fanout`, `calendar_gap`…) |
| `expected_result_sha256` | string | khi `answer` | | |
| `generation` | object | ✅ | ✅ | `{gold_writer, question_writer, cross_checker}`: model/prompt/người nào đã tạo |
| `review_status` | enum | ✅ | ✅ | `draft` / `agent_crosschecked` / `de_reviewed` / `approved` |
| `reviewer` | string | khi ≥ `de_reviewed` | ✅ | |
| `reviewed_at` | date | khi ≥ `de_reviewed` | ✅ | |
| `review_notes` | string | | ✅ | |

## Ví dụ: case answer (H002 sau khi sửa)

```json
{
  "id": "H002",
  "question": "Tìm danh sách các cell 5G có chuỗi ít nhất 3 ngày liên tiếp (streak >= 3) bị suy giảm thông lượng (dl_user_throughput_mbps < 4 Mbps và traffic > 0) trong cửa sổ 7 ngày kết thúc ngày 2026-08-20.",
  "question_explicit": "Tìm danh sách các cell 5G có chuỗi ít nhất 3 ngày liên tiếp (streak >= 3) bị suy giảm thông lượng (dl_user_throughput_mbps < 4 Mbps và traffic > 0) trong cửa sổ 7 ngày kết thúc ngày 2026-08-20.",
  "question_natural": "Trong tuần tính đến hết ngày 20/8/2026, những cell 5G nào bị tốc độ tải xuống dưới 4 Mbps ít nhất 3 ngày liền mà vẫn có phát sinh lưu lượng?",
  "difficulty": "hard",
  "domain": "network_kpi_5g",
  "expected_outcome": "answer",
  "gold_sql_duckdb": "-- viết lại theo ngày lịch sau khi DE chốt CONV_BAD_DAY_DEFINITION",
  "gold_sql_trino": "...",
  "required_tables": ["hive.npms.kpi_access5g_5g_cell_peak_view"],
  "required_columns": [
    "hive.npms.kpi_access5g_5g_cell_peak_view.object_id",
    "hive.npms.kpi_access5g_5g_cell_peak_view.date",
    "hive.npms.kpi_access5g_5g_cell_peak_view.dl_user_throughput_mbps",
    "hive.npms.kpi_access5g_5g_cell_peak_view.nr_ps_traffic_total_gb"
  ],
  "skills": ["window_lag", "streak_detection", "type_cast"],
  "conventions": ["CONV_STORAGE_KPI_VARCHAR_CAST", "CONV_BAD_DAY_DEFINITION"],
  "trap_groups": ["cast", "calendar_gap", "multi_row_per_day"],
  "expected_result_sha256": "...",
  "generation": {
    "gold_writer": "agent-A:<model>@<prompt-version>",
    "question_writer": "agent-B:<model>@<prompt-version>",
    "cross_checker": "agent-C:<model>@<prompt-version>"
  },
  "review_status": "de_reviewed",
  "reviewer": "<tên DE>",
  "reviewed_at": "2026-10-01",
  "review_notes": "Sửa LAG theo dòng thành chuỗi ngày lịch; xem review 02 §2."
}
```

## Ví dụ: case unanswerable

```json
{
  "id": "U001",
  "question": "Chỉ số NPS trung bình của thuê bao FTTH theo từng tỉnh trong tháng 8/2026 là bao nhiêu?",
  "question_explicit": "Chỉ số NPS trung bình của thuê bao FTTH theo từng tỉnh trong tháng 8/2026 là bao nhiêu?",
  "question_natural": "Mức độ sẵn sàng giới thiệu dịch vụ (NPS) của khách hàng cáp quang theo tỉnh tháng 8/2026?",
  "difficulty": "hard",
  "domain": "fbb",
  "expected_outcome": "unanswerable",
  "expected_outcome_reason": "Không có bảng/cột NPS hay khảo sát khách hàng trong catalog. Các bảng gần nghĩa (ftth_qoe_daily, ftth_churn_signal) là chỉ số kỹ thuật, không phải NPS.",
  "skills": ["abstention"],
  "conventions": [],
  "trap_groups": ["near_synonym_table"],
  "review_status": "draft"
}
```

## Ví dụ: case ambiguous

```json
{
  "id": "A001",
  "question": "Top 10 cell 5G có lưu lượng cao nhất ngày 20/8/2026",
  "question_explicit": "Top 10 cell 5G có lưu lượng cao nhất ngày 20/8/2026",
  "question_natural": "Top 10 cell 5G có lưu lượng cao nhất ngày 20/8/2026",
  "difficulty": "medium",
  "domain": "network_kpi_5g",
  "expected_outcome": "ambiguous",
  "expected_outcome_reason": "\"Lưu lượng\" có thể là tổng traffic PS (nr_ps_traffic_total_gb), traffic DL, hoặc traffic UL; các cách hiểu cho ra top 10 khác nhau.",
  "clarification_options": [
    {"label": "Tổng traffic PS (GB)", "gold_sql_duckdb": "..."},
    {"label": "Traffic tải xuống (DL)", "gold_sql_duckdb": "..."}
  ],
  "skills": ["clarification"],
  "conventions": ["CONV_STORAGE_KPI_VARCHAR_CAST"],
  "trap_groups": [],
  "review_status": "draft"
}
```

## Quy tắc chấm cho expected_outcome

| Expected | Hệ thống trả | Chấm |
|---|---|---|
| `answer` | answer, kết quả khớp | ✅ đúng |
| `answer` | answer, kết quả lệch | ❌ **wrong-but-plausible** (lỗi nặng nhất) |
| `answer` | abstain / clarify | ⚪ mất coverage, không tính là sai |
| `unanswerable` | abstain | ✅ |
| `unanswerable` | answer | ❌ lỗi nặng (bịa kết quả) |
| `ambiguous` | clarify, có nêu đúng điểm mơ hồ | ✅ |
| `ambiguous` | answer khớp một trong các `clarification_options` | ⚪ chấp nhận được, ghi nhận riêng |
| `ambiguous` | answer không khớp option nào | ❌ |
