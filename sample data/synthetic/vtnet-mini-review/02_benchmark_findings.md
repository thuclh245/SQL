# 02 — Phát hiện chi tiết

Mọi con số dưới đây được tái lập bằng `scripts/reproduce_review_checks.py` (output: `outputs/review_checks.json`).

## Nguyên nhân gốc

Dữ liệu, bẫy, câu hỏi và gold đều do **cùng một agent** sinh ra, và không có bước kiểm tra độc lập nào. Kết quả là một benchmark **tự nhất quán**: gold luôn chạy đúng trên đúng bộ dữ liệu được sinh ra cho nó. Nhưng benchmark này chưa chắc **đúng với nghiệp vụ**, và cũng chưa đủ **nhạy** để phân biệt SQL đúng với SQL sai tinh vi. Các phát hiện F1–F6 đều bắt nguồn từ đây.

Dùng agent để sinh không có gì sai. Điều cần thêm là **tách vai và kiểm tra chéo** (xem `03_plan_v1_1.md`, Phase 3).

---

## §1 — Dữ liệu quá nhỏ và gần như toàn bẫy (F1, F2)

| Chỉ số | Giá trị |
|---|---|
| Tổng dòng | 1.770 |
| Trung vị dòng/bảng | 5 |
| Cell riêng biệt trong `kpi_access5g_5g_cell_peak_view` | 63 |
| Cell thuộc nhóm bẫy A–H (từ `validation_report.json`) | 53 |
| **Tỷ lệ bẫy** | **84%** |
| Khoảng thời gian | 2026-08-01 → 2026-08-20, 2 khung giờ |

**Hệ quả:**
- Hai SQL khác nhau về logic rất dễ trả cùng một kết quả, nên xác suất "lucky match" cao (xem §2).
- Phân phối không giống mạng thật, nơi cell xấu chỉ chiếm vài phần trăm. Các câu top-N, trung bình, phân vị, cùng mọi tín hiệu value probe/profiling đều không phản ánh thực tế.
- Không kiểm tra được hiệu năng hay chi phí query (quét partition, CAST trên hàng triệu dòng).

## §2 — Gold H002 có lỗi tiềm ẩn mà dữ liệu hiện tại không phát hiện được (F3)

Câu hỏi: *"cell 5G có chuỗi ít nhất 3 ngày liên tiếp bị suy giảm thông lượng (< 4 Mbps và traffic > 0) trong 7 ngày kết thúc 2026-08-20"*.

Gold dùng `LAG(...) OVER (PARTITION BY object_id ORDER BY date)` trên các dòng **đã bị lọc** `traffic > 0`. Tức là nó xét 3 **dòng** liền nhau, chứ không phải 3 **ngày lịch** liên tiếp.

Script thêm 2 cell thử nghiệm vào một DuckDB in-memory:

| Cell | Dữ liệu | Đáp án đúng | Gold trả |
|---|---|---|---|
| `CELL_GAP` | Xấu ngày 14, 15, 17; ngày 16 traffic = 0 (bị `WHERE` lọc mất) | Không tính (không có 3 ngày liên tiếp) | **Tính** |
| `CELL_2H` | Ngày 14 có 2 khung giờ xấu, ngày 15 xấu, tổng cộng 2 ngày | Không tính | **Tính** |

Trên dữ liệu hiện tại, gold và bản đúng (gộp theo ngày rồi tìm chuỗi ngày lịch) đều trả **37 cell giống hệt nhau**. Nghĩa là gold sai nhưng benchmark không phát hiện ra. Đây là bằng chứng trực tiếp cho §1.

**Việc cần làm:**
- DE chốt định nghĩa "ngày bị suy giảm" khi một ngày có nhiều khung giờ (mọi giờ xấu? trung bình ngày? giờ cao điểm?).
- Viết lại gold theo ngày lịch.
- Cài vào dữ liệu thật hai loại bẫy: ngày trống giữa chuỗi và nhiều khung giờ trong một ngày.
- Rà lại toàn bộ case có skill `window_lag`, `streak_detection`, `rolling_window`, `multi_window` theo cùng hướng này.

## §3 — H012: câu hỏi và gold không khớp (F4)

Câu hỏi: *"Thống kê khối lượng công việc **của từng phòng ban** GNOC: số lượng cảnh báo thuộc địa bàn quản lý và số lượt điều chỉnh thông số trong od_history."*

Gold tính `COUNT(*)` trên **toàn bảng** `od_history` rồi `CROSS JOIN` với từng phòng ban, nên cả 6 phòng ban đều nhận cùng giá trị **30**. Trong khi đó `od_history` có sẵn cột `unit_id`, rất có thể là khóa phòng ban.

**Việc cần làm:** DE xác nhận ý nghĩa `unit_id`, sau đó sửa gold (join theo `unit_id`) hoặc sửa câu hỏi (bỏ cụm "của từng phòng ban" cho phần od_history). Đây đúng là loại lỗi mà **chú thích kép** (Phase 3.2) sẽ tự động bắt được.

## §4 — Câu hỏi bị lộ schema và cú pháp SQL (F5)

- **39/100** câu chứa định danh bảng/cột có trong gold (`f_location_new`, `occean_cell`, `nr_ps_traffic_total_gb`, `station_code`…).
- **9** câu chứa gợi ý cú pháp SQL: H001, H009, H017, H025, H035, H036, H037, H038, H039. Ví dụ H001 ghi "…bằng GROUPING SETS (Production Query Variant 1)".

**Hệ quả:** benchmark đang đo khả năng viết SQL khi đã được chỉ bảng, chưa đo được khả năng hiểu câu hỏi nghiệp vụ và tìm đúng bảng. Trong khi với catalog 8.800 bảng, retrieval và hiểu nghiệp vụ mới là phần khó nhất.

**Việc cần làm:** giữ bản hiện tại làm `question_explicit`, đồng thời tạo thêm `question_natural` viết bằng ngôn ngữ nghiệp vụ (xem `05_case_schema_v2.md`).

## §5 — Không có câu no-answer/ambiguous (F6)

`cases.jsonl` không có trường `expected_outcome`, và không có câu nào mà đáp án đúng là "không trả lời được" hoặc "cần hỏi lại". Product contract của dự án (`docs/01_PRODUCT_CONTRACT.md`) lại đặt Answer / Ambiguous / Abstain làm trung tâm, và coi **wrong-but-plausible** là lỗi tệ nhất.

**Việc cần làm:** thêm 15–20 câu có `expected_outcome` ∈ {`unanswerable`, `ambiguous`}, kèm lý do (xem 03, Phase 3.3).

## §6 — Kết quả 93% là mô phỏng, lõi hệ thống chưa chạy trên VTNet (F7)

- `scripts/simulate_nl2sql_predictions.py` lấy gold rồi cài lỗi vào 21 case đã chọn trước. Con số 93% EX vì vậy chỉ phản ánh số lỗi đã cài, không nói gì về chất lượng của bất kỳ model nào. `DE_REVIEW_GUIDE.md` đã có ghi chú điều này, nhưng `reports/nl2sql_error_analysis.md` thì chưa.
- `DuckDBRuntime` (`backend/services/runtime_service.py`) tự làm prompt, rewrite và self-heal, **không đi qua** các thành phần grounding, value grounding, verification, orchestrator trong `src/t2s`.

**Việc cần làm:** gắn nhãn `SIMULATED` vào báo cáo; nối `src/t2s` vào DuckDB và chạy model thật (03, Phase 5).

## §7 — Metadata chủ yếu do AI sinh hoặc bỏ trống (F8), nên xem là cơ hội

| Nguồn mô tả cột | Số cột | Tỷ lệ |
|---|---|---|
| `[AI Gen]` | 3.398 | 58% |
| Trống | 2.459 | 42% |
| Khác | 7 | 0,1% |

Có mô tả AI sai hẳn. Ví dụ `kpi_access5g_5g_cell_peak_view.object_id`, thực chất là khóa cell dùng để anti-join với `occean_cell`, lại được mô tả là: *"Trường dữ liệu chưa xác định… thông tin phụ trợ chưa được chuẩn hoá"*.

Đồng thời 47% cột là VARCHAR, trong đó có metric KPI lưu dạng text. Đây đúng là nguồn của lỗi so sánh chuỗi `'90' > '100'` mà `nl2sql_error_analysis.md` đã chỉ ra.

**Không nên xóa đi mà nên dùng làm biến thí nghiệm:** so pipeline trên metadata trống, metadata AI sinh, metadata đã xác minh bằng dữ liệu, và metadata người viết (03, Phase 4). Benchmark công khai không làm được điều này, vì metadata của chúng sạch.

## §8 — Dữ liệu được vá theo từng case, và có chỗ mâu thuẫn với grain production (F9)

**Chèn dữ liệu riêng cho từng case.** `scripts/generate_synthetic_data.py` có **14 chỗ** chèn dữ liệu cho một case cụ thể, ví dụ:

| Dòng | Chú thích trong code |
|---|---|
| 165, 330 | `Trap cell CELL_5G_A00 for H020` |
| 348 | `Historical high throughput … to change AVG for M016` |
| 378 | `Duplicate measurement … so COUNT(DISTINCT date) != COUNT(date) for H044` |
| 494 | `Empty station code for H009 (kills DROP_WHERE on H009)` |
| 647 | `Duplicate date_hour record for H007` |

Thêm dữ liệu để phân biệt SQL đúng/sai là **việc nên làm**. Nhưng làm theo từng case thì có 3 tác dụng phụ:
1. Benchmark chỉ nhạy với đúng những mutant mà người viết đã nghĩ tới. Kill rate 100% phần nào là do được vá cho đến khi đạt 100%, nên không phải bằng chứng độc lập.
2. Phân phối dữ liệu bị gold định hình, thay vì định hình theo thực tế.
3. Mỗi lần thêm case là phải vá generator, rất khó bảo trì.

**Mâu thuẫn grain với query production.** `sample data/query.md` tính `COUNT(*) AS no_bad_day` trên `kpi_access5g_5g_cell_peak_view`, tức là mặc định **1 dòng cho mỗi cell mỗi ngày** (`date_hour` luôn là `-00`). Dữ liệu synthetic lại có **50 khóa `(object_id, date_hour)` bị trùng** trên 8 cell, và cả 50 cặp có giá trị khác nhau (dòng 355: *"carrier aggregation / dual carrier"*). Hệ quả: chạy **chính query production** trên benchmark này có thể bị chấm là sai.

**Việc cần làm:**
- DE xác nhận: ở production, `peak_view` có thể có nhiều dòng cho cùng một cell-ngày không? Nếu **không**, bỏ các dòng trùng và đưa bẫy COUNT/COUNT DISTINCT sang bảng hourly. Nếu **có**, ghi thành quy ước (`04_conventions_template.yaml`) và cập nhật query mẫu.
- Chuyển từ vá theo case sang **bẫy theo lớp** (Phase 1.3): mỗi loại bẫy được sinh với tỷ lệ cố định trên toàn bộ dữ liệu, không gắn với ID case nào.
- Giữ một bộ mutant **held-out** mà người sinh dữ liệu không được thấy, để kill rate trở thành thước đo độc lập.

## §9 — Điểm tốt nên giữ

- Tên bảng/cột, kiểu dữ liệu và độ nhiễu lấy từ OM thật.
- Bẫy A–H được thiết kế theo query production mẫu, và validation tự động có PASS/FAIL cho từng nhóm.
- Mutation test trên gold là ý tưởng tốt; chỉ cần thêm mutant tinh vi.
- Có cả gold dialect Trino và DuckDB, cùng `table_name_mapping.json`, nên sẵn sàng chuyển sang Trino/OM.
- Có sẵn gói review cho DE (`vtnet-mini-de-review-lean`).
