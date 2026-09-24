"""SQLite Schema Introspector.

Tự động trích xuất toàn bộ cấu trúc CSDL SQLite (bảng, cột, kiểu dữ liệu, khóa chính,
khóa ngoại) và chuyển đổi thành định dạng Schema Manifest tiêu chuẩn để Text-to-SQL
runtime có thể nhận diện và truy vấn ngay lập tức mà không cần cấu hình thủ công.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def introspect_sqlite_database(db_path: Path | str, db_id: str) -> dict[str, Any]:
    """Trích xuất cấu trúc của một CSDL SQLite thành định dạng Manifest chuẩn."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp SQLite tại: {path}")

    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    try:
        # 1. Lấy danh sách bảng người dùng (loại trừ các bảng hệ thống của SQLite)
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        )
        tables = [str(row[0]) for row in cursor.fetchall()]

        column_names_original: list[list[Any]] = [[-1, "*"]]
        column_names: list[list[Any]] = [[-1, "*"]]
        column_types: list[str] = ["text"]
        primary_keys: list[int] = []

        # Ánh xạ (table_name, col_name) -> column_index
        col_idx_map: dict[tuple[str, str], int] = {}

        for t_idx, table_name in enumerate(tables):
            cursor.execute(f'PRAGMA table_info("{table_name}");')
            # Cột trả về: cid, name, type, notnull, dflt_value, pk
            for row in cursor.fetchall():
                col_name = str(row[1])
                raw_type = str(row[2]).lower() if row[2] else "text"
                is_pk = bool(row[5] > 0)

                col_idx = len(column_names_original)
                column_names_original.append([t_idx, col_name])

                # Tạo tên ngữ nghĩa dễ hiểu
                semantic_col_name = col_name.replace("_", " ")
                column_names.append([t_idx, semantic_col_name])

                # Chuẩn hóa kiểu dữ liệu
                if any(k in raw_type for k in ["int", "real", "floa", "doub", "num", "dec"]):
                    column_types.append("number")
                elif any(k in raw_type for k in ["time", "date"]):
                    column_types.append("time")
                elif any(k in raw_type for k in ["bool"]):
                    column_types.append("boolean")
                else:
                    column_types.append("text")

                if is_pk:
                    primary_keys.append(col_idx)

                col_idx_map[(table_name.lower(), col_name.lower())] = col_idx

        # 2. Lấy danh sách khóa ngoại
        foreign_keys: list[list[int]] = []
        for table_name in tables:
            cursor.execute(f'PRAGMA foreign_key_list("{table_name}");')
            # Cột trả về: id, seq, table, from, to, on_update, on_delete, match
            for row in cursor.fetchall():
                target_table = str(row[2]).lower()
                from_col = str(row[3]).lower()
                to_col = str(row[4]).lower() if row[4] else ""

                from_key = (table_name.lower(), from_col)
                to_key = (target_table, to_col)

                if from_key in col_idx_map and to_key in col_idx_map:
                    foreign_keys.append([col_idx_map[from_key], col_idx_map[to_key]])

        # Tên bảng ngữ nghĩa
        semantic_table_names = [t.replace("_", " ") for t in tables]

        return {
            "db_id": db_id,
            "table_names_original": tables,
            "table_names": semantic_table_names,
            "column_names_original": column_names_original,
            "column_names": column_names,
            "column_types": column_types,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
        }
    finally:
        conn.close()


def generate_suggested_prompts(manifest: dict[str, Any]) -> list[str]:
    """Tự động sinh các câu hỏi gợi ý phù hợp với các bảng và cột trong CSDL."""
    tables = manifest.get("table_names_original", [])
    if not tables:
        return ["Hiển thị toàn bộ dữ liệu trong cơ sở dữ liệu?"]

    prompts = []
    # Gợi ý 1: Đếm số lượng dòng trong bảng đầu tiên
    first_table = tables[0]
    prompts.append(f"Có bao nhiêu bản ghi trong bảng '{first_table}'?")

    # Gợi ý 2: Liệt kê top 5 bản ghi
    prompts.append(f"Hiển thị thông tin 5 dòng đầu tiên từ bảng '{first_table}'?")

    # Gợi ý 3: Nếu có từ 2 bảng trở lên, gợi ý truy vấn kết nối hoặc bảng thứ 2
    if len(tables) > 1:
        second_table = tables[1]
        prompts.append(f"Tổng số lượng dữ liệu trong bảng '{second_table}' là bao nhiêu?")
    else:
        # Tìm cột dạng số để tính tổng hoặc trung bình nếu có
        cols = manifest.get("column_names_original", [])
        types = manifest.get("column_types", [])
        number_cols = [
            cols[i][1]
            for i, t in enumerate(types)
            if t == "number" and i < len(cols) and cols[i][0] != -1
        ]
        if number_cols:
            col_name = number_cols[0]
            prompts.append(f"Giá trị lớn nhất và trung bình của cột '{col_name}' là bao nhiêu?")
        else:
            prompts.append(f"Danh sách các giá trị khác nhau trong bảng '{first_table}'?")

    return prompts[:3]
