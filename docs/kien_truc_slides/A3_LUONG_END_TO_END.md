# A3 — Vòng đời của một câu hỏi (End-to-end)

**Thông điệp chính:** Giữa lúc người dùng bấm Enter và lúc nhìn thấy số liệu, câu SQL do LLM sinh ra phải **vượt qua 6 chốt chặn độc lập**. Bất kỳ chốt nào không thoả mãn đều dẫn tới `AMBIGUOUS` hoặc `ABSTAIN` — không có đường tắt "cứ chạy thử".

## Nội dung slide (dán thẳng)

- Một câu hỏi = một `run_id`, có dấu vết đầy đủ (trace) qua mọi trạng thái — kiểm toán được từng bước.
- LLM được gọi **1 lần** trên đường chính. Không có vòng lặp "nghĩ lại" chung chung.
- Trước khi chạm DB thật: parse AST → chặn không phải SELECT → kiểm tra quyền trên từng bảng/cột được tham chiếu → EXPLAIN ước lượng chi phí.
- Kết thúc luôn là 1 trong 3 trạng thái công khai: `ANSWER` / `AMBIGUOUS` / `ABSTAIN`.

## Mermaid — Sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant API as API /v1/query
    participant RT as TextToSqlRuntime
    participant SEC as Security
    participant GR as Grounding
    participant LLM as Solver → vLLM 120B
    participant V as Verification
    participant GW as 🔒 DB Gateway
    participant DB as ClickHouse / StarRocks / PostgreSQL

    U->>API: Câu hỏi + token định danh
    API->>RT: QueryRequest + UserIdentity (run_id)
    RT->>SEC: Lấy danh sách tài nguyên được phép
    SEC-->>RT: Tập bảng/cột trong quyền hạn

    RT->>GR: Dựng ngữ cảnh (chỉ trong phạm vi được phép)
    GR->>GR: Truy hồi → xếp hạng → mở rộng quan hệ → cắt cột
    GR-->>RT: GroundingContext (≤8 bảng, ≤60 cột) + danh sách "chưa giải quyết được"

    alt Ngữ cảnh không đủ / định danh không tồn tại
        RT-->>U: ABSTAIN — nêu rõ thiếu dữ liệu gì
    end

    RT->>LLM: Prompt tối giản (schema đã chọn + phương ngữ đích)
    LLM-->>RT: SqlCandidate (chưa được tin)

    RT->>V: Kiểm chứng
    V->>V: L1 parse AST · L2 SELECT-only · L3 quyền truy cập · L4 bất biến cấu trúc
    alt Vi phạm an toàn hoặc quyền
        V-->>RT: REJECT
        RT-->>U: ABSTAIN — lý do cụ thể (không lộ thông tin nhạy cảm)
    end
    V-->>RT: PASS + danh sách bằng chứng

    RT->>GW: EXPLAIN (ước lượng chi phí, phát hiện fan-out)
    GW->>DB: EXPLAIN
    DB-->>GW: Kế hoạch thực thi
    GW-->>RT: Chi phí ước lượng
    alt Chi phí vượt ngưỡng / thiếu lọc phân vùng
        RT-->>U: ABSTAIN — truy vấn quá nặng, đề xuất thu hẹp phạm vi
    end

    RT->>GW: Thực thi có kiểm soát (timeout, giới hạn dòng, quyền của người dùng)
    GW->>DB: SELECT …
    DB-->>GW: Tập kết quả
    GW->>GW: Ghi QueryAuditEvent (ai · SQL nào · lúc nào · kết quả)
    GW-->>RT: Kết quả + số liệu thực thi

    RT-->>API: ANSWER — dữ liệu + SQL + giải thích + dấu vết bằng chứng
    API-->>U: Kết quả kèm bảng/cột/giá trị đã dùng
```

## Mermaid — Rút gọn cho slide chật (nếu sequence quá dài)

```mermaid
flowchart LR
    Q["Câu hỏi"] --> S["🔒 Danh tính<br/>& phạm vi ACL"]
    S --> G["Grounding<br/>9.000 → ≤8 bảng"]
    G --> L(["LLM 120B<br/>sinh 1 SQL"])
    L --> V["Kiểm chứng<br/>AST · an toàn · quyền · bất biến"]
    V --> E["🔒 EXPLAIN<br/>ước lượng chi phí"]
    E --> X["Thực thi có giới hạn<br/>timeout · row limit · audit"]
    X --> D{"Đủ bằng chứng?"}
    D -->|Có| A["ANSWER"]
    D -->|Mơ hồ xác định được| M["AMBIGUOUS"]
    D -->|Không| AB["ABSTAIN"]
    style L stroke-dasharray: 5 5
```

## Ánh xạ mã nguồn

| Bước | Mã nguồn |
|---|---|
| Máy trạng thái vòng đời | `src/t2s/runtime/text_to_sql_runtime.py` (`execute_query_pipeline`) |
| Các trạng thái & trace | `src/t2s/runtime/runtime_contracts.py` (`RuntimeState`, `StateTransitionRecord`) |
| Dựng ngữ cảnh | `src/t2s/grounding/grounding_context_builder.py` |
| Gọi LLM | `src/t2s/solver/direct_sql_solver.py` |
| Chốt kiểm chứng | `src/t2s/verification/` |
| EXPLAIN + thực thi + audit | `src/t2s/database/secure_query_executor.py` |

**Các trạng thái kết thúc có thật trong mã** (`RuntimeStatus`): `completed`, `unresolved`, `generation_failed`, `safety_rejected`, `access_denied`, `execution_failed`, `timeout` — dùng đúng các tên này khi nói về telemetry để hội đồng thấy đây không phải sơ đồ vẽ cho đẹp.

## Phản biện thường gặp

- *"Nhiều chốt thế thì độ trễ ra sao?"* → Các chốt xác định (parse AST, kiểm tra quyền, bất biến cấu trúc) tính bằng mili-giây, chi phí thực tế nằm ở 1 lần gọi LLM và EXPLAIN. Số đo độ trễ p50/p95: `⟨TBD⟩`.
- *"Chốt nào tốn kém nhất?"* → EXPLAIN trên DB thật. Bù lại, chính nó ngăn được sự cố nghẽn cụm (A7).
