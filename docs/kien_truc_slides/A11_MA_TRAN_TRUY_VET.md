# A11 — Ma trận truy vết: Vấn đề → Bằng chứng → Chốt chặn → Mã nguồn

**Thông điệp chính:** Không có một dòng kiến trúc nào tồn tại vì "thấy hay thì làm". Mỗi thành phần đều truy ngược được về **một phương thức lỗi đã đo được** hoặc **một kết quả nghiên cứu đã công bố**. Đây là slide trả lời dứt điểm câu hỏi *"vì sao phải phức tạp thế?"*.

## Bảng chính (nên để nguyên 1 slide ngang, cỡ chữ nhỏ cũng chấp nhận được — hội đồng sẽ đọc kỹ bảng này)

| # | Phương thức lỗi | Bằng chứng | Chốt chặn của T2S | Mã nguồn | Slide |
|---|---|---|---|---|---|
| 1 | Catalog 9.000 bảng, nhồi context gây "ngộ độc thông tin" | *Lost in the Middle* (TACL 2024); I5: EX giảm 0,70%, chi phí +23,1% | Grounding phân tầng 5 nấc + ngân sách cứng | `src/t2s/grounding/` | A4 |
| 2 | Bịa giá trị literal | I2: EX tụt 48,67% → 5,81%; *PV-SQL*, *VET* (ACL 2026) | Value grounding + DB probing có kiểm soát (`LIMIT 1`, `EXISTS`) | `filters_and_values` check + DB Gateway | A5 |
| 3 | Lỗi ngữ nghĩa áp đảo lỗi cú pháp | *BIRD* (NeurIPS 2023): liên kết ngữ nghĩa ~40,6%; I1: `wrong_row_set` 40,6%, `wrong_metric` 38,7% | 7 phép kiểm tra bất biến ở tầng L4 | `src/t2s/verification/deterministic_verifier.py` | A5 |
| 4 | Lai tạp cú pháp giữa các engine | *Spider 2.0* (ICLR 2025): tỷ lệ thành công tụt mạnh khi đổi phương ngữ enterprise | Phương ngữ là kiểu dữ liệu hạng nhất; parse theo đúng engine | `src/t2s/verification/sql_ast_parser.py` | A8 |
| 5 | Self-correction không có phản hồi ngoài là vô ích | *Huang et al.* (ICLR 2024); I3: **855/855** ca sinh lại y hệt | Xoá self-reflection chung chung; chỉ leo thang theo chẩn đoán, **tối đa 1 lần** | `src/t2s/orchestration/escalation_policy.py` | A6 |
| 6 | Resampling/voting chạm trần sớm, chung điểm mù | *CHASE-SQL* (ICLR 2025), *DPC* (ACL 2026); I4: k=3 chỉ +4,68% nhưng ×3 chi phí | Không dùng majority voting; ưu tiên chiến lược khác biệt khi cần | `src/t2s/orchestration/` | A6 |
| 7 | Truy vấn bùng nổ làm nghẽn cụm BI | Sự cố vận hành đã biết trên ClickHouse/StarRocks | EXPLAIN trước khi chạy · timeout 30s · trần 1.000 dòng · chỉ 1 câu lệnh | `src/t2s/database/` | A7 |
| 8 | Mơ hồ nội tại của ngôn ngữ ("doanh thu tháng này") | Nghiên cứu *Selective Prediction* / Abstention | Hợp đồng 3 trạng thái; `AMBIGUOUS` hỏi lại có lựa chọn cụ thể | `RuntimeStatus`, decision policy | A9 |
| 9 | Bảo mật đặt trong system prompt là ảo tưởng | Prompt injection là lớp tấn công đã được chứng minh | 3 chốt **dưới** LLM: ACL ở Grounding · AST access check · DB role/RLS | `src/t2s/security/`, `sql_access_validator.py` | A7 |
| 10 | LLM-as-a-Judge chia sẻ điểm mù với model sinh | *DPC* (ACL 2026) | Verifier LLM chỉ là **1 trong 6 tầng**, tuỳ chọn, tắt được | `VerifierMode`, `llm_semantic_verifier.py` | A5 |
| 11 | Metadata nghèo chặn trần chất lượng | Quan sát nội bộ trên catalog thật | Dùng OpenMetadata làm nguồn sự thật + pipeline làm giàu | `workers/metadata_indexer/` | A10 |

> Ghi chú: các mã `I1`–`I6` tham chiếu `docs/10_EVIDENCE_REGISTER.md`. **Kiểm tra lại từng con số trong sổ bằng chứng trước khi lên slide** — số nào chưa chốt thì để `⟨TBD⟩`, đừng điền ước lượng.

## Ma trận ngược — mỗi thành phần biện minh cho sự tồn tại của nó

Dùng khi bị hỏi *"bỏ bớt cái này được không?"*:

| Thành phần | Nếu bỏ đi thì sao? |
|---|---|
| Grounding phân tầng | Prompt vượt cửa sổ ngữ cảnh, hoặc chi phí token tăng tuyến tính theo số bảng của công ty |
| Kiểm tra AST an toàn | Không còn gì đảm bảo LLM không sinh `DELETE` — chỉ còn lời hứa trong prompt |
| Kiểm tra quyền trên AST | Rò rỉ metadata và dữ liệu qua subquery/CTE mà lọc chuỗi không bắt được |
| Bất biến ngữ nghĩa L4 | Lỗi *wrong-but-plausible* (≈40% tổng lỗi) đi thẳng tới người dùng dưới dạng số liệu đẹp |
| Ngân sách leo thang | Chi phí GPU không có trần trên; I3 cho thấy phần chi thêm phần lớn là vô ích |
| EXPLAIN trước khi chạy | Một câu hỏi vô hại của người dùng có thể làm nghẽn cụm BI của cả công ty |
| DB role / RLS | Mất chốt phòng thủ cuối cùng; toàn bộ bảo mật phụ thuộc vào việc LLM "nghe lời" |
| Hợp đồng 3 trạng thái | Hệ thống buộc phải đoán bừa trên câu hỏi mơ hồ ⇒ sai âm thầm |

## Cách dùng slide này

Đây nên là **slide cuối cùng của phần kiến trúc**, ngay trước phần kết quả đo lường. Nó khép lại mạch lập luận: Phần 2 nêu vấn đề đo được → Phần 3 nêu chốt chặn → A11 chứng minh **ánh xạ 1–1**, không thừa một thành phần nào, không bỏ sót một phương thức lỗi nào.
