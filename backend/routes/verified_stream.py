"""SSE events for the verified-context pipeline (VTNet Mini).

The pipeline runs as one coroutine; its block traces are then replayed as the
four steps the UI already renders, plus two outcomes the old flow did not have:
``abstain`` (không đủ dữ liệu / ngoài phạm vi / chính sách) and ``clarify``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from backend.services.runtime_service import VerifiedDuckDBRuntime, format_sql
from t2s.verified_context.pipeline import BlockTrace, PipelineResult

TIMEOUT_SECONDS = 150.0
UI_ROWS = 100


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _block(result: PipelineResult, name: str) -> BlockTrace | None:
    return next((t for t in result.trace if t.name == name), None)


def _blocks(result: PipelineResult, *names: str) -> list[BlockTrace]:
    return [t for t in result.trace if t.name in names]


def _step(step: int, name: str, title: str, status: str, detail: str, thinking: Any) -> str:
    return _sse(
        "step",
        {
            "step": step,
            "name": name,
            "title": title,
            "status": status,
            "detail": detail,
            "thinking": thinking,
        },
    )


def _step1_thinking(result: PipelineResult) -> dict[str, Any]:
    linking = _block(result, "linking")
    gates = _block(result, "gates")
    context = _block(result, "context")
    ctx = context.data if context else {}
    return {
        "summary": linking.detail if linking else "",
        "available_tables": [t.rsplit(".", 1)[-1] for t in result.tables]
        or (linking.data.get("tables", []) if linking else []),
        "catalog_foreign_keys": [],
        "evidence_applied": ctx.get("conventions", []),
        "grain_info": {t: " ".join(v) for t, v in (ctx.get("grain") or {}).items()},
        "value_dictionary": ctx.get("values", {}),
        "concepts": linking.data.get("concepts", {}) if linking else {},
        "gate_checks": gates.data.get("checks", []) if gates else [],
        "data_range": gates.data.get("data_range", {}) if gates else {},
    }


def _graph(result: PipelineResult) -> dict[str, Any]:
    context = _block(result, "context")
    tables = (context.data.get("tables") if context else None) or {}
    nodes = [
        {
            "id": t,
            "label": t,
            "role": "primary",
            "is_bridge": False,
            "key_columns": [line.split()[1] for line in lines[:4]],
            "total_columns": len(lines),
            "all_columns": [line.split()[1] for line in lines[:6]],
        }
        for t, lines in tables.items()
    ]
    return {"graph_nodes": nodes, "steiner_edges": [], "bridge_tables": [], "graph_connected": True}


def _checklist(result: PipelineResult) -> list[dict[str, str]]:
    items = []
    for guard in _blocks(result, "guard")[-1:]:
        items.append(
            {
                "rule": "Chỉ đọc (Read-Only Guard)",
                "status": "passed" if guard.status == "done" else "failed",
                "detail": guard.detail,
            }
        )
    violated = {v["convention_id"]: v for v in result.violations}
    for cid in result.conventions:
        v = violated.get(cid)
        items.append(
            {
                "rule": f"Quy ước {cid}",
                "status": "warning" if v else "passed",
                "detail": "; ".join(v["messages"]) if v else "Tuân thủ",
            }
        )
    if result.status == "answered":
        items.append(
            {
                "rule": "Kết quả khác rỗng",
                "status": "passed" if result.row_count else "warning",
                "detail": f"{result.row_count} dòng",
            }
        )
    if result.repairs:
        items.append(
            {
                "rule": "Vòng sửa của verifier",
                "status": "warning",
                "detail": f"Đã yêu cầu model sửa {result.repairs} lần",
            }
        )
    return items


async def verified_events(
    runtime: VerifiedDuckDBRuntime, question: str, db_id: str
) -> AsyncGenerator[str, None]:
    started = time.perf_counter()
    model = runtime.effective_model
    yield _step(
        1,
        "Dò tìm dữ liệu",
        "Bước 1: Chọn bảng theo glossary, cổng kiểm tra & ngữ cảnh đã kiểm chứng",
        "running",
        f"Đang chọn bảng và lắp ngữ cảnh cho '{db_id}'...",
        {},
    )
    try:
        result = await asyncio.wait_for(runtime.run(question), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        yield _sse(
            "error",
            {
                "status": "error",
                "error_message": f"Mô hình không phản hồi trong {int(TIMEOUT_SECONDS)} giây.",
                "total_latency_seconds": round(time.perf_counter() - started, 2),
            },
        )
        return

    step1 = _step1_thinking(result)
    declined = result.status in ("abstain", "clarify")
    gates = _block(result, "gates")
    yield _step(
        1,
        "Dò tìm dữ liệu",
        "Bước 1: Chọn bảng theo glossary, cổng kiểm tra & ngữ cảnh đã kiểm chứng",
        "warning" if declined else "done",
        (
            gates.detail
            if declined and gates
            else (_block(result, "context") or gates or result.trace[0]).detail
        ),
        step1,
    )

    generations = _blocks(result, "generation", "repair")
    step2 = {
        "summary": "; ".join(g.detail for g in generations) or "Không gọi model",
        "referenced_tables": [t.rsplit(".", 1)[-1] for t in result.tables],
        "candidate_sql": format_sql(result.sql, "duckdb") if result.sql else "",
        "graph_warnings": [],
        **_graph(result),
    }
    if generations:
        yield _step(
            2,
            "Sinh SQL",
            f"Bước 2: AI ({model}) sinh SQL",
            "done" if result.status == "answered" else "warning",
            step2["summary"],
            step2,
        )
    else:
        yield _step(2, "Sinh SQL", "Bước 2: Không cần sinh SQL", "skipped", "Đã dừng ở cổng", step2)

    step3 = {
        "summary": "Guardrail chỉ đọc + kiểm chứng quy ước nghiệp vụ (AST)",
        "checklist": _checklist(result) or step1["gate_checks"],
        "findings": [
            {"code": v["convention_id"], "severity": "warning", "message": "; ".join(v["messages"])}
            for v in result.violations
        ],
        "advice": "",
        "referenced_tables": step2["referenced_tables"],
    }
    step3_status = (
        "skipped"
        if not generations
        else "failed"
        if result.status == "error"
        else "warning"
        if result.violations
        else "done"
    )
    yield _step(
        3,
        "Kiểm chứng",
        "Bước 3: Guardrail & kiểm chứng quy ước",
        step3_status,
        f"{len(result.conventions)} quy ước áp dụng, {len(result.violations)} vi phạm còn lại",
        step3,
    )

    total = round(time.perf_counter() - started, 2)
    step4 = {
        "summary": result.message or f"{result.row_count} bản ghi",
        "rows_returned": result.row_count,
        "execution_latency_ms": result.latency_ms,
        "total_elapsed_seconds": total,
    }
    base = {
        "question": question,
        "sql": format_sql(result.sql, "duckdb") if result.sql else "",
        "model_used": model,
        "total_latency_seconds": total,
        "execution_time_ms": result.latency_ms,
        "ast_tables": step2["referenced_tables"],
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.prompt_tokens + result.completion_tokens,
        "thinking_step1": step1,
        "thinking_graph": step2,
        "thinking_ast": step3,
        "thinking_exec": step4,
        "conventions": result.conventions,
        "violations": result.violations,
        "repairs": result.repairs,
    }

    if declined:
        label = "Cần làm rõ câu hỏi" if result.status == "clarify" else "Từ chối trả lời"
        yield _step(4, "Kết quả", f"Bước 4: {label}", "warning", result.message, step4)
        yield _sse(
            "result",
            {
                **base,
                "status": result.status,
                "is_blocked": False,
                "is_execution_failed": False,
                "status_label": label,
                "message": result.message,
                "options": result.options,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error_message": None,
                "guardrails_status": "warning",
                "findings": [result.message],
                "sqlgrade": {"grade": "B", "label": label, "badge": "warning", "findings": []},
            },
        )
        return

    if result.status != "answered":
        yield _step(4, "Kết quả", "Bước 4: Lỗi thực thi", "failed", result.message, step4)
        yield _sse(
            "result",
            {
                **base,
                "status": "execution_failed",
                "is_blocked": False,
                "is_execution_failed": True,
                "status_label": "Lỗi thực thi CSDL",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error_message": result.message,
                "guardrails_status": "warning",
                "findings": [result.message],
                "advice": "Verifier đã yêu cầu model sửa nhưng câu lệnh vẫn lỗi.",
                "sqlgrade": {"grade": "C", "label": "Lỗi thực thi", "badge": "warning"},
            },
        )
        return

    warn = bool(result.violations) or result.row_count == 0
    label = (
        "Có vi phạm quy ước, cần kiểm tra"
        if result.violations
        else "Kết quả rỗng, cần kiểm tra"
        if result.row_count == 0
        else "Đã kiểm chứng (chỉ đọc, tuân thủ quy ước)"
    )
    yield _step(4, "Kết quả", "Bước 4: Thực thi CSDL", "warning" if warn else "done", label, step4)
    yield _sse(
        "result",
        {
            **base,
            "status": "completed",
            "is_blocked": False,
            "is_execution_failed": False,
            "status_label": label,
            "columns": result.columns,
            "rows": result.rows[:UI_ROWS],
            "row_count": result.row_count,
            "error_message": None,
            "guardrails_status": "warning" if warn else "passed",
            "findings": [
                f"{v['convention_id']}: {'; '.join(v['messages'])}" for v in result.violations
            ],
            "sqlgrade": {
                "grade": "B" if warn else "A",
                "label": label,
                "badge": "warning" if warn else "success",
                "findings": [],
                "guardrails_status": "warning" if warn else "passed",
            },
        },
    )
