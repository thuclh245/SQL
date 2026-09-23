"""Database schema introspection and metadata service."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.config import (
    DB_CATALOG,
    LAKEHOUSE_DB_ID,
    LAKEHOUSE_TABLES_JSON,
    TABLES_JSON,
    CUSTOM_TABLES_JSON,
    IMPORTED_DB_DIR,
    OFFICIAL_DB_DIR,
    SCHEMA_DB_DIR,
    SYNTHETIC_DB_DIR,
)


def get_db_schema_details(db_id: str) -> dict[str, Any]:
    """Lấy danh sách bảng, cột, khóa chính và khóa ngoại của CSDL."""
    forced_json = None
    db_file = None

    if db_id == LAKEHOUSE_DB_ID:
        # Lakehouse không có file SQLite nào để nội soi; mô tả bảng lấy từ
        # metadata đã sinh, nếu không panel schema sẽ hiện nhầm fixture cũ.
        forced_json = LAKEHOUSE_TABLES_JSON
    else:
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

    if db_file and db_file.exists():
        try:
            conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]

            columns_map: dict[str, list[str]] = {}
            pks_map: dict[str, list[str]] = {}
            fks_list: list[dict[str, Any]] = []

            for tbl in tables:
                cursor.execute(f'PRAGMA table_info("{tbl}");')
                cols_info = cursor.fetchall()
                columns_map[tbl] = [c[1] for c in cols_info]
                pks = [c[1] for c in cols_info if c[5] > 0]
                if pks:
                    pks_map[tbl] = pks

                cursor.execute(f'PRAGMA foreign_key_list("{tbl}");')
                for fk in cursor.fetchall():
                    fks_list.append({
                        "from_table": tbl,
                        "from_col": fk[3],
                        "to_table": fk[2],
                        "to_col": fk[4],
                        "cardinality": "N:1",
                    })

            conn.close()
            return {
                "db_id": db_id,
                "tables": tables,
                "columns": columns_map,
                "primary_keys": pks_map,
                "foreign_keys": fks_list,
            }
        except Exception:
            pass

    # Fallback to tables.json if available
    active_json = forced_json or TABLES_JSON
    if forced_json is None and CUSTOM_TABLES_JSON.exists():
        try:
            with open(CUSTOM_TABLES_JSON, "r", encoding="utf-8") as f:
                mans = json.load(f)
                if any(m.get("db_id") == db_id for m in mans):
                    active_json = CUSTOM_TABLES_JSON
        except Exception:
            pass

    if active_json.exists():
        try:
            with open(active_json, "r", encoding="utf-8") as f:
                schemas = json.load(f)
                for s in schemas:
                    if s.get("db_id") == db_id:
                        tbls = s.get("table_names_original", [])
                        cols_raw = s.get("column_names_original", [])
                        col_map: dict[str, list[str]] = {t: [] for t in tbls}
                        for t_idx, c_name in cols_raw:
                            if 0 <= t_idx < len(tbls):
                                col_map[tbls[t_idx]].append(c_name)

                        fks = []
                        for from_idx, to_idx in s.get("foreign_keys", []):
                            if 0 <= from_idx < len(cols_raw) and 0 <= to_idx < len(cols_raw):
                                f_tbl_idx, f_col = cols_raw[from_idx]
                                t_tbl_idx, t_col = cols_raw[to_idx]
                                if 0 <= f_tbl_idx < len(tbls) and 0 <= t_tbl_idx < len(tbls):
                                    fks.append({
                                        "from_table": tbls[f_tbl_idx],
                                        "from_col": f_col,
                                        "to_table": tbls[t_tbl_idx],
                                        "to_col": t_col,
                                        "cardinality": "N:1",
                                    })

                        return {
                            "db_id": db_id,
                            "tables": tbls,
                            "columns": col_map,
                            "foreign_keys": fks,
                        }
        except Exception:
            pass

    return {"db_id": db_id, "tables": [], "columns": {}, "foreign_keys": []}
