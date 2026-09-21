"""API routes for configuration, databases catalog, and schemas."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import DB_CATALOG, SUPPORTED_MODELS
from backend.services.schema_service import get_db_schema_details

router = APIRouter(prefix="/api", tags=["Config & Schema"])


@router.get("/config")
def get_config() -> dict:
    """Trả về danh sách databases và models hỗ trợ cho frontend."""
    return {
        "databases": list(DB_CATALOG.values()),
        "models": SUPPORTED_MODELS,
    }


@router.get("/schema/{db_id}")
def get_schema(db_id: str) -> dict:
    """Trả về schema chi tiết của một database (bảng, cột, khóa)."""
    if db_id not in DB_CATALOG:
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' không tồn tại.")
    return get_db_schema_details(db_id)
