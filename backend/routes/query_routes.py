"""API routes for SSE streaming text-to-SQL query pipeline."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.config import DB_CATALOG, IMPORTED_DB_DIR, load_imported_catalog, resolve_evidence
from backend.routes.verified_stream import verified_events
from backend.services.guardrail_service import validate_query_safety
from backend.services.runtime_service import (
    VerifiedDuckDBRuntime,
    get_or_create_runtime,
    run_query_pipeline,
)
from backend.services.schema_service import get_db_schema_details
from t2s.grounding.steiner_join_graph import GraphJoinEdge, SteinerJoinGraph

router = APIRouter(prefix="/api/query", tags=["Query Pipeline"])


class StreamQueryRequest(BaseModel):
    question: str = Field(..., description="Câu hỏi bằng tiếng Việt hoặc tiếng Anh")
    database_id: str = Field("telecom_lakehouse", description="ID của cơ sở dữ liệu đang chọn")
    model_name: str | None = Field(None, description="Mô hình LLM được chọn")


@router.post("/stream")
async def stream_query_pipeline(body: StreamQueryRequest):
    question = body.question.strip()
    db_id = body.database_id
    model_id = body.model_name
    if db_id not in DB_CATALOG:
        load_imported_catalog()
    if db_id not in DB_CATALOG:
        imported_sqlite = IMPORTED_DB_DIR / db_id / f"{db_id}.sqlite"
        if imported_sqlite.exists():
            DB_CATALOG[db_id] = {
                "id": db_id,
                "title": db_id.replace("_", " ").title(),
                "icon": "🗄️",
                "badge": "Imported",
                "description": f"CSDL {db_id} đã nhập",
                "prompts": [],
            }
        else:
            raise HTTPException(
                status_code=400, detail=f"Database '{db_id}' không tồn tại hoặc chưa được khởi tạo."
            )

    async def event_generator() -> AsyncGenerator[str, None]:
        def sse(event_type: str, data: dict[str, Any]) -> str:
            payload = json.dumps(data, ensure_ascii=False)
            return f"event: {event_type}\ndata: {payload}\n\n"

        overall_start = time.perf_counter()

        try:
            # --- BƯỚC 1: Dò tìm Schema & Dữ liệu ---
            schema_info = get_db_schema_details(db_id)
            total_db_tables = schema_info.get("tables", [])
            runtime, active_model = get_or_create_runtime(db_id, model_id)
            if isinstance(runtime, VerifiedDuckDBRuntime):
                async for event in verified_events(runtime, question, db_id):
                    yield event
                return
            evidence_list = resolve_evidence(question, db_id)

            step1_thinking = {
                "summary": f"Đã định vị schema cho CSDL '{db_id}' với {len(total_db_tables)} bảng.",
                "available_tables": total_db_tables,
                "catalog_foreign_keys": schema_info.get("foreign_keys", []),
                "evidence_applied": evidence_list,
                "sample_columns": {
                    t: schema_info.get("columns", {}).get(t, [])[:5] for t in total_db_tables[:4]
                },
            }

            yield sse(
                "step",
                {
                    "step": 1,
                    "name": "Dò tìm dữ liệu",
                    "title": "Bước 1: Phân tích Schema & Dò tìm thực thể",
                    "status": "running",
                    "detail": f"Đang quét {len(total_db_tables)} bảng trong '{db_id}'...",
                    "thinking": step1_thinking,
                },
            )
            await asyncio.sleep(0.15)

            ev_info = (
                f"Áp dụng quy ước: {evidence_list[0]}"
                if evidence_list
                else f"Nhận diện ngữ cảnh từ {len(total_db_tables)} bảng trong CSDL"
            )
            yield sse(
                "step",
                {
                    "step": 1,
                    "name": "Dò tìm dữ liệu",
                    "title": "Bước 1: Phân tích Schema & Dò tìm thực thể",
                    "status": "done",
                    "detail": ev_info,
                    "thinking": step1_thinking,
                },
            )

            # --- BƯỚC 2: Sinh câu lệnh SQL & Suy luận Đồ thị JOIN ---
            await asyncio.sleep(0.15)
            yield sse(
                "step",
                {
                    "step": 2,
                    "name": "Sinh SQL & Đồ thị",
                    "title": f"Bước 2: AI ({active_model}) sinh SQL & đồ thị JOIN",
                    "status": "running",
                    "detail": "Đang tính toán đường đi Steiner Join Graph và suy luận câu lệnh...",
                    "thinking": step1_thinking,
                },
            )

            # Chặn một provider chậm/không phản hồi giữ kết nối SSE vô thời hạn.
            pipe_res = await asyncio.wait_for(
                run_query_pipeline(runtime, question, evidence_list),
                timeout=50.0,
            )
            candidate_sql = pipe_res["candidate_sql"]
            ast_tables = pipe_res["ast_tables"]
            is_exec_failed = pipe_res["is_execution_failed"]
            raw_exec_error = pipe_res["error_message"]

            # Suy luận đồ thị JOIN (Steiner Join Graph) giữa các bảng được truy vấn
            fks = schema_info.get("foreign_keys", [])
            graph_edges = [
                GraphJoinEdge(
                    left_table=fk["from_table"],
                    right_table=fk["to_table"],
                    left_cols=(fk["from_col"],),
                    right_cols=(fk["to_col"],),
                    source="fk",
                    cardinality=fk.get("cardinality", "N:1"),
                )
                for fk in fks
            ]
            join_graph = SteinerJoinGraph(graph_edges)
            join_plan = join_graph.plan(ast_tables if ast_tables else total_db_tables[:2])

            graph_visual_nodes = []
            for e in join_plan.edges:
                graph_visual_nodes.append(
                    {
                        "left": e.left_table,
                        "right": e.right_table,
                        "left_cols": list(e.left_cols),
                        "right_cols": list(e.right_cols),
                        "cardinality": e.cardinality,
                        "on_clause": e.on_clause(),
                    }
                )

            # Chuẩn bị danh sách nodes cho Whiteboard Canvas
            cols_map = schema_info.get("columns", {})
            fks_list = schema_info.get("foreign_keys", [])
            involved_tables = list(
                dict.fromkeys(
                    ast_tables
                    + [e.left_table for e in join_plan.edges]
                    + [e.right_table for e in join_plan.edges]
                    + join_plan.bridge_tables
                )
            )
            if not involved_tables and total_db_tables:
                involved_tables = total_db_tables[:2]

            graph_nodes = []
            for tbl in involved_tables:
                tbl_fks = [fk["from_col"] for fk in fks_list if fk.get("from_table") == tbl]
                tbl_pks = [fk["to_col"] for fk in fks_list if fk.get("to_table") == tbl]
                all_cols = cols_map.get(tbl, [])
                key_cols = list(dict.fromkeys(tbl_fks + tbl_pks))
                if not key_cols and all_cols:
                    key_cols = all_cols[:3]

                is_bridge = tbl in join_plan.bridge_tables
                role = "bridge" if is_bridge else ("primary" if tbl in ast_tables else "dimension")

                graph_nodes.append(
                    {
                        "id": tbl,
                        "label": tbl,
                        "role": role,
                        "is_bridge": is_bridge,
                        "key_columns": key_cols[:4],
                        "total_columns": len(all_cols),
                        "all_columns": all_cols[:6],
                    }
                )

            step2_thinking = {
                "summary": (
                    f"Đã suy luận đường nối bảng qua Steiner Join Graph "
                    f"({len(ast_tables)} bảng tham chiếu)."
                ),
                "referenced_tables": ast_tables,
                "candidate_sql": candidate_sql,
                "steiner_edges": graph_visual_nodes,
                "graph_nodes": graph_nodes,
                "bridge_tables": join_plan.bridge_tables,
                "graph_connected": join_plan.connected,
                "graph_warnings": join_plan.warnings,
            }

            if not candidate_sql:
                step2_status = "failed"
                step2_detail = "Không thể sinh câu lệnh SQL khả dụng"
            elif is_exec_failed:
                step2_status = "warning"
                clean_err_part = (
                    raw_exec_error.split("|")[0]
                    .replace("SQLite query execution failed:", "")
                    .strip()
                    if raw_exec_error
                    else "Lỗi schema"
                )
                step2_detail = (
                    f"Đã tạo câu lệnh ({len(ast_tables)} bảng) • Cảnh báo schema: {clean_err_part}"
                )
            else:
                step2_status = "done"
                tb_summary = ", ".join(ast_tables) if ast_tables else "đơn"
                step2_detail = f"Đã tạo câu lệnh ({len(ast_tables)} bảng: {tb_summary})"

            yield sse(
                "step",
                {
                    "step": 2,
                    "name": "Sinh SQL & Đồ thị",
                    "title": f"Bước 2: AI ({active_model}) sinh SQL & Suy luận Đồ thị",
                    "status": step2_status,
                    "detail": step2_detail,
                    "thinking": step2_thinking,
                },
            )

            # --- BƯỚC 3: Kiểm tra an toàn AST & Chính sách theo Domain ---
            await asyncio.sleep(0.15)
            db_tag = "Lakehouse" if db_id == "telecom_lakehouse" else "Chuẩn CSDL"
            yield sse(
                "step",
                {
                    "step": 3,
                    "name": "Kiểm tra an toàn",
                    "title": f"Bước 3: Kiểm tra an toàn AST ({db_tag})",
                    "status": "running",
                    "detail": "Kiểm tra quyền chỉ đọc (Read-Only) và an toàn cú pháp...",
                },
            )
            await asyncio.sleep(0.2)

            guard_result = validate_query_safety(db_id, candidate_sql, schema_info)
            is_blocked = guard_result["is_blocked"]
            policy_findings = guard_result["findings"]
            checklist = guard_result["checklist"]
            advice = guard_result["advice"]

            step3_thinking = {
                "summary": "Kết quả kiểm định an toàn AST.",
                "checklist": checklist,
                "findings": policy_findings,
                "advice": advice,
                "referenced_tables": ast_tables,
            }

            if is_blocked:
                blocked_msgs = [f["message"] for f in policy_findings if f["severity"] == "block"]
                status_label = "Từ chối thực thi (Chặn rủi ro)"
                status_badge = "danger"

                yield sse(
                    "step",
                    {
                        "step": 3,
                        "name": "Kiểm tra an toàn",
                        "title": "Bước 3: Phát hiện vi phạm an toàn - ĐÃ CHẶN",
                        "status": "failed",
                        "detail": f"CHẶN: {'; '.join(blocked_msgs)}",
                        "thinking": step3_thinking,
                    },
                )
                await asyncio.sleep(0.1)

                step4_thinking = {
                    "summary": "Dừng thực thi để bảo đảm an toàn dữ liệu.",
                    "reason": blocked_msgs,
                    "advice": advice,
                }

                yield sse(
                    "step",
                    {
                        "step": 4,
                        "name": "Kết quả",
                        "title": "Bước 4: Từ chối thực thi câu lệnh",
                        "status": "blocked",
                        "detail": (
                            "Đã dừng thực thi để bảo vệ database "
                            "(ngăn ngừa thao tác can thiệp dữ liệu)"
                        ),
                        "thinking": step4_thinking,
                    },
                )

                total_elapsed = round(time.perf_counter() - overall_start, 2)

                yield sse(
                    "result",
                    {
                        "status": "blocked",
                        "is_blocked": True,
                        "status_label": status_label,
                        "sql": candidate_sql,
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "model_used": active_model,
                        "execution_time_ms": 1,
                        "total_latency_seconds": total_elapsed,
                        "ast_tables": ast_tables,
                        "error_message": blocked_msgs[0]
                        if blocked_msgs
                        else "Bị chặn bởi AST Policy Guard",
                        "guardrails_status": "danger",
                        "findings": blocked_msgs,
                        "advice": advice,
                        "thinking_step1": step1_thinking,
                        "thinking_graph": step2_thinking,
                        "thinking_ast": step3_thinking,
                        "thinking_exec": step4_thinking,
                        "sqlgrade": {
                            "grade": "F",
                            "label": status_label,
                            "badge": status_badge,
                            "findings": blocked_msgs,
                            "guardrails_status": "danger",
                        },
                    },
                )
                return

            # Cú pháp và an toàn AST hợp lệ
            yield sse(
                "step",
                {
                    "step": 3,
                    "name": "Kiểm tra an toàn",
                    "title": "Bước 3: Kiểm tra an toàn AST - HỢP LỆ",
                    "status": "done",
                    "detail": "Cú pháp an toàn, 100% Read-Only, không phát sinh lệnh nguy hại",
                    "thinking": step3_thinking,
                },
            )

            # --- BƯỚC 4: Thực thi CSDL và Chuẩn bị Kết quả ---
            await asyncio.sleep(0.15)
            yield sse(
                "step",
                {
                    "step": 4,
                    "name": "Kết quả",
                    "title": "Bước 4: Thực thi CSDL & Thống kê Tài nguyên",
                    "status": "running",
                    "detail": "Đang kiểm tra kết quả trả về từ cơ sở dữ liệu...",
                },
            )

            if is_exec_failed:
                clean_err = (
                    raw_exec_error.split("|")[0].strip()
                    if raw_exec_error
                    else "Lỗi thực thi SQLite"
                )
                total_elapsed = round(time.perf_counter() - overall_start, 2)

                step4_thinking = {
                    "summary": "Không thể thực thi câu lệnh do lỗi cơ sở dữ liệu.",
                    "error": clean_err,
                    "full_error": raw_exec_error,
                    "rows_returned": 0,
                    "execution_latency_ms": 0,
                    "total_elapsed_seconds": total_elapsed,
                }

                yield sse(
                    "step",
                    {
                        "step": 4,
                        "name": "Kết quả",
                        "title": "Bước 4: Cơ sở dữ liệu báo lỗi thực thi",
                        "status": "failed",
                        "detail": f"Lỗi SQLite: {clean_err}",
                        "thinking": step4_thinking,
                    },
                )

                yield sse(
                    "result",
                    {
                        "status": "execution_failed",
                        "is_blocked": False,
                        "is_execution_failed": True,
                        "status_label": "Lỗi thực thi CSDL (Không tìm thấy cột/bảng)",
                        "sql": candidate_sql,
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "model_used": active_model,
                        "execution_time_ms": 1,
                        "total_latency_seconds": total_elapsed,
                        "ast_tables": ast_tables,
                        "error_message": clean_err,
                        "guardrails_status": "warning",
                        "findings": [clean_err],
                        "advice": (
                            "Mô hình đã sinh câu lệnh có tên cột/bảng không tồn tại "
                            "trong CSDL thực tế. Bạn có thể thử lại."
                        ),
                        "thinking_step1": step1_thinking,
                        "thinking_graph": step2_thinking,
                        "thinking_ast": step3_thinking,
                        "thinking_exec": step4_thinking,
                        "sqlgrade": {
                            "grade": "C",
                            "label": "Lỗi cấu trúc CSDL",
                            "badge": "warning",
                            "findings": [clean_err],
                            "guardrails_status": "warning",
                        },
                    },
                )
                return

            # Thực thi thành công
            cols_data = pipe_res["columns"]
            rows_data = pipe_res["rows"]
            exec_time = pipe_res["execution_time_ms"]
            total_elapsed = round(time.perf_counter() - overall_start, 2)

            step4_thinking = {
                "summary": f"Thực thi thành công, trả về {len(rows_data)} bản ghi.",
                "rows_returned": len(rows_data),
                "execution_latency_ms": exec_time,
                "total_elapsed_seconds": total_elapsed,
            }

            yield sse(
                "step",
                {
                    "step": 4,
                    "name": "Kết quả",
                    "title": "Bước 4: Thực thi CSDL & Chuẩn bị Dữ liệu",
                    "status": "done",
                    "detail": f"Hoàn tất trong {total_elapsed}s ({len(rows_data)} bản ghi)",
                    "thinking": step4_thinking,
                },
            )

            yield sse(
                "result",
                {
                    "status": "completed",
                    "is_blocked": False,
                    "is_execution_failed": False,
                    "status_label": "Thực thi an toàn (Chỉ đọc)",
                    "sql": candidate_sql,
                    "columns": cols_data,
                    "rows": rows_data,
                    "row_count": len(rows_data),
                    "model_used": active_model,
                    "execution_time_ms": exec_time,
                    "total_latency_seconds": total_elapsed,
                    "ast_tables": ast_tables,
                    "error_message": None,
                    "guardrails_status": "passed",
                    "findings": [],
                    "thinking_step1": step1_thinking,
                    "thinking_graph": step2_thinking,
                    "thinking_ast": step3_thinking,
                    "thinking_exec": step4_thinking,
                    "sqlgrade": {
                        "grade": "A",
                        "label": "Thực thi an toàn (Chỉ đọc)",
                        "badge": "success",
                        "findings": [],
                        "guardrails_status": "passed",
                    },
                },
            )

        except TimeoutError:
            total_elapsed = round(time.perf_counter() - overall_start, 2)
            yield sse(
                "error",
                {
                    "status": "error",
                    "error_message": "Mô hình không phản hồi trong 50 giây. Vui lòng thử lại.",
                    "total_latency_seconds": total_elapsed,
                },
            )
        except Exception as exc:
            import traceback

            print(
                f"\n[ERROR in query_routes] Question: {question[:80]!r} | "
                f"DB: {db_id!r} | Model: {model_id!r}"
            )
            traceback.print_exc()
            total_elapsed = round(time.perf_counter() - overall_start, 2)
            yield sse(
                "error",
                {
                    "status": "error",
                    "error_message": str(exc),
                    "total_latency_seconds": total_elapsed,
                },
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")
