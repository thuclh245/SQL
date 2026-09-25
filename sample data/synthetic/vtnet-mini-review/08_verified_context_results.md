# 08 — Pipeline verified-context: kiến trúc, ablation, phát hiện (2026-09-24)

Tài liệu này ghi lại việc biến ba thành phần đóng góp của dự án thành pipeline chạy thật và đo được:
**(1) quy ước dữ liệu ngầm có checker AST, (2) metadata có độ tin cậy (profiler, glossary), (3) biết từ chối / hỏi lại.**
Mọi con số dưới đây tái lập được bằng lệnh ở cuối file.

## 1. Tóm tắt

| | Hệ thống cũ (B0) | Hệ thống mới (C6) |
|---|---|---|
| **Safe = (A+B)/Tổng theo thang A–F, 123 câu** (chỉ số chính, §4b) | **4,9%** | **63,4%** |
| EX theo nghĩa, 106 câu answer (bộ chấm cũ, §4) | 5,7% | 53,8% |
| Tỷ lệ sai im lặng (kết quả được trả ra nhưng sai) | **93,2%** | **41,2%** |
| Nhận ra câu không trả lời được / mơ hồ (17 câu) | 0/17 | **17/17** |
| Lỗi thực thi | 35 | 0 |

Model `openai/gpt-oss-120b`, 123 case chấm điểm của `benchmark_v2`, câu hỏi nghiệp vụ (`question_natural`). Số liệu lấy từ lượt 1, là lượt đầy đủ duy nhất. Lượt 2, chạy sau khi sửa, mới hoàn thành một phần vì tài khoản OpenRouter hết credit (xem §5).

**Kết luận chính:**
- Chênh lệch giữa B0 và C6 **không đến từ model**, vì hai hệ thống dùng cùng model.
- Chênh lệch đến từ các khối chọn bảng, profiler, cổng từ chối và kiểm chứng, tức phần đóng góp của dự án.
- Bảng ablation (§4) chỉ ra khối nào đóng góp bao nhiêu.

## 2. Đã làm gì

| Thành phần | File |
|---|---|
| Package mới `t2s.verified_context` (production, đã đăng ký trong `configs/security/benchmark_registry.json`) | `src/t2s/verified_context/` |
| Checker quy ước dùng chung cho runtime, validator, builder và audit | `src/t2s/verified_context/conventions.py`; `scripts/convention_checks.py` giờ chỉ là adapter |
| Glossary nghiệp vụ: khái niệm → bảng, định nghĩa, thuật ngữ mơ hồ, thuật ngữ nhạy cảm, mẫu thời gian | `vtnet-mini/conventions/glossary.yaml` |
| Chấm điểm theo nghĩa và theo kết cục (answer/abstain/clarify) | `src/t2s/evaluation/selective_scoring.py` |
| Chạy ablation, có cache, bỏ qua lỗi provider, chế độ `--rescore` | `vtnet-mini/scripts/run_ablation.py` |
| Baseline B0 đóng băng nguyên văn (commit 8301397) để tái lập | `vtnet-mini/scripts/baselines/legacy_duckdb_runtime.py` |
| Backend `vtnet_mini` chạy qua pipeline mới; bỏ `DuckDBRuntime` cũ (−472 dòng) | `backend/services/runtime_service.py`, `backend/routes/verified_stream.py` |
| Giao diện hiển thị trạng thái "Từ chối" / "Cần làm rõ", có nút chọn cách hiểu | `frontend/app.js` |
| Test: 28 test mới; toàn bộ test unit của repo vẫn pass (gồm các guard kiến trúc) | `tests/unit/verified_context/`, `tests/unit/evaluation/test_selective_scoring.py` |
| Registry: thêm luật cấm CAST `date_hour`, nhận dạng ANTI JOIN và anti-join qua CTE; 52/52 fixture đúng | `vtnet-mini/conventions/conventions.yaml` |
| Benchmark: sửa câu H052 ("lần đo gần nhất **của từng chỉ số**") | `scripts/build_v1_1_assets.py` → `benchmark_v2/cases.jsonl` |

## 3. Kiến trúc

```
câu hỏi
 → linking     glossary (khái niệm → bảng) + độ trùng mô tả metadata M0/M1/M2; loại 110/148 bảng không có dữ liệu thật
 → gates       chính sách PII | thuật ngữ mơ hồ → CLARIFY | thời gian ngoài phạm vi dữ liệu → ABSTAIN | không có bảng → ABSTAIN
 → context     chỉ cột có dữ liệu, kiểu thật, giá trị thật, phạm vi, grain, định nghĩa glossary, quy ước áp dụng
 → LLM         hợp đồng đầu ra SQL / CLARIFY / ABSTAIN
 → normalise   chỉ đổi tên bảng sang tên vật lý DuckDB; không viết lại ngữ nghĩa SQL
 → guard       một câu SELECT, chỉ đọc (chạy TRƯỚC khi thực thi)
 → execute + verify   lỗi thực thi | vi phạm quy ước accepted | kết quả rỗng → 1 vòng sửa
 → nếu vẫn vi phạm quy ước accepted → ABSTAIN (không trả kết quả chưa tuân thủ)
```

**Khác biệt về thiết kế so với hệ thống cũ:**
- Hệ thống cũ **tự viết lại SQL** bằng các rule 1–8 và self-heal bằng regex. Cách này sinh ra lỗi (rule 6 làm hỏng SQL đúng ở H052) và che mất lỗi thật.
- Hệ thống mới **không viết lại ngữ nghĩa**: verifier báo lỗi cho model và để model tự sửa. Vì vậy SQL cuối cùng luôn là SQL model viết ra, không phải SQL do hệ thống âm thầm chỉnh.

## 4. Ablation lượt 1 (đầy đủ, 123 case, gpt-oss-120b)

Mỗi hàng thêm đúng một thành phần so với hàng trên. Bảng này dùng bộ chấm trước khi sửa hai lỗi chấm oan (xem §4b). Số liệu chính thức là bảng A–F ở §4b.

| Cấu hình | EX | EX chặt | EX (gold sạch, 91) | Sai im lặng ↓ | Độ phủ | Decline P / R | Từ chối nhầm | Lỗi thực thi |
|---|---|---|---|---|---|---|---|---|
| **B0** hệ thống cũ | 5,7% | 3,8% | 6,6% | 93,2% | 71,5% | – / 0% | 0 | 35 |
| **C1** chọn bảng bằng glossary, M0 (chỉ tên + kiểu) | 35,8% | 32,1% | 39,6% | 65,2% | 91,1% | – / 0% | 0 | 11 |
| **C2** + mô tả M1 (AI sinh) | 37,7% | 32,1% | 41,8% | 65,2% | 93,5% | – / 0% | 0 | 8 |
| **C3** + profiler (M2, giá trị thật, phạm vi, grain) | **54,7%** | 47,2% | 58,2% | 51,3% | 96,7% | – / 0% | 0 | 4 |
| **C4** + quy ước trong prompt | 52,8% | 46,2% | 57,1% | 51,7% | 94,3% | – / 0% | 0 | 7 |
| **C5** + verifier, 1 vòng sửa | 52,8% | 49,1% | 56,0% | 51,3% | 93,5% | – / 0% | 0 | 8 |
| **C6** + cổng và hợp đồng ABSTAIN/CLARIFY | 53,8% | 50,9% | 58,2% | **41,2%** | 78,9% | 65% / **100%** | 9 | **0** |
| C6m1 = C6 nhưng dùng mô tả M1 thay M2 | 50,0% | 48,1% | 51,7% | 39,1% | 70,7% | 65% / 100% | 9 | 10 |
| C7 = C6 nhưng đưa sẵn bảng đúng (cận trên của linking) | 51,9% | 48,1% | 56,0% | 43,3% | 78,9% | 74% / 100% | 6 | 3 |

*Model thứ hai:* `qwen-2.5-coder-32b` ở B0 đạt EX 3,8% và sai im lặng 95,4%, tức hệ thống cũ cũng hỏng với model khác. Các lượt C3/C6 của qwen chưa chạy xong (hết credit).

**Cách đọc các cột:**
- **EX:** chấm theo nghĩa. Bỏ qua thứ tự dòng, thứ tự cột và tên cột; cho phép thừa cột; chấp nhận đổi nhãn 1-1 (`area_code` ↔ `area_name`, NULL ↔ 'TOTAL' ở dòng tổng).
- **EX chặt:** giá trị phải khớp chính xác.
- **Gold sạch:** bỏ các case có gold bị tranh chấp (lệch câu hỏi, có điều kiện ẩn, xung đột quy ước, chưa có định nghĩa).
- **Sai im lặng:** số kết quả sai trên tổng số kết quả đã trả ra cho người dùng.
- **Decline P/R:** precision/recall của việc từ chối hoặc hỏi lại, tính trên 17 case không có đáp án.

**Diễn giải:**
1. **Khối chọn bảng là đóng góp lớn nhất** (+30 điểm, từ B0 sang C1). Khối cũ chỉ lấy đủ bảng ở 25% case; glossary lấy đủ ở 95% (102/107). C7 (đưa sẵn bảng đúng) không cao hơn C6, nghĩa là **chọn bảng không còn là điểm nghẽn**.
2. **Profiler là đóng góp lớn thứ hai** (+17 điểm, từ C2 sang C3): chỉ đưa cột có dữ liệu thật (peak_view còn 10/395 cột), cùng giá trị thật (`AREA_1` chứ không phải `1`), phạm vi ngày và grain.
3. **Mô tả AI (M1) hầu như không giúp** (+1,9 điểm, trong mức dao động). Trong hệ thống đầy đủ, dùng M1 thay M2 **làm giảm** EX (−3,8 điểm) và làm tăng lỗi thực thi (0 → 10). Đây là bằng chứng cho luận điểm "metadata phải được kiểm chứng".
4. **Cổng từ chối/hỏi lại** làm giảm sai im lặng từ 51% xuống 41% mà EX không giảm, và nhận diện đúng 17/17 case. Đổi lại có 9 câu answer bị từ chối nhầm (phân tích ở §6).
5. **Quy ước và verifier không làm tăng EX ở lượt này** (C3 → C5 nằm trong mức dao động, xem §5). Có hai lý do:
   - Quy ước bad-cell chỉ áp dụng cho khoảng 10 case, và 6 trong số đó có gold vi phạm chính các quy ước này (F13).
   - Verifier chỉ được kích hoạt ở 3 case.

   Giá trị của thành phần này nằm ở chỗ khác: nó biến "sai im lặng" thành "từ chối có lý do", ví dụ ở H017 (§5).

## 4b. Chấm theo thang A–F chuẩn (docs/t2s_docs_v2/05, ADR-004)

Chỉ số chính của dự án là **Production Semantic Safe Rate = (A+B)/Total**, không phải EX.
Nhãn được suy ra tự động từ verdict (`t2s.evaluation.selective_scoring.grade`), tính trên
toàn bộ 123 case (gồm cả 17 case không trả lời được / mơ hồ):

| Verdict | Nhãn |
|---|---|
| khớp gold, đúng số cột | A |
| thêm cột vô hại / đổi nhãn 1-1 (area_code↔area_name) / xoay bảng (một dòng nhiều cột ↔ nhiều dòng) | B1 / B3 / B5 |
| từ chối/hỏi lại đúng ở case không trả lời được / mơ hồ | A (từ chối đúng loại khác → B) |
| case mơ hồ, trả lời theo đúng một cách hiểu | C |
| sai kết quả / lỗi thực thi / trả lời câu phải từ chối / từ chối câu trả lời được | D (D, D-error, D-missed, D-refuse) |
| thiếu cột so với gold, gold có thể dư cột (F19) | F (cần người audit) |
| E (lucky match) | không tự phát hiện; A/B trên gold bị tranh chấp liệt kê là "nghi E" |

Lượt 1, gpt-oss-120b, 123 case:

| Config | A | B | C | D | F | **Safe (A+B)/Total** | Cond. safe | EX |
|---|---|---|---|---|---|---|---|---|
| B0 | 2 | 4 | 0 | 115 | 2 | **4.9%** | 5.0% | 5.7% |
| C1 | 31 | 8 | 1 | 73 | 10 | **31.7%** | 34.5% | 36.8% |
| C2 | 33 | 9 | 0 | 72 | 9 | **34.2%** | 36.8% | 39.6% |
| C3 | 48 | 12 | 0 | 50 | 13 | **48.8%** | 54.5% | 56.6% |
| C4 | 48 | 13 | 0 | 50 | 12 | **49.6%** | 54.9% | 57.6% |
| C5 | 50 | 12 | 0 | 49 | 12 | **50.4%** | 55.9% | 58.5% |
| C6 | 70 | 8 | 0 | 34 | 11 | **63.4%** | 69.6% | 57.6% |
| C6m1 | 65 | 9 | 0 | 41 | 8 | **60.2%** | 64.3% | 53.8% |
| C7 | 68 | 7 | 0 | 36 | 12 | **61.0%** | 67.6% | 54.7% |

qwen-2.5-coder-32b B0: Safe 3.3% (A=3, D=118).

Điểm khác với bảng EX: cổng từ chối (C5→C6) gần như không đổi EX (58.5%→57.6%) nhưng làm Safe tăng **+13.0 điểm** (50.4%→63.4%), vì 17 câu phải từ chối chuyển từ D-missed sang A.
D-refuse (9 câu trả lời được bị từ chối) là cái giá phải trả, vẫn nằm trong D.
Bộ chấm đã sửa hai lỗi chấm oan (đổi nhãn khi có số đếm trùng nhau, và kết quả xoay bảng); mọi cấu hình được chấm lại cùng một bộ chấm, nên các con số so sánh được với nhau. Nghi lucky match cần kiểm thử đột biến: E018, H003, M002, M013 (gold có cờ tranh chấp).

## 5. Phân tích lỗi lượt 1 → ba sửa → lượt 2 (từng phần)

Phân tích 40 câu trả lời sai của C6 cho thấy ba lỗi có tính hệ thống:

| Lỗi | Bằng chứng | Sửa |
|---|---|---|
| **Va chạm thuật ngữ do chính việc hiển thị giá trị gây ra:** "cảnh báo" nghĩa đen là "warning", nên khi profiler liệt kê giá trị `level_important` (…, **WARNING**) model lọc `level_important = 'WARNING'` | M004 đúng ở C2 (chưa hiển thị giá trị), sai từ C3; H031 sai từ C4; H026, H033 sai ở C3–C6 với cùng kiểu lọc `'WARNING'` | Glossary thêm `note`: "Mỗi dòng gnoc là MỘT cảnh báo; 'cảnh báo' ≠ WARNING" |
| **Hiểu sai bộ đếm AAA:** "số phiên bắt đầu" là `SUM(start)`, nhưng model đếm số dòng hoặc số khung giờ | M005, M025, H010 | `note` cho accounting/authentication |
| **Grain gây hiểu nhầm cho bảng sự kiện:** profiler cảnh báo "station_code + date_hour không duy nhất, hãy khử trùng" cho gnoc, trong khi mỗi dòng là một cảnh báo riêng (`schedule_id` duy nhất) | — | Bảng sự kiện ghi "mỗi dòng là một sự kiện, định danh bởi schedule_id"; bảng danh mục vẫn giữ cảnh báo fan-out |
| **Verifier phát hiện vi phạm nhưng kết quả vẫn được trả ra** | H017: model JOIN với occean_cell (tức lấy chính cell biển đảo); sau 1 vòng sửa vẫn sai, nhưng C6 vẫn trả kết quả | Chính sách mới: còn vi phạm quy ước accepted → ABSTAIN |

**Kết quả sau khi sửa** (lượt 2, dừng giữa chừng vì lỗi 402 của OpenRouter). Bảng dưới so từng cặp case, cùng code benchmark:

| So sánh | Số case answer | EX trước → sau | Thay đổi |
|---|---|---|---|
| C3, chỉ sửa grain | 85 | 45 → 42 | +3 / −6: **trong mức dao động, chưa thấy tác dụng** |
| C6m1, cả ba sửa | 86 | 43 → **52** | +12 / −3: **khoảng +10 điểm**, sai im lặng giữ nguyên (25 → 24), độ phủ tăng |
| C7, cả ba sửa | 12 | 7 → 10 | mẫu quá nhỏ |
| **Dao động:** C6 so với C6r (cùng code, chạy lại) | 32 | 18 → 16 | **±5–6 điểm là nhiễu** giữa hai lần chạy (provider không tất định dù temperature = 0) |

Smoke test 11 case sau khi sửa: M004, H031, H026, M005, H010 và M025 chuyển sang đúng; H017 chuyển sang ABSTAIN có lý do thay vì trả kết quả sai.

> **Lưu ý trung thực:** các `note` trong glossary được viết **sau khi** đã xem lỗi của lượt 1. Chúng là tri thức nghiệp vụ chung (ý nghĩa bộ đếm, ý nghĩa một dòng), không gắn với câu hỏi cụ thể nào. Dù vậy, con số +10 điểm vẫn là ước lượng lạc quan cho tới khi được đo trên một tập câu hỏi held-out (§7).

## 5b. Tương tác người dùng và vòng học (bản local)

Đã có trên UI và API (`src/t2s/verified_context/pipeline.py`, `feedback.py`, `retrieval.py`; `backend/routes/verified_routes.py`; `frontend/review.html`):

| Khả năng | Cách hoạt động |
|---|---|
| Chọn bảng khi hệ thống không chắc | Glossary đánh dấu `choose_one` (lưu lượng / thông lượng: 5G hay 4G; trạm: cảnh báo hay lịch bảo dưỡng; máy chủ: xác thực hay accounting). Thẻ bảng chỉ dùng nhãn đã duyệt và số liệu profiler. |
| Ô "Khác" ở mọi bước hỏi lại | Cách hiểu tự gõ, mô tả dữ liệu tự gõ (tìm bằng BM25 + giá trị thật), hoặc bổ sung thông tin khi bị từ chối. |
| Ghim bảng `@schema.table` | Có gợi ý khi gõ `@`; bảng không tồn tại được báo lại. |
| Giả định đã dùng + "Chưa đúng ý?" | Liệt kê bảng, cách hiểu, định nghĩa, quy ước (gắn nhãn "chờ DE duyệt" nếu mới đề xuất). Sửa cách hiểu được cộng dồn. |
| Hỏi tiếp | Lượt sau mang theo câu hỏi, SQL, bảng và cách hiểu của lượt trước. |
| Nhật ký, Đúng / Báo sai, trang `/review` | SQLite local (`data/verified_context/`, không commit). DE sửa SQL (phải chỉ đọc và chạy được) rồi duyệt thành câu mẫu. Câu hỏi trùng benchmark/held-out bị chặn (so khớp chính xác sau chuẩn hóa; câu gần giống vẫn lọt, cần so khớp gần đúng khi có embedding). |

Đo, không gọi LLM, trên 123 case:

| | Kết quả |
|---|---|
| Số câu benchmark bị hỏi chọn bảng | 0/123 (quy tắc chỉ hỏi khi toàn bộ bảng định chọn nằm trong nhóm thay thế nhau) |
| Độ phủ bảng, câu hỏi gõ không dấu | 64/106 → **102/106** khi so glossary sau khi bỏ dấu (chỉ áp dụng cho câu không dấu, vì bỏ dấu câu có dấu gộp "tỉnh"/"tính") |
| Câu không trả lời được vẫn tìm ra bảng | 4/12, không đổi |
| BM25 làm lớp dự phòng tự động | **Không bật**: đưa số câu không trả lời được có bảng từ 4/12 lên 11/12; điểm BM25 của hai nhóm chồng lấn (3,1–6,2 so với 6,7) nên không có ngưỡng tách được. BM25 chỉ dùng cho mô tả tự do của người dùng. |

Chạy lại 21 câu đã test trước đây (có người dùng giả lập trả lời bước hỏi lại): A/B **14/21** (hệ thống cũ 0/21), D 4, F 3. Sau khi làm rõ qua ô "Khác", 1/4 câu mơ hồ đúng; ba câu còn lại sai do model (độ hạt, bỏ sót dòng bằng điểm).

## 6. Phát hiện mới về benchmark (cần DE xem)

| # | Phát hiện | Case |
|---|---|---|
| F17 | **Nhãn không nhất quán:** "lưu lượng" không nói rõ loại được coi là ambiguous ở A001, nhưng là answer (tổng lưu lượng) ở M026, H020 và H002. Cổng hỏi lại theo đúng nguyên tắc nên bị tính là "từ chối nhầm" 3 case | A001 và M026, H020, H002 |
| F18 | **Gold có điều kiện ẩn chưa được gắn cờ:** loại mã rỗng `''`, lọc throughput > 0, lọc theo khoảng ngày, join danh mục để lấy tên | H008, H009, H013, H011, H023, H027 |
| F19 | **Gold trả thêm cột câu hỏi không yêu cầu** ("những X nào" nhưng gold trả thêm chỉ số). Evaluator tách riêng thành `subset_columns` (11 case ở C6), chỉ tính trong EX "lỏng" | H040, H042, H053, M010, M016, M033… |
| F20 | **Join heuristic:** model từ chối vì không có khóa nối (enodeb_id ↔ station_code), trong khi gold dùng `SUBSTR(station_code, -4)`. Từ chối là hợp lý nếu DE không xác nhận luật nối này | H015, H045, H050, H022, H047 |
| F21 | **Quy ước proposed KQI (−10 không hợp lệ) xung đột với gold H051:** gold lấy giá trị thô −10 | H051 |
| F22 | **Khớp cụm từ cứng dễ vỡ:** "cell **5G** xấu" không khớp "cell xấu"; "chưa **được** đóng" không khớp "chưa đóng". Đã thêm biến thể, nhưng về lâu dài cần khớp theo embedding hoặc Glossary Term của OM | registry `applies_when` |

## 7. Hạn chế

1. **Glossary và câu hỏi do cùng một người viết**, người này đã biết domain của benchmark. Vì vậy các con số sau đều **lạc quan**: recall 95% của khối chọn bảng, recall 100% của cổng hỏi lại (mẫu mơ hồ được viết khi đã biết 5 câu ambiguous), và mức +10 điểm của các `note`. Cần một tập **held-out**: 30–50 câu do người khác viết (DE hoặc người dùng thật), không xem glossary.
2. **Dao động ±5–6 điểm** giữa hai lần chạy. Mọi chênh lệch nhỏ hơn mức này (C2 so với C1, C4 so với C3, C5 so với C4) chưa có ý nghĩa. Cần chạy 3 lần mỗi cấu hình và báo trung bình ± độ lệch.
3. Mới có **một model chạy đầy đủ**. qwen mới xong B0.
4. **M3 (mô tả do DE viết) chưa có.** Các `note` trong glossary là bản xấp xỉ M3 cho vài khái niệm.
5. Dữ liệu synthetic vẫn còn các vấn đề của Phase 1 (F10: 5.766/5.865 cột hằng).

## 8. Việc tiếp theo

1. **Nạp thêm credit OpenRouter** rồi chạy tiếp; cache sẽ tự bù đúng các case còn thiếu:
   ```bash
   python "sample data/synthetic/vtnet-mini/scripts/run_ablation.py" --configs C3,C4,C5,C6,C6m1,C7,C6r
   python "sample data/synthetic/vtnet-mini/scripts/run_ablation.py" --configs B0,C3,C6 --model qwen/qwen-2.5-coder-32b-instruct
   ```
2. Tập câu hỏi held-out do người khác viết, chấm bằng cùng evaluator.
3. DE duyệt F17–F22, các `note` trong glossary và 8 quy ước proposed.
4. Đồng bộ glossary sang OM Glossary Terms khi có OM trên VM.

## 9. Tái lập

```bash
cd "sample data/synthetic/vtnet-mini"
python scripts/validate_conventions.py                  # 52 fixture
python scripts/build_v1_1_assets.py && python scripts/audit_v1_1_assets.py
python scripts/run_ablation.py --rescore reports/ablation/gpt-oss-120b/run1_before_fixes   # chấm lại, không gọi LLM
cd ../../.. && python -m pytest tests/unit/verified_context tests/unit/evaluation tests/unit/architecture -q
```

Kết quả thô từng case: `reports/ablation/<model>/<config>.jsonl` (đầu ra pipeline, gồm trace từng khối) và `.scored.jsonl` (verdict).
