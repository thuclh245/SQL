"""API cho phần tương tác của verified-context: gợi ý bảng khi gõ @, phản hồi Đúng/Báo sai,
và hàng chờ để DE duyệt câu mẫu."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.config import FRONTEND_DIR
from backend.services.runtime_service import get_interaction_store, verified_pipeline
from t2s.verified_context.feedback import ReviewError

router = APIRouter(tags=["Verified context"])
VERIFIED_DATABASES = ("vtnet_mini",)


class FeedbackRequest(BaseModel):
    turn_id: str
    verdict: str = Field(..., description="correct | wrong")
    note: str = ""


class ReviewRequest(BaseModel):
    sql: str | None = Field(None, description="SQL đã sửa; bỏ trống để dùng SQL của lượt hỏi")
    note: str = ""
    reviewer: str = "DE"


@router.get("/api/verified/tables")
def list_tables(database_id: str = "vtnet_mini") -> list[dict[str, Any]]:
    """Bảng có dữ liệu thật, để gợi ý khi người dùng gõ @ trong ô hỏi."""
    if database_id not in VERIFIED_DATABASES:
        return []
    pipe = verified_pipeline()
    labels = pipe.assets.glossary.table_labels
    return [
        {
            "fqn": fqn,
            "name": fqn.split(".", 1)[1],
            "label": labels.get(fqn, ""),
            "domain": pipe.assets.catalogs["M1"][fqn].domain,
        }
        for fqn in sorted(pipe.linker.candidates)
    ]


@router.post("/api/verified/feedback")
def add_feedback(body: FeedbackRequest) -> dict[str, Any]:
    try:
        return get_interaction_store().add_feedback(body.turn_id, body.verdict, body.note)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/verified/review/items")
def review_items(status: str = "pending") -> dict[str, Any]:
    store = get_interaction_store()
    return {"items": store.review_items(status), "stats": store.stats()}


@router.post("/api/verified/review/{turn_id}/approve")
def approve(turn_id: str, body: ReviewRequest) -> dict[str, Any]:
    store = get_interaction_store()
    sql = body.sql
    if sql is not None:
        # SQL do DE sửa phải chạy được và chỉ đọc, giống SQL do model sinh.
        pipe = verified_pipeline()
        sql = pipe.normalise(sql.strip().rstrip(";"))
        if (blocked := pipe.guard(sql)) is not None:
            raise HTTPException(status_code=400, detail=blocked)
        _columns, _rows, error = pipe.execute(sql)
        if error:
            raise HTTPException(status_code=400, detail=f"SQL không chạy được: {error}")
    try:
        return store.approve(turn_id, sql=sql, note=body.note, reviewer=body.reviewer)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/verified/review/{turn_id}/reject")
def reject(turn_id: str, body: ReviewRequest) -> dict[str, Any]:
    try:
        return get_interaction_store().reject(turn_id, note=body.note, reviewer=body.reviewer)
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/verified/examples")
def examples() -> list[dict[str, Any]]:
    return get_interaction_store().approved_examples()


@router.get("/review")
def review_page() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "review.html"))
