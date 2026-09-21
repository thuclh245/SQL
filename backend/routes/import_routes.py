"""Database import API endpoints (SQL Script, SQLite file, CSV files)."""

from __future__ import annotations

import csv as csv_lib
import io
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.config import (
    DB_CATALOG,
    IMPORTED_DB_DIR,
    save_custom_manifest,
    save_imported_catalog,
)
from backend.services.runtime_service import _RUNTIMES

router = APIRouter(prefix="/api/database", tags=["Database Import"])


class ImportSqlScriptRequest(BaseModel):
    db_id: str = Field(..., description="Mã định danh CSDL (chữ thường, không dấu, không khoảng trắng)")
    title: str = Field(..., description="Tên hiển thị CSDL")
    description: str = Field("", description="Mô tả dữ liệu")
    icon: str = Field("📝", description="Icon emoji")
    sql_script: str = Field(..., description="Nội dung kịch bản SQL (DDL + DML)")


@router.post("/import/sqlite")
async def import_sqlite_file(
    file: UploadFile = File(...),
    db_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    icon: str = Form("🗄️"),
):
    clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", db_id.lower().strip())
    if not clean_id:
        raise HTTPException(status_code=400, detail="Mã CSDL (ID) không hợp lệ.")

    target_dir = IMPORTED_DB_DIR / clean_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{clean_id}.sqlite"

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Tệp tải lên rỗng.")

    with open(target_file, "wb") as f:
        f.write(content)

    try:
        from t2s.database.sqlite_introspector import introspect_sqlite_database, generate_suggested_prompts
        manifest = introspect_sqlite_database(target_file, clean_id)
        save_custom_manifest(manifest)
        prompts = generate_suggested_prompts(manifest)
    except Exception as exc:
        if target_file.exists():
            target_file.unlink()
        raise HTTPException(status_code=400, detail=f"Không thể đọc cấu trúc CSDL SQLite: {exc}")

    entry = {
        "id": clean_id,
        "title": title.strip() or clean_id,
        "icon": icon.strip() or "🗄️",
        "badge": "Đã nhập (SQLite)",
        "description": description.strip() or f"CSDL tùy chỉnh gồm {len(manifest['table_names_original'])} bảng.",
        "prompts": prompts,
        "is_imported": True,
        "table_count": len(manifest["table_names_original"]),
        "tables": manifest["table_names_original"],
    }

    DB_CATALOG[clean_id] = entry
    save_imported_catalog()

    for k in list(_RUNTIMES.keys()):
        if k.startswith(f"{clean_id}_"):
            del _RUNTIMES[k]

    return {"status": "success", "database": entry}


@router.post("/import/sql")
async def import_sql_script(req: ImportSqlScriptRequest):
    clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", req.db_id.lower().strip())
    if not clean_id:
        raise HTTPException(status_code=400, detail="Mã CSDL (ID) không hợp lệ.")
    if not req.sql_script.strip():
        raise HTTPException(status_code=400, detail="Kịch bản SQL không được để trống.")

    target_dir = IMPORTED_DB_DIR / clean_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{clean_id}.sqlite"
    if target_file.exists():
        target_file.unlink()

    conn = sqlite3.connect(str(target_file))
    try:
        conn.executescript(req.sql_script)
        conn.commit()
    except Exception as exc:
        conn.close()
        if target_file.exists():
            target_file.unlink()
        raise HTTPException(status_code=400, detail=f"Lỗi thực thi cú pháp SQL: {exc}")
    finally:
        conn.close()

    try:
        from t2s.database.sqlite_introspector import introspect_sqlite_database, generate_suggested_prompts
        manifest = introspect_sqlite_database(target_file, clean_id)
        save_custom_manifest(manifest)
        prompts = generate_suggested_prompts(manifest)
    except Exception as exc:
        if target_file.exists():
            target_file.unlink()
        raise HTTPException(status_code=400, detail=f"Không thể đọc cấu trúc CSDL sau khi tạo: {exc}")

    entry = {
        "id": clean_id,
        "title": req.title.strip() or clean_id,
        "icon": req.icon.strip() or "📝",
        "badge": "Đã nhập (SQL)",
        "description": req.description.strip() or f"Khởi tạo từ kịch bản SQL với {len(manifest['table_names_original'])} bảng.",
        "prompts": prompts,
        "is_imported": True,
        "table_count": len(manifest["table_names_original"]),
        "tables": manifest["table_names_original"],
    }

    DB_CATALOG[clean_id] = entry
    save_imported_catalog()

    for k in list(_RUNTIMES.keys()):
        if k.startswith(f"{clean_id}_"):
            del _RUNTIMES[k]

    return {"status": "success", "database": entry}


@router.post("/import/csv")
async def import_csv_files(
    files: list[UploadFile] = File(...),
    db_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    icon: str = Form("📊"),
):
    clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", db_id.lower().strip())
    if not clean_id:
        raise HTTPException(status_code=400, detail="Mã CSDL (ID) không hợp lệ.")
    if not files:
        raise HTTPException(status_code=400, detail="Chưa chọn tệp CSV nào.")

    target_dir = IMPORTED_DB_DIR / clean_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{clean_id}.sqlite"

    conn = sqlite3.connect(str(target_file))
    cur = conn.cursor()

    try:
        created_tables = []
        for f in files:
            raw_tname = Path(f.filename or "table").stem
            table_name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_tname.lower())
            if not table_name:
                table_name = f"table_{int(time.time())}"

            content_bytes = await f.read()
            text_stream = io.StringIO(content_bytes.decode("utf-8-sig", errors="replace"))
            reader = csv_lib.reader(text_stream)

            header = next(reader, None)
            if not header:
                continue

            clean_cols = [
                re.sub(r"[^a-zA-Z0-9_]", "_", h.strip()) or f"col_{i}"
                for i, h in enumerate(header)
            ]

            cols_def = ", ".join([f'"{c}" TEXT' for c in clean_cols])
            cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            cur.execute(f'CREATE TABLE "{table_name}" ({cols_def})')

            placeholders = ", ".join(["?"] * len(clean_cols))
            insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'
            batch = []
            for row in reader:
                row_vals = row[: len(clean_cols)] + [""] * max(0, len(clean_cols) - len(row))
                batch.append(row_vals)
                if len(batch) >= 1000:
                    cur.executemany(insert_sql, batch)
                    batch = []
            if batch:
                cur.executemany(insert_sql, batch)
            created_tables.append(table_name)

        conn.commit()
    except Exception as exc:
        conn.close()
        if target_file.exists():
            target_file.unlink()
        raise HTTPException(status_code=400, detail=f"Lỗi nhập dữ liệu CSV: {exc}")
    finally:
        conn.close()

    try:
        from t2s.database.sqlite_introspector import introspect_sqlite_database, generate_suggested_prompts
        manifest = introspect_sqlite_database(target_file, clean_id)
        save_custom_manifest(manifest)
        prompts = generate_suggested_prompts(manifest)
    except Exception as exc:
        if target_file.exists():
            target_file.unlink()
        raise HTTPException(status_code=400, detail=f"Không thể đọc cấu trúc CSDL sau khi nạp CSV: {exc}")

    entry = {
        "id": clean_id,
        "title": title.strip() or clean_id,
        "icon": icon.strip() or "📊",
        "badge": "Đã nhập (CSV)",
        "description": description.strip() or f"Tạo tự động từ {len(files)} tệp CSV với {len(manifest['table_names_original'])} bảng.",
        "prompts": prompts,
        "is_imported": True,
        "table_count": len(manifest["table_names_original"]),
        "tables": manifest["table_names_original"],
    }

    DB_CATALOG[clean_id] = entry
    save_imported_catalog()

    for k in list(_RUNTIMES.keys()):
        if k.startswith(f"{clean_id}_"):
            del _RUNTIMES[k]

    return {"status": "success", "database": entry}


@router.delete("/{db_id}")
async def delete_imported_database(db_id: str):
    if db_id not in DB_CATALOG:
        raise HTTPException(status_code=404, detail="Không tìm thấy CSDL.")
    if not DB_CATALOG[db_id].get("is_imported"):
        raise HTTPException(status_code=400, detail="Chỉ có thể xóa CSDL do người dùng tự nhập.")

    del DB_CATALOG[db_id]
    save_imported_catalog()

    target_dir = IMPORTED_DB_DIR / db_id
    if target_dir.exists():
        import shutil
        shutil.rmtree(target_dir, ignore_errors=True)

    for k in list(_RUNTIMES.keys()):
        if k.startswith(f"{db_id}_"):
            del _RUNTIMES[k]

    return {"status": "success", "message": f"Đã xóa CSDL {db_id}"}
