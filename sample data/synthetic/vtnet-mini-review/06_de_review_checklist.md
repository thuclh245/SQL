# 06 — Checklist DE review từng case

Dùng khi chuyển case từ `agent_crosschecked` (hoặc `draft`) sang `de_reviewed`. Mỗi mục ghi ✅ / ❌ / N/A, mục ❌ ghi lý do vào `review_notes`.

## A. Câu hỏi

- [ ] **A1.** Người dùng nghiệp vụ Viettel có hỏi câu này thật không? (Nếu không, sửa lại hoặc loại bỏ)
- [ ] **A2.** `question_natural` không chứa tên bảng, tên cột hay từ khóa SQL (`GROUPING SETS`, `HAVING`, `NOT EXISTS`, `CTE`…)
- [ ] **A3.** Câu hỏi đủ rõ để chỉ có **một** kết quả đúng. Nếu có nhiều cách hiểu hợp lệ thì chuyển sang `ambiguous`
- [ ] **A4.** Mốc thời gian, địa bàn và đơn vị (Mbps, GB, %) được nêu rõ hoặc có mặc định theo quy ước
- [ ] **A5.** Thuật ngữ dùng đúng nghĩa nghiệp vụ (cell/site/enodeb, traffic/throughput, alarm/ticket/WO…)

## B. Gold SQL

- [ ] **B1.** Gold trả lời **đúng câu hỏi**, không phải câu gần giống. (Ví dụ lỗi: H012 hỏi theo từng phòng ban nhưng gold trả tổng)
- [ ] **B2.** Grain đúng: đếm object (cell, thuê bao, alarm) thay vì đếm dòng; đã gộp trước khi join với bảng không unique
- [ ] **B3.** Logic thời gian theo **ngày lịch** nếu câu hỏi nói "ngày liên tiếp", "7 ngày gần nhất"; không dùng LAG theo dòng khi dữ liệu có thể thiếu ngày hoặc có nhiều dòng/ngày (ví dụ lỗi: H002)
- [ ] **B4.** Đã áp dụng đủ các quy ước trong `conventions` (CAST, định dạng date_id, loại occean_cell/blacklist, `country = 'VNM'`, dùng bảng mới thay bảng deprecated)
- [ ] **B5.** Biên của điều kiện đúng như câu hỏi (`>` so với `>=`, "hơn 3 ngày" nghĩa là `> 3`)
- [ ] **B6.** Chọn LEFT hay INNER JOIN đúng ý: có cần giữ dòng thiếu mapping không (nhóm H)
- [ ] **B7.** `gold_sql_trino` tương đương `gold_sql_duckdb` về ngữ nghĩa
- [ ] **B8.** Không phụ thuộc vào thứ tự dòng, trừ khi câu hỏi yêu cầu sắp xếp

## C. Dữ liệu và kết quả

- [ ] **C1.** Kết quả không rỗng, trừ khi case có chủ đích như vậy
- [ ] **C2.** Kết quả **thay đổi** khi áp dụng ít nhất một mutant hợp lý (bỏ một quy ước, đổi biên, đổi JOIN). Nếu không, dữ liệu chưa phân biệt được
- [ ] **C3.** Dữ liệu dùng cho case là bẫy **theo lớp**, không phải dữ liệu chèn riêng cho case này trong generator
- [ ] **C4.** Grain dữ liệu khớp với query production tương ứng (ví dụ `peak_view` 1 dòng/cell/ngày)
- [ ] **C5.** Giá trị có vẻ hợp lý về nghiệp vụ (throughput, traffic, thời gian xử lý alarm nằm trong khoảng thực tế)

## D. Nhãn

- [ ] **D1.** `difficulty` hợp lý (hard = từ 3 kỹ năng trở lên, hoặc có quy ước ngầm, hoặc có logic thời gian phức tạp)
- [ ] **D2.** `skills`, `conventions`, `trap_groups` đầy đủ và đúng
- [ ] **D3.** `required_tables` / `required_columns` đủ và không thừa
- [ ] **D4.** Với `unanswerable`/`ambiguous`: `expected_outcome_reason` thuyết phục; đã chắc chắn trong catalog **không có** bảng nào trả lời được

## Kết luận

- **Đạt:** mọi mục A, B, C4 và D đều ✅ → `de_reviewed`
- **Sửa nhỏ:** sửa trực tiếp, ghi vào `review_notes` → `de_reviewed`
- **Sửa lớn:** trả về `draft` kèm lý do
- **Loại bỏ:** ghi lý do, chuyển sang file `rejected_cases.jsonl` để lưu vết

## Hàng đợi ưu tiên

1. Case lệch giữa gold và agent C (chú thích kép)
2. H002, H012 và các case có skill `window_lag`, `streak_detection`, `rolling_window`, `multi_window`, `cross_join`
3. Các case dùng dữ liệu chèn riêng trong generator: H007, H008, H009, H020, H040, H043, H044, H047, M016
4. Toàn bộ case hard còn lại
5. Mẫu 30% case easy/medium
