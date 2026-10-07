# T2S: hỏi dữ liệu viễn thông bằng tiếng Việt

Người dùng hỏi bằng tiếng Việt, hệ thống chọn bảng, sinh SQL, kiểm chứng rồi chạy
trên kho dữ liệu, hoặc hỏi lại / từ chối khi câu hỏi mơ hồ hay ngoài phạm vi.

## Hai pipeline

| Pipeline | Mã nguồn | Chạy trên | Dùng ở đâu |
|---|---|---|---|
| **Verified context** (chính) | `src/t2s/verified_context/` | DuckDB của VTNet Mini | Web (CSDL `vtnet_mini`), benchmark 123 câu |
| Runtime lakehouse | phần còn lại của `src/t2s/` (grounding, solver, verification, orchestration…) | Trino (lakehouse lab) hoặc SQLite | Web (CSDL `telecom_lakehouse`, CSDL tự nhập), REST API `/v1/query` cho n8n |

Hai pipeline độc lập: `verified_context` không import gì từ runtime lakehouse.

## Cấu trúc thư mục

```
src/t2s/
  verified_context/      pipeline chính: liên kết thuật ngữ, profiler, prompt, quy ước, cổng, phản hồi
  evaluation/            selective_scoring.py: bộ chấm A–F của benchmark 123 câu
  bootstrap/             dựng runtime: từ Settings (REST API) và từ tables.json (web)
  api/  main.py          REST API /v1/query (uvicorn t2s.main:app)
  grounding/ solver/ verification/ orchestration/ runtime/ semantics/
  catalog/ database/ integrations/ security/ contracts/ configuration/ ...
backend/                 web server FastAPI (run_web.py, cổng 8080)
frontend/                giao diện web và trang duyệt phản hồi (review.html)
workers/                 đồng bộ / đánh chỉ mục metadata
prompts/                 prompt theo phiên bản của runtime lakehouse
datasets/
  vtnet_mini/            VTNet Mini: DuckDB, metadata, quy ước, benchmark_v2 (123 câu), script, kết quả ablation
  telecom_synthetic/     bộ 400 bảng tổng hợp nạp lên lakehouse Trino
  source_samples/        mẫu thật: query.md, CSV, ghi chú metadata
data/
  lakehouse/tables.json  metadata lakehouse cho runtime Trino
  imported_databases/    CSDL người dùng nhập qua web
deploy/
  telecom_lab/           MinIO + Hive Metastore + Trino + OpenMetadata
  n8n/                   workflow n8n gọi REST API
docs/
  13–15                  slide, kịch bản thuyết trình, báo cáo tiến độ và benchmark
  vtnet_mini/            kế hoạch (plan/) và kết quả đánh giá (review/)
  deployment/            hướng dẫn triển khai lab và n8n
  archive/               tài liệu thiết kế giai đoạn nghiên cứu trước VTNet Mini
tests/                   unit/ và integration/
```

## Bắt đầu

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env          # điền VLLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME
```

Web (cổng 8080):

```bash
.venv/bin/python run_web.py
```

REST API cho n8n (cổng 8000). Cần `RUNTIME_SQLITE_DATABASE_PATH` trỏ tới một CSDL có dữ liệu, xem `.env.example`:

```bash
.venv/bin/uvicorn t2s.main:app --host 127.0.0.1 --port 8000
```

Test:

```bash
.venv/bin/python -m pytest
```

## Benchmark 123 câu (VTNet Mini)

Chạy lại (gọi LLM, kết quả lưu cache theo config/model/câu):

```bash
.venv/bin/python datasets/vtnet_mini/scripts/run_ablation.py --configs C6
```

Chấm lại kết quả đã lưu, không gọi LLM (lệnh ghi đè file trong thư mục chỉ định):

```bash
.venv/bin/python datasets/vtnet_mini/scripts/run_ablation.py --rescore datasets/vtnet_mini/reports/ablation/gpt-oss-120b/run1_before_fixes
```

Ý nghĩa các config và số liệu: `docs/vtnet_mini/review/08_verified_context_results.md`.
Kết quả đủ 123 câu của mọi config nằm trong `reports/ablation/gpt-oss-120b/run1_before_fixes/`;
thư mục cha chứa các lượt chạy sau khi sửa nhưng chưa đủ 123 câu.

## Lakehouse lab

```bash
cd deploy/telecom_lab
docker compose --env-file .env up -d minio metastore-db hive-metastore trino
```

Chi tiết: `docs/deployment/telecom_lab_pipeline_plan.md`.

## Hạn chế đã biết

- `verified_context` sinh SQL dialect DuckDB; chưa chạy trực tiếp trên Trino.
- Case E009 của benchmark không tất định: `ORDER BY … LIMIT 5` cắt giữa các giá trị bằng nhau,
  nên mỗi lần chấm có thể cho A hoặc B3.
- `datasets/vtnet_mini/scripts/run_query_md.py` lỗi `Mismatch row count: 16 vs 10`.
- Web dùng một danh tính cố định (`user_analyst`), chưa có đăng nhập và phân quyền theo người dùng.
