"""Main FastAPI Application for Text-to-SQL Copilot."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import FRONTEND_DIR, load_imported_catalog
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
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        raise RuntimeError(f"Không tìm thấy {index}")
    return FileResponse(str(index))


if __name__ == "__main__":
    import uvicorn
    print("\n⚡ T2S Copilot Web Server is running at: http://localhost:8080\n")
    uvicorn.run(app, host="0.0.0.0", port=8080)
