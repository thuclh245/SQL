# 03 — Kế hoạch chi tiết VTNet Mini V1.1

## Mục tiêu

Biến VTNet Mini từ một **benchmark tự nhất quán** thành một **testbed đo được đóng góp chính của dự án**, và giữ nó sẵn sàng để chuyển lên OpenMetadata trên VM.

Luận điểm mà testbed phải kiểm chứng được:

> Trong datalake viễn thông doanh nghiệp, SQL sai-mà-trông-đúng chủ yếu đến từ **quy ước dữ liệu không được ghi lại** (kiểu lưu, định dạng, bảng thay thế, luật loại trừ, grain) và **metadata không đáng tin** (chủ yếu do AI sinh hoặc bỏ trống), chứ không phải từ độ khó cú pháp SQL. Một hệ thống kiểm chứng được các quy ước này và biết từ chối khi thiếu bằng chứng sẽ đạt độ chính xác cao hơn ở cùng mức coverage.

## Ràng buộc giữ nguyên từ V1

- 4 domain bắt buộc: Network KPI/5G, Alarm, FBB, Data Monitoring; **mỗi domain ≥ 20 bảng**.
- Engine local là DuckDB; giữ song song `gold_sql_trino`.
- Metadata seed lấy từ `VTNet-presto-OM.xlsx`.
- OM thật nằm trên VM, dùng ở Phase 7.
- Seed cố định, mọi expected result phải sinh lại được.

## Tổng quan phase

| Phase | Nội dung | Thời gian | Phụ thuộc |
|---|---|---|---|
| 0 | Chốt baseline | 0,5 ngày | — |
| 1 | Mở rộng dữ liệu, giảm tỷ lệ bẫy | 3–4 ngày | 0 |
| 2 | Registry quy ước dữ liệu | 2 ngày | 0 |
| 3 | Benchmark v2: tách vai, kiểm tra chéo | 4–5 ngày | 1, 2 |
| 4 | Các phiên bản metadata M0–M3 | 2 ngày | 1 |
| 5 | Chạy lõi `src/t2s` thật trên DuckDB | 3–4 ngày | 0 |
| 6 | Ma trận thí nghiệm | 3 ngày | 3, 4, 5 |
| 7 | Đưa lên OM trên VM | 2–3 ngày | 4, 6 |

Tổng cộng khoảng **3–4 tuần**. Phase 1, 2 và 5 chạy song song được.

```
0 ─┬─ 1 ─┬─ 3 ─┐
   │     └─ 4 ─┼─ 6 ─ 7
   ├─ 2 ───────┘ (vào 3)
   └─ 5 ───────┘
```

---

## Phase 0 — Chốt baseline (0,5 ngày)

| Việc | Output |
|---|---|
| `git switch read_mini_viettel` (đang detached HEAD tại `42d65de`) | Làm việc trên nhánh thật |
| Gắn tag bản hiện tại | `vtnet-mini-v1.0` |
| Gắn nhãn `SIMULATED` vào `reports/nl2sql_error_analysis.md` và `benchmark/evaluation_report.json` | Không ai hiểu nhầm 93% là kết quả thật |
| Cập nhật `vtnet-mini-plan/02_schema_table_plan.md` theo tên bảng thật đã dùng | Plan khớp với thực tế |

**Hoàn thành khi:** có tag, và báo cáo đã có nhãn.

---

## Phase 1 — Mở rộng dữ liệu, giảm tỷ lệ bẫy (3–4 ngày)

### 1.1 Quy mô

| Hạng mục | V1.0 | V1.1 |
|---|---|---|
| Cell 5G | 63 | 2.000–5.000 |
| Site | — | 700–1.500 |
| Tỉnh / khu vực | — | 12–20 / 4 |
| Khoảng thời gian | 20 ngày | 2026-06-01 → 2026-08-31 (92 ngày) |
| Khung giờ | 2 | 24 ở bảng hourly; bảng daily giữ grain ngày |
| Tổng dòng | 1.770 | 0,5M–2M |
| Thuê bao FBB / account PPPoE | — | 20k–100k |
| Alarm event | — | 50k–200k |

Để DuckDB file gọn, bảng lớn có thể lưu Parquet và tạo view trong DuckDB.

### 1.2 Phân phối nền (không random đều)

- Throughput: log-normal theo vendor/công nghệ; giảm vào giờ cao điểm (19–22h).
- Traffic: theo chu kỳ ngày/tuần, và theo quy mô tỉnh.
- Alarm: Poisson theo site; severity lệch (CRITICAL ít); thời gian clear có đuôi dài.
- FBB: phần lớn thuê bao active có session; một phần nhỏ không có.
- Data Monitoring: phần lớn job success; failed-then-retry-success khoảng 3–5%.

### 1.3 Bẫy

Giữ logic A–H nhưng **tỷ lệ bẫy ≤ 5–10% số object**, trộn lẫn trong dữ liệu nền. Bổ sung các bẫy phân biệt mới:

| Bẫy | Bắt được lỗi gì | Case liên quan |
|---|---|---|
| Ngày trống / traffic = 0 giữa chuỗi xấu | LAG theo dòng thay vì ngày lịch | H002 và các case `window_lag`, `streak_detection` |
| Nhiều khung giờ trong một ngày | Đếm giờ thành ngày | H002, M010 |
| Dimension trùng dòng (1 `province_code` → 2 dòng ở bảng phụ) | Join fan-out làm SUM/COUNT bị thổi phồng | các case `fanout_prevention` |
| VARCHAR chứa `''`, `'NaN'`, `'1,5'`, `' 12'` | CAST lỗi hoặc âm thầm ra NULL | các case `type_cast` |
| `f_location` (cũ) vẫn có dữ liệu trông hợp lý nhưng lệch với `f_location_new` | Chọn bảng deprecated | case chọn bảng |
| NULL ở khóa join | INNER thay cho LEFT làm mất dòng | case `left_join` |
| Sự kiện qua mốc 00:00 (+07) | Sai biên ngày/timezone | case `date_boundary` |
| Job failed rồi retry success cùng ngày | Đếm failed thô thay vì trạng thái cuối | case Data Monitoring |

**Bẫy theo lớp, không vá theo case.** Mỗi loại bẫy được sinh với tỷ lệ cố định trên toàn bộ dữ liệu, không gắn với ID case nào. Bỏ dần 14 chỗ chèn dữ liệu riêng cho từng case trong `generate_synthetic_data.py` (review 02 §8). Grain `peak_view` phải được DE chốt trước khi sinh lại (1 dòng/cell/ngày theo query production, hoặc ghi rõ thành quy ước nếu không phải).

### 1.4 Mutation test v2

Mở rộng `scripts/test_benchmark_mutations.py` với các mutant tinh vi:

| Mutant | Mô tả |
|---|---|
| `GT_TO_GTE` | `>` ↔ `>=`, `<` ↔ `<=` |
| `DISTINCT_DROP_IN_COUNT` | `COUNT(DISTINCT x)` → `COUNT(x)` |
| `LEFT_TO_INNER` | `LEFT JOIN` → `JOIN` |
| `DROP_CAST` | Bỏ `CAST(... AS DOUBLE)` |
| `SWAP_TABLE_DEPRECATED` | `f_location_new` → `f_location` |
| `ROW_LAG_FOR_CALENDAR` | Thay logic ngày lịch bằng LAG theo dòng |
| `DROP_EXCLUSION` | Bỏ `NOT EXISTS occean_cell / blacklist` |
| `ISO_DATE_LITERAL` | `20260820` → `'2026-08-20'` với cột `date_id` |

**Hoàn thành khi:**
- Validation A–H và các bẫy mới đều PASS.
- Tỷ lệ bẫy ≤ 10%.
- Mutation kill rate ≥ 95% trên cả mutant thô và mutant tinh vi. Mutant nào sống sót thì phải thêm dữ liệu phân biệt **theo lớp** hoặc ghi rõ là tương đương về ngữ nghĩa.
- Có một bộ mutant **held-out** (người sinh dữ liệu không được thấy) với kill rate ≥ 90%, dùng làm thước đo độc lập.
- Không còn chỗ chèn dữ liệu nào gắn với ID case trong generator.
- 100/100 gold chạy được; không case nào rỗng ngoài chủ đích.

---

## Phase 2 — Registry quy ước dữ liệu (2 ngày)

Tạo `vtnet-mini/conventions/conventions.yaml` theo template `04_conventions_template.yaml`. Mục tiêu: **15–25 quy ước**, mỗi quy ước có:

- `id`, `type` (`storage` / `format` / `supersession` / `exclusion` / `grain` / `scope_default`)
- `scope` (bảng/cột), `trigger_terms` (từ ngữ nghiệp vụ tiếng Việt kích hoạt quy ước)
- `rule` (mô tả cho người đọc), `check` (mẫu kiểm tra AST/SQL mà máy chạy được)
- `om_mapping` (tag/glossary tương ứng trong OM)
- `evidence` (dòng nào trong Excel OM hoặc query mẫu nào chứng minh quy ước này)

Gắn danh sách `conventions` vào từng case benchmark (Phase 3).

**Hoàn thành khi:** có ≥ 15 quy ước, mỗi quy ước có `check` chạy được trên ít nhất 1 gold và 1 mutant vi phạm.

---

## Phase 3 — Benchmark v2: tách vai và kiểm tra chéo (4–5 ngày)

### 3.1 Tách vai sinh câu hỏi

| Vai | Input | Output | Ràng buộc |
|---|---|---|---|
| Agent A (gold writer) | Schema + quy ước + ý định nghiệp vụ | `gold_sql_duckdb`, `gold_sql_trino` | — |
| Agent B (question writer) | Ý định nghiệp vụ + kết quả gold, **không** thấy SQL | `question_natural` | Không được nhắc tên bảng, tên cột hay từ khóa SQL |

Giữ câu hỏi hiện tại làm `question_explicit`. Đo khoảng cách EX giữa `explicit` và `natural`: đó chính là độ khó của việc hiểu nghiệp vụ và retrieval.

### 3.2 Chú thích kép (dual annotation)

Agent C (model hoặc prompt khác A) chỉ nhận `question_natural` + schema, rồi tự viết SQL. So kết quả với gold:
- **Khớp:** chuyển trạng thái `agent_crosschecked`.
- **Lệch:** đưa vào hàng đợi DE review, ghi lý do lệch (gold sai / câu hỏi mơ hồ / agent C sai).

Có thể làm bước này ngay trên 100 case hiện tại, trước cả Phase 1. Chi phí thấp mà bắt được các lỗi kiểu H012.

### 3.3 Câu có expected outcome khác "answer"

Thêm **15–20 câu**:

| Loại | Số câu | Ví dụ |
|---|---|---|
| `unanswerable`: metric không tồn tại | 4–5 | "Tỷ lệ hài lòng NPS của thuê bao FTTH theo tỉnh" (không có bảng NPS) |
| `unanswerable`: ngoài phạm vi dữ liệu | 3–4 | "Throughput 5G tháng 12/2025" |
| `unanswerable`: không có quyền / ngoài domain | 2–3 | Dữ liệu cá nhân chi tiết của thuê bao |
| `ambiguous`: metric đa nghĩa | 4–5 | "Lưu lượng của cell X" (DL / UL / tổng?) |
| `ambiguous`: grain/địa bàn đa nghĩa | 2–3 | "Khu vực miền Bắc" (area hay tập tỉnh?) |

Mỗi câu kèm `expected_outcome_reason`, và với `ambiguous` thì kèm `clarification_options`.

### 3.4 Cân lại domain

Data Monitoring hiện chỉ có 5 case (plan là 15). Bổ sung để đạt **≥ 12**.

### 3.5 Trạng thái review

`draft → agent_crosschecked → de_reviewed → approved`, có ghi `reviewer` và `reviewed_at`. DE review **100% case hard** và mọi case lệch ở 3.2; lấy mẫu 30% case easy/medium. Checklist: `06_de_review_checklist.md`.

**Hoàn thành khi:**
- 100% case có `question_natural`, `conventions`, `trap_groups`, `expected_outcome`.
- 100% case hard ở trạng thái ≥ `de_reviewed`.
- Mọi case lệch ở 3.2 đã được xử lý.
- Có ≥ 15 câu `unanswerable`/`ambiguous`.
- H002 và H012 đã được sửa.

---

## Phase 4 — Các phiên bản metadata (2 ngày)

| Phiên bản | Nội dung | Cách tạo |
|---|---|---|
| **M0** | Tên + kiểu, không mô tả | Xóa description |
| **M1** | Mô tả AI sinh như hiện tại, giữ nhãn `[AI Gen]` | Giữ nguyên |
| **M2** | Đã xác minh bằng dữ liệu | Profiler tự động (bên dưới) + sửa mô tả sai |
| **M3** | Người viết tay cho khoảng 20 bảng lõi | DE viết; dùng làm mốc trên |

Profiler cho M2 suy ra:
- VARCHAR mà ≥ 99% giá trị parse được thành số → gắn quy ước "cần CAST".
- Cột có toàn giá trị 8 chữ số dạng ngày → định dạng `YYYYMMDD`.
- Overlap giá trị giữa hai cột ≥ 95%, và một bên unique → ứng viên khóa join (bổ sung vào 17 join path hiện có).
- Hai bảng gần trùng schema, một bảng có freshness cũ → đánh dấu deprecated.
- Mô tả AI mâu thuẫn với dữ liệu (ví dụ `object_id` được gọi là "chưa xác định" nhưng thực tế là khóa join) → ghi đè và lưu lý do.

Output: `vtnet-mini/metadata/variants/{M0,M1,M2,M3}/catalog.json` cùng một format. Mỗi mô tả có `source` ∈ {`om_excel`, `ai_gen`, `profiler`, `human`} và `evidence`.

**Hoàn thành khi:** có 4 phiên bản cùng format; M2 có báo cáo về số mô tả đã sửa và số quy ước đã suy ra.

---

## Phase 5 — Chạy lõi `src/t2s` thật trên DuckDB (3–4 ngày)

| Việc | File dự kiến |
|---|---|
| Executor read-only cho DuckDB theo `query_executor_port.py` | `src/t2s/database/duckdb_read_only_query_executor.py` |
| Readiness inspector | `src/t2s/database/duckdb_readiness_inspector.py` |
| Value probe theo `value_probe_port.py` | `src/t2s/grounding/value_grounding/duckdb_value_probe.py` |
| Catalog provider đọc `metadata/variants/*` | `src/t2s/catalog/vtnet_variant_metadata_provider.py` |
| Nối vào `AdaptiveOrchestrator` qua `bootstrap/runtime_factory.py`; `DuckDBRuntime` trong backend gọi lõi thay vì tự làm pipeline | `backend/services/runtime_service.py` |
| Runner benchmark ghi `predictions_real_{pipeline}_{metadata}_{question}.jsonl` | `vtnet-mini/scripts/run_real_benchmark.py` |

Model: gpt-oss-120b qua vLLM. Ghi lại model id, tham số sinh, seed và commit.

**Hoàn thành khi:** chạy trọn 100 case bằng model thật với M1 + `question_explicit`, có trace đầy đủ (grounding context, SQL, kết quả, lý do escalation/abstain).

---

## Phase 6 — Ma trận thí nghiệm (3 ngày)

| Trục | Mức |
|---|---|
| Pipeline | **P0** direct prompt (full schema của domain) · **P1** lõi `src/t2s` · **P2** P1 + kiểm tra quy ước (Phase 2) + cho phép abstain |
| Metadata | M0 · M1 · M2 · M3 |
| Câu hỏi | `explicit` · `natural` |

Tổng cộng 24 cấu hình. Nếu thiếu thời gian, ưu tiên: P0/P1/P2 × M1/M2 × `natural`.

**Chỉ số:**
- EX tổng và theo độ khó/domain.
- **Tỷ lệ bắt lỗi theo từng quy ước và từng nhóm bẫy.**
- Với câu `unanswerable`/`ambiguous`: precision và recall của abstain/clarify.
- Đường cong precision–coverage (P2 so với P0/P1).
- Phân loại nguyên nhân lỗi: retrieval / quy ước / logic / metadata sai / dialect.
- 2–3 lần chạy (seed khác nhau) để có khoảng tin cậy.

**Output trung tâm:** một bảng P × M × Q và một hình precision–coverage. Đây là kết quả chính của dự án.

**Hoàn thành khi:** có bảng kết quả, hình, và báo cáo phân loại lỗi, tất cả chạy lại được bằng một lệnh.

---

## Phase 7 — Đưa lên OM trên VM (2–3 ngày, làm sau)

| Việc | Ghi chú |
|---|---|
| Ingest `om_ingest/` cho M1 và M2 | Tách service hoặc dùng tag phiên bản để không trộn lẫn |
| Map quy ước sang tag/glossary OM | Dựa trên `om_mapping` ở Phase 2 |
| Tắt/bật OM provider so với provider tĩnh | Dùng `openmetadata_provider.py` sẵn có |
| So retrieval: provider tĩnh vs OM search | Recall bảng/cột cần thiết trên benchmark v2 |
| Parity check | Theo tiền lệ live-vs-versioned parity guard ở P04 |
| (Tùy chọn) Load dữ liệu lên Trino trên VM | Chạy `gold_sql_trino` để kiểm tra dialect |

**Hoàn thành khi:** có kết quả retrieval qua OM thật cho M1 và M2, và parity với provider tĩnh.

---

## Điều kiện hoàn thành V1.1

- [ ] Tỷ lệ bẫy ≤ 10%; dữ liệu 0,5M–2M dòng; 92 ngày; 24 giờ ở bảng hourly
- [ ] Mutation kill rate ≥ 95% (thô + tinh vi)
- [ ] ≥ 15 quy ước có `check` chạy được
- [ ] 100% case hard `de_reviewed`; mọi case lệch ở chú thích kép đã xử lý; H002, H012 đã sửa
- [ ] ≥ 15 câu `unanswerable`/`ambiguous`; Data Monitoring ≥ 12 case
- [ ] 4 phiên bản metadata M0–M3 cùng format
- [ ] Lõi `src/t2s` chạy 100 case bằng model thật
- [ ] Bảng kết quả P × M × Q + hình precision–coverage

## Thứ tự ưu tiên nếu thời gian gấp

1. Phase 0
2. Phase 3.2: chú thích kép trên 100 case hiện tại (rẻ, sửa được gold ngay)
3. Phase 5: chạy lõi thật
4. Phase 4: M0/M1/M2
5. Phase 6 trên 50 case hard

Phase 1 (mở rộng dữ liệu) làm song song với 2–5.

## Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Agent B/C dùng cùng model với A nên mắc cùng thiên lệch | Dùng model khác hoặc prompt khác hẳn; DE review mọi case lệch |
| Dữ liệu lớn làm DuckDB chậm và test lâu | Parquet + view; tạo subset nhỏ cho CI |
| Quy ước tự đặt không giống production | Mỗi quy ước bắt buộc có `evidence` từ Excel OM hoặc query mẫu; DE xác nhận |
| M2 profiler "gian lận" vì dữ liệu do chính mình sinh | Chạy profiler mù (không đọc generator); ghi rõ hạn chế; về sau kiểm lại trên OM thật |
| Không có DE đủ thời gian review | Ưu tiên case hard và case lệch; ghi rõ case nào chưa review trong báo cáo |
