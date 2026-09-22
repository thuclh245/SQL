"""Runtime orchestration and execution service."""

from __future__ import annotations

import os
import re
import json
import time
from pathlib import Path
from typing import Any

from t2s.benchmark.runtime_factory import build_bird_runtime_for_database
from t2s.configuration.settings import Settings
from t2s.contracts import QueryRequest
from t2s.grounding import GroundingBudget
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.runtime.runtime_profile import SemanticRuntimeProfile
from t2s.security import UserIdentity

from backend.config import (
    IMPORTED_DB_DIR,
    OFFICIAL_DB_DIR,
    SCHEMA_DB_DIR,
    SYNTHETIC_DB_DIR,
    TABLES_JSON,
    CUSTOM_TABLES_JSON,
    PROMPT_DIR,
)

_RUNTIMES: dict[str, Any] = {}


def get_or_create_runtime(db_id: str, model_name: str | None = None) -> tuple[Any, str]:
    """Khởi tạo hoặc lấy runtime semantic cache cho database và model chỉ định."""
    settings = Settings()
    effective_model = (
        model_name
        or os.getenv("LLM_MODEL_NAME")
        or settings.llm_model_name
        or "openai/gpt-oss-120b"
    )

    cache_key = f"{db_id}_{effective_model}"
    if cache_key in _RUNTIMES:
        return _RUNTIMES[cache_key]

    imported_db = IMPORTED_DB_DIR / db_id / f"{db_id}.sqlite"
    official_db = OFFICIAL_DB_DIR / db_id / f"{db_id}.sqlite"
    schema_db = SCHEMA_DB_DIR / db_id / f"{db_id}.sqlite"
    synthetic_db = SYNTHETIC_DB_DIR / f"{db_id}.sqlite"

    if imported_db.exists():
        db_file = imported_db
    elif official_db.exists():
        db_file = official_db
    elif synthetic_db.exists():
        db_file = synthetic_db
    elif schema_db.exists():
        db_file = schema_db
    else:
        raise FileNotFoundError(f"Database SQLite không tồn tại: {db_id}")

    active_tables_json = TABLES_JSON
    candidates = [
        CUSTOM_TABLES_JSON,
        Path("/home/thuclh245/MyCode/SQL/data/imported_databases/custom_tables.json"),
        Path("/home/thuclh245/.gemini/antigravity/worktrees/SQL/streamlit_chat_interface/data/imported_databases/custom_tables.json"),
    ]
    for c_path in candidates:
        if c_path.exists():
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    custom_mans = json.load(f)
                    if any(m.get("db_id") == db_id for m in custom_mans):
                        active_tables_json = c_path
                        break
            except Exception:
                pass

    provider_url = os.getenv("VLLM_BASE_URL") or settings.vllm_base_url or "https://openrouter.ai/api/v1"
    api_key = os.getenv("LLM_API_KEY") or settings.llm_api_key or ""

    client = OpenAICompatibleChatClient(
        base_url=provider_url,
        api_key=api_key,
        # Tránh để giao diện chờ vô hạn khi provider không hỗ trợ model/schema đã chọn.
        request_timeout_seconds=45.0,
    )

    profile = SemanticRuntimeProfile(
        model_name=effective_model,
        prompt_version="v001",
        grounding_budget=GroundingBudget(
            small_db_threshold=15,
            max_hydrated_tables=12,
        ),
        release_candidates_with_caveats=True,
    )

    runtime = build_bird_runtime_for_database(
        db_id=db_id,
        db_path=db_file,
        tables_json_path=active_tables_json,
        chat_client=client,
        model_name=effective_model,
        prompt_directory=PROMPT_DIR,
        prompt_version="v001",
        runtime_profile=profile,
    )
    _RUNTIMES[cache_key] = (runtime, effective_model)
    return runtime, effective_model


async def run_query_pipeline(
    runtime: Any,
    question: str,
    evidence: list[str],
) -> dict[str, Any]:
    """Thực thi pipeline truy vấn an toàn và khôi phục câu lệnh dự tuyển nếu có lỗi thực thi."""
    req = QueryRequest(question=question, evidence=evidence)
    user_id = UserIdentity(
        user_id="user_analyst",
        roles=["analyst", "viewer"],
        attributes={"clearance": "standard"},
    )

    result = await runtime.execute_query_pipeline(
        query_request=req,
        user_identity=user_id,
        run_id=f"run_{int(time.time())}",
    )

    candidate_sql = result.sql or ""
    is_exec_failed = False
    exec_error_msg = result.error_message

    # Nếu result.sql bị rỗng nhưng có lỗi SQLite, bóc tách câu lệnh SQL dự tuyển đã sinh
    if not candidate_sql and exec_error_msg and "| SQL: " in exec_error_msg:
        parts = exec_error_msg.split("| SQL: ", 1)
        if len(parts) == 2:
            candidate_sql = parts[1].strip()
            is_exec_failed = True

    ast_tables = result.trace.ast_referenced_tables if result.trace else []

    # Nếu chưa có ast_tables nhưng có candidate_sql, thử bóc tách từ SQL
    if not ast_tables and candidate_sql:
        try:
            import sqlglot
            from sqlglot import exp
            tree = sqlglot.parse_one(candidate_sql, dialect="sqlite")
            for t in tree.find_all(exp.Table):
                if t.name and t.name not in ast_tables:
                    ast_tables.append(t.name)
        except Exception:
            pass

    return {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "candidate_sql": candidate_sql,
        "ast_tables": ast_tables,
        "columns": result.columns or [],
        "rows": result.rows or [],
        "row_count": result.row_count or (len(result.rows) if result.rows else 0),
        "execution_time_ms": result.execution_time_ms or 1,
        "error_message": exec_error_msg,
        "is_execution_failed": is_exec_failed,
    }
