"""Configuration and catalog settings for Text-to-SQL backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data" / "bird_mini_dev"
SCHEMA_DB_DIR = DATA_DIR / "schema_only_databases"
TABLES_JSON = DATA_DIR / "mini_dev_tables.json"
PROMPT_DIR = BASE_DIR / "prompts" / "direct_sql"
OFFICIAL_DB_DIR = BASE_DIR / "benchmarks" / "t2s" / "databases" / "official"
SYNTHETIC_DB_DIR = BASE_DIR / "benchmarks" / "synthetic_solver_ceiling" / "databases"
SYNTHETIC_META_DIR = BASE_DIR / "benchmarks" / "synthetic_solver_ceiling" / "metadata"

# CSDL duy nhất chạy trên lakehouse: metadata sinh từ catalog của snapshot,
# dữ liệu nằm trên Trino chứ không phải file SQLite nào.
LAKEHOUSE_DB_ID = "telecom_lakehouse"
LAKEHOUSE_TABLES_JSON = BASE_DIR / "data" / "lakehouse" / "tables.json"

IMPORTED_DB_DIR = BASE_DIR / "data" / "imported_databases"
IMPORTED_CATALOG_FILE = IMPORTED_DB_DIR / "catalog_registry.json"
CUSTOM_TABLES_JSON = IMPORTED_DB_DIR / "custom_tables.json"

DB_CATALOG: dict[str, dict[str, Any]] = {
    "telecom_lakehouse": {
        "id": "telecom_lakehouse",
        "title": "Viễn thông Lakehouse (Trino)",
        "icon": "📡",
        "badge": "Lakehouse",
        "description": "32 bảng trên lakehouse: thuê bao, gói cước, hóa đơn, trạm và cell, KPI vô tuyến, QoS, truyền dẫn và xác thực FTTH. Truy vấn chạy trên Trino qua catalog hive.",
        "prompts": [
            "Có bao nhiêu thuê bao trong bảng khách hàng?",
            "Số thuê bao theo tên tỉnh là bao nhiêu?",
            "Trong ngày 2026-08-19, liệt kê 10 cell có tổng lưu lượng xuống cao nhất cùng tên tỉnh và trạm.",
        ],
    },
}

SUPPORTED_MODELS = [
    {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B", "provider": "OpenAI / OpenRouter"},
    {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "provider": "Meta"},
    {"id": "qwen/qwen-2.5-coder-32b-instruct", "name": "Qwen 2.5 Coder 32B", "provider": "Alibaba"},
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "provider": "DeepSeek"},
]

def resolve_evidence(question: str, db_id: str) -> list[str]:
    """Chưa có nguồn gợi ý ngữ nghĩa cho lakehouse.

    Các gợi ý cũ đều viết cứng cho những CSDL benchmark đã gỡ khỏi catalog.
    Nguồn thay thế là mô tả bảng/cột trong OpenMetadata, thuộc cổng G2.
    """
    return []


def save_custom_manifest(manifest: dict[str, Any]) -> None:
    IMPORTED_DB_DIR.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    if CUSTOM_TABLES_JSON.exists():
        try:
            with open(CUSTOM_TABLES_JSON, "r", encoding="utf-8") as f:
                manifests = json.load(f)
        except Exception:
            manifests = []
    manifests = [m for m in manifests if m.get("db_id") != manifest.get("db_id")]
    manifests.append(manifest)
    with open(CUSTOM_TABLES_JSON, "w", encoding="utf-8") as f:
        json.dump(manifests, f, ensure_ascii=False, indent=2)


def save_imported_catalog() -> None:
    IMPORTED_DB_DIR.mkdir(parents=True, exist_ok=True)
    imported_entries = {k: v for k, v in DB_CATALOG.items() if v.get("is_imported", False)}
    with open(IMPORTED_CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(imported_entries, f, ensure_ascii=False, indent=2)


def load_imported_catalog() -> None:
    if IMPORTED_CATALOG_FILE.exists():
        try:
            with open(IMPORTED_CATALOG_FILE, "r", encoding="utf-8") as f:
                imported_entries = json.load(f)
                DB_CATALOG.update(imported_entries)
        except Exception:
            pass
