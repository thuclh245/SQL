# 07 — Trạng thái thực hiện V1.1 (2026-09-24)

Ghi lại những gì đã làm theo `03_plan_v1_1.md`, cách kiểm chứng, và việc còn lại. Mọi con số dưới đây đều tái lập được bằng các lệnh ở cuối file.

## Tóm tắt

| Phase | Trạng thái | Ghi chú |
|---|---|---|
| 0 Chốt baseline | ~80% | Đã gắn nhãn SIMULATED; **chưa gắn tag git** (đang detached HEAD) |
| 1 Mở rộng dữ liệu | 0% (đã định lượng vấn đề) | Cần sửa generator: xem phát hiện mới bên dưới |
| 2 Registry quy ước | ~75% | 11 accepted (có số dòng `query.md`) + 8 proposed; validator AST; **chưa có DE xác nhận** |
| 3 Benchmark v2 | ~60% | 124 case; câu hỏi nghiệp vụ viết tay; **chưa có chú thích kép độc lập, chưa DE review** |
| 4 Metadata variants | ~65% | M0/M1/M2 đúng provenance; M2 từ profiler; **M3 cần DE viết** |
| 5–7 | ~40% | Pipeline chạy thật với LLM qua OpenRouter; ablation lượt 1 xong, lượt 2 dang dở vì hết credit (xem 08). OM trên VM vẫn chưa có |

## Đã làm

### Benchmark v2 (`vtnet-mini/benchmark_v2/`)
- **124 case**, chấm điểm 123: 106 answer, 12 unanswerable, 5 ambiguous. H012 có `case_status: blocked_by_data` và bị loại khỏi chấm điểm (không gắn unanswerable: câu hỏi hợp lệ, lỗi nằm ở dữ liệu).
- **100 câu `question_natural` viết tay** (`natural_questions.json`): không tên bảng/cột, không từ khóa SQL, giữ đúng ngữ nghĩa gold kể cả điều kiện ẩn, không nêu quy ước mà hệ thống phải tự biết. Hạn chế: người viết có xem gold, nên đây chưa phải chú thích kép.
- **Gold đã sửa:** H002 (chuỗi ngày lịch, chạy được), H027 (thêm tiêu chí phụ cho NTILE), H012 (gom theo `unit_id`, nhưng bị chặn bởi dữ liệu).
- **Hash tính lại** cho mọi gold bằng cùng cách chuẩn hóa với V1; chạy 3 lần với số thread khác nhau để phát hiện kết quả không ổn định.
- **Data Monitoring: 12 câu answer** (5 cũ + 7 mới) chỉ dùng các cột có dữ liệu thật (`kqi_monitor_web`, `usersinarea_blacklist_enodeb_id`).
- **Unanswerable (12):** lý do được đối chiếu với catalog. Có 4 bẫy đồng âm có thật: `nps_*` (counter 5G, không phải NPS), `population`, `update_user`, `cpu/memory`. U003 là từ chối theo chính sách (catalog **có** `msisdn`). A005/A007 cũ chuyển thành U012/U011.
- **Ambiguous (5):** mỗi cách hiểu có gold riêng nếu dữ liệu cho phép, còn lại ghi `blocked_reason` cụ thể.
- **`conventions` suy ra từ câu hỏi và bảng, không từ gold**, nên có thể phát hiện gold vi phạm (`convention_conflicts`).
- **`review_flags`** ghi các vấn đề phát hiện khi viết lại câu hỏi (xem bên dưới).

### Quy ước (`vtnet-mini/conventions/conventions.yaml`)
- 11 quy ước `accepted`, mỗi quy ước có **số dòng cụ thể trong `sample data/query.md`**. 8 quy ước `proposed` ghi rõ vì sao chưa có nguồn; đã sửa các evidence bị ghi nhầm nguồn trước đó (AAA, DISTINCT dimension).
- Thêm 2 quy ước có trong query.md mà bản trước bỏ sót: loại throughput = 0 (dòng 19) và snapshot occean_cell (dòng 24).
- `scripts/convention_checks.py` kiểm tra bằng **AST (sqlglot)**. 47 fixture đều đúng: 27 SQL đúng được chấp nhận (alias, `::DOUBLE`, TRY_CAST, so sánh đảo chiều, 3 dạng anti-join, `AVG(...) < 5`) và 20 SQL vi phạm bị bắt.

### Metadata (`vtnet-mini/metadata/variants/`)
- **M0:** không mô tả bảng, không mô tả cột.
- **M1:** giữ nguyên mô tả OM; `description_source` khớp với nội dung (`ai_gen` / `om_other` / `none`).
- **M2:** chỉ thêm ghi chú `[Profiler]` từ `profile_report.json`, gồm 36 cột: kiểu số lưu dạng chuỗi, định dạng thời gian, đơn vị epoch, giá trị sentinel, khóa nối. Đã thay 2 mô tả AI sai (`object_id` của peak_view và occean_cell). Cờ constant/placeholder chỉ nằm trong `profile_flags`, không đưa vào mô tả.
- **M3:** không sinh. Có file `NOT_BUILT.md` giải thích lý do.

### Kiểm chứng
- `audit_v1_1_assets.py` **độc lập với builder**: phát hiện rò rỉ dựa trên gold và schema, tính lại hash, chạy mỗi gold 3 lần, kiểm tra provenance khớp với nội dung, kiểm tra M3 không bị làm giả.
- **Đã thử cài 6 lỗi có chủ đích** vào một bản sao (rò rỉ tên bảng, câu cụt, hash sai, gỡ tiêu chí phụ của H027, nhãn `human` giả, M3 giả). Audit bắt đủ cả 6 và thoát với mã 1.
- Build lại từ đầu cho ra `cases.jsonl`, `M2/catalog.json` và `profile_report.json` **giống hệt từng byte**.

## Phát hiện mới trong đợt này

| # | Phát hiện | Mức độ |
|---|---|---|
| F10 | **Chỉ 99/5.865 cột có hơn 1 giá trị**: 5.766 cột hằng (trong đó 2.066 là placeholder `sample_*`). Mọi câu hỏi chạm tới các cột này đều vô nghĩa; value probe/profiling trên phần lớn schema không đo được gì | Rất cao, Phase 1 |
| F11 | **H027 không tái lập được hash V1**: NTILE trên giá trị trùng nhau. Đã sửa | Đã xử lý |
| F12 | **5 gold lệch câu hỏi** (E013, E018, M002, M013, H029) và **5 gold có điều kiện ẩn** (H003, H006, H020, H025, H028); 2 câu trùng nghĩa (E015/E010, E019/E003) | Cao, DE |
| F13 | **6 gold vi phạm quy ước bad-cell của query production** (H002, H029, H034, H035, H045, H050): thiếu VNM, occean_cell, traffic > 0. Hoặc gold sai, hoặc câu hỏi cố ý dùng định nghĩa khác, DE cần chốt | Cao, DE |
| F14 | **Mô tả AI sai về đơn vị**: `kqi_monitor_web.ts` ghi "epoch milliseconds" nhưng dữ liệu là epoch giây (tháng 8/2026) | Minh chứng cho Hướng B |
| F15 | 5 join theo heuristic (SUBSTR/LIKE mã trạm, region = area_code) trong H012, H015, H022, H045, H047 | Trung bình, DE |
| F16 | Nhiều cột thay thế (DL/UL traffic, latency, packet loss) toàn giá trị 0, nên phần lớn cách hiểu của câu ambiguous chưa có gold | Trung bình, Phase 1 |

## Việc còn lại (không làm được nếu thiếu người/hạ tầng)

1. **DE review:** 18 xung đột quy ước, 5 lệch câu hỏi–gold, 5 điều kiện ẩn, 5 join heuristic, định nghĩa "ngày xấu", chính sách PII, xác nhận 11 quy ước `accepted` (`de_confirmed`).
2. **Chú thích kép độc lập (Phase 3.2):** một người/agent **không xem gold** viết SQL từ `question_natural`, sau đó so kết quả.
3. **Phase 1 (generator):** thay placeholder và cột hằng bằng dữ liệu có phân phối; mở rộng quy mô; bẫy theo lớp; bỏ 14 chỗ chèn dữ liệu riêng cho từng case; chốt grain `peak_view`; sửa `od_history.unit_id` để mở khóa H012.
4. **M3:** DE viết mô tả cho khoảng 20 bảng lõi.
5. **Phase 5–7:** vLLM endpoint cho model thật; OM trên VM.
6. Gắn tag `vtnet-mini-v1.0` (baseline) sau khi switch sang nhánh thật.

## Tái lập

```bash
cd "sample data/synthetic/vtnet-mini"
pip install duckdb sqlglot pyyaml
python scripts/profile_vtnet_metadata.py      # -> metadata/variants/M2/profile_report.json
python scripts/build_v1_1_assets.py           # -> benchmark_v2/, metadata/variants/
python scripts/validate_conventions.py        # -> reports/convention_validation.json (exit 1 nếu fixture sai)
python scripts/audit_v1_1_assets.py           # -> reports/v1_1_asset_audit.json (exit 1 nếu có lỗi cứng)
```
