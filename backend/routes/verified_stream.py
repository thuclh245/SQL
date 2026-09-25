"""SSE events for the verified-context pipeline (VTNet Mini).

The pipeline runs as one coroutine; its block traces are then replayed as the
steps of the UI stepper: chọn dữ liệu → cổng quyết định (step 5, hiển thị ở vị trí
thứ hai) → sinh SQL → kiểm chứng & chạy → kết cục. Hỏi lại (``clarify``) và từ chối
(``abstain``) là kết cục đúng, nên được gửi với status riêng thay vì ``warning``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from backend.services.runtime_service import (
    VerifiedDuckDBRuntime,
    format_sql,
    get_interaction_store,
)
from t2s.verified_context.pipeline import BlockTrace, PipelineResult

LOGGER = logging.getLogger(__name__)
TIMEOUT_SECONDS = 150.0
UI_ROWS = 100


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _block(result: PipelineResult, name: str) -> BlockTrace | None:
    return next((t for t in result.trace if t.name == name), None)


def _blocks(result: PipelineResult, *names: str) -> list[BlockTrace]:
    return [t for t in result.trace if t.name in names]


def _step(
    step: int, name: str, title: str, status: str, detail: str, thinking: Any, label: str = ""
) -> str:
    return _sse(
        "step",
        {
            "step": step,
            "name": name,
            "title": title,
            "status": status,
            "detail": detail,
            "thinking": thinking,
            "label": label,
        },
    )


def _stopped_at(result: PipelineResult) -> str:
    """Khối đã dừng một lượt hỏi lại / từ chối: gate (trước khi gọi model), model, verifier."""
    generations = _blocks(result, "generation", "repair")
    if not generations:
        return "gate"
    if not _blocks(result, "guard"):
        return "model"
    return "verifier"


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


def _record(
    result: PipelineResult,
    question: str,
    db_id: str,
    model: str,
    interaction: dict[str, Any] | None,
) -> str | None:
    """Ghi lượt hỏi vào nhật ký; lỗi ghi nhật ký không được làm hỏng câu trả lời."""
    try:
        return get_interaction_store().record_turn(
            db_id=db_id,
            model=model,
            question=question,
            interaction=interaction,
            status=result.status,
            sql=result.sql,
            tables=result.tables,
            assumptions=result.assumptions,
            message=result.message,
            row_count=result.row_count,
            latency_ms=result.latency_ms,
            tokens=result.prompt_tokens + result.completion_tokens,
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception("Không ghi được nhật ký tương tác")
        return None


async def verified_events(
    runtime: VerifiedDuckDBRuntime,
    question: str,
    db_id: str,
    interaction: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    started = time.perf_counter()
    model = runtime.effective_model
    yield _step(
        1,
        "Chọn dữ liệu",
        "Chọn bảng theo glossary & lắp ngữ cảnh từ dữ liệu thật",
        "running",
        f"Đang chọn bảng và lắp ngữ cảnh cho '{db_id}'...",
        {},
    )
    try:
        result = await asyncio.wait_for(runtime.run(question, interaction), timeout=TIMEOUT_SECONDS)
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

    turn_id = _record(result, question, db_id, model, interaction)
    step1 = _step1_thinking(result)
    declined = result.status in ("abstain", "clarify")
    stopped_at = _stopped_at(result) if declined else ""
    stepper: list[dict[str, str]] = []

    def emit(
        step: int, name: str, title: str, status: str, detail: str, thinking: Any, label: str = ""
    ) -> str:
        stepper.append({"step": step, "status": status, "detail": detail, "label": label})
        return _step(step, name, title, status, detail, thinking, label)

    context = _block(result, "context")
    linking = _block(result, "linking")
    picked = context or linking
    yield emit(
        1,
        "Chọn dữ liệu",
        "Chọn bảng theo glossary & lắp ngữ cảnh từ dữ liệu thật",
        "done",
        picked.detail if picked else "",
        step1,
    )

    gates = _block(result, "gates")
    gate_thinking = {
        "checks": step1["gate_checks"],
        "data_range": step1["data_range"],
        "decision": result.message if stopped_at == "gate" else (gates.detail if gates else ""),
    }
    if stopped_at == "gate":
        yield emit(5, "Cổng quyết định", "Cổng quyết định", result.status, result.message, gate_thinking)
    elif gates is None or gates.status == "skipped":
        yield emit(5, "Cổng quyết định", "Cổng quyết định", "skipped", "Cổng đang tắt", gate_thinking)
    else:
        yield emit(5, "Cổng quyết định", "Cổng quyết định", "done", gates.detail, gate_thinking)

    generations = _blocks(result, "generation", "repair")
    step2 = {
        "summary": "; ".join(g.detail for g in generations) or "Không gọi model",
        "referenced_tables": [t.rsplit(".", 1)[-1] for t in result.tables],
        "candidate_sql": format_sql(result.sql, "duckdb") if result.sql else "",
        "graph_warnings": [],
        **_graph(result),
    }
    if not generations:
        yield emit(2, "Sinh SQL", "Sinh SQL", "skipped", "Không cần gọi model: đã dừng ở cổng", step2)
    elif stopped_at == "model":
        yield emit(2, "Sinh SQL", f"Model ({model}) đề nghị dừng", result.status, result.message, step2)
    else:
        yield emit(2, "Sinh SQL", f"Model ({model}) viết SQL", "done", step2["summary"], step2)

    step3 = {
        "summary": "Chỉ đọc + chạy thử + kiểm chứng quy ước nghiệp vụ (AST)",
        "checklist": _checklist(result) or step1["gate_checks"],
        "findings": [
            {"code": v["convention_id"], "severity": "warning", "message": "; ".join(v["messages"])}
            for v in result.violations
        ],
        "advice": "",
        "referenced_tables": step2["referenced_tables"],
    }
    if not _blocks(result, "guard"):
        status3, detail3 = "skipped", "Không có SQL để kiểm chứng"
    elif stopped_at == "verifier":
        status3, detail3 = "abstain", result.message
    elif result.status == "error":
        status3, detail3 = "failed", result.message
    else:
        status3 = "warning" if result.violations or result.row_count == 0 else "done"
        detail3 = (
            f"Chỉ đọc · {len(result.conventions)} quy ước, {len(result.violations)} vi phạm"
            f" · {result.row_count} dòng"
            + (f" · đã sửa {result.repairs} lần" if result.repairs else "")
        )
    yield emit(3, "Kiểm chứng & chạy", "Kiểm chứng & chạy chỉ đọc", status3, detail3, step3)

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
        "thinking_gate": gate_thinking,
        "conventions": result.conventions,
        "violations": result.violations,
        "repairs": result.repairs,
        "assumptions": result.assumptions,
        "table_options": result.table_options,
        "interaction": interaction or {},
        "tables": result.tables,
        "turn_id": turn_id,
        "stepper": stepper,
    }

    if declined:
        label = (
            "Chọn nguồn dữ liệu"
            if result.table_options and not result.options
            else "Cần làm rõ câu hỏi"
            if result.status == "clarify"
            else "Từ chối trả lời"
        )
        outcome = "Hỏi lại" if result.status == "clarify" else "Từ chối"
        yield emit(4, "Kết cục", label, result.status, result.message, step4, outcome)
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
        yield emit(4, "Kết cục", "Lỗi thực thi", "failed", result.message, step4, "Lỗi")
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
    yield emit(4, "Kết cục", "Trả lời", "warning" if warn else "done", label, step4, "Trả lời")
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
