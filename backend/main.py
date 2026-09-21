"""Main FastAPI Application for Text-to-SQL Copilot."""

from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import FRONTEND_DIR, WEB_DIR, load_imported_catalog
from backend.routes.config_routes import router as config_router
from backend.routes.import_routes import router as import_router
from backend.routes.query_routes import router as query_router

app = FastAPI(title="T2S Copilot - Modern Text-to-SQL")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Nạp CSDL đã nhập lúc khởi động
load_imported_catalog()

# Đăng ký các Router API
app.include_router(config_router)
app.include_router(import_router)
app.include_router(query_router)

# Phục vụ Frontend
static_path = FRONTEND_DIR if FRONTEND_DIR.exists() else WEB_DIR
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    candidates = [
        FRONTEND_DIR / "index.html",
        WEB_DIR / "index.html",
        Path("/home/thuclh245/MyCode/SQL/frontend/index.html"),
        Path("/home/thuclh245/.gemini/antigravity/worktrees/SQL/streamlit_chat_interface/frontend/index.html"),
    ]
    for c in candidates:
        if c.exists():
            return FileResponse(str(c))
    raise RuntimeError("Không tìm thấy file frontend/index.html")


if __name__ == "__main__":
    import uvicorn
    print("\n⚡ T2S Copilot Web Server is running at: http://localhost:8080\n")
    uvicorn.run(app, host="0.0.0.0", port=8080)
