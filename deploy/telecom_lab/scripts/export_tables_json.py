"""Sinh tables.json (định dạng BIRD) mô tả các bảng đã nạp lên lake.

Runtime của ứng dụng đọc metadata theo định dạng này. Tên bảng giữ đủ hai phần
`schema.table` vì catalog Trino không đặt schema mặc định, nên SQL sinh ra phải
tự gọi tên đủ. Kiểu cột dùng kiểu Trino thật thay vì kiểu của generator để mô
hình nhìn đúng thứ nó sắp truy vấn.

Khóa ngoại chỉ giữ lại khi cả hai đầu đều nằm trong phạm vi đã nạp; tham chiếu
ra ngoài phạm vi sẽ thành chỉ số rác trong định dạng này.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lakehouse_catalog import CATALOG_PATH, REPO_ROOT, SCOPE_CHOICES, resolve_scope

DATABASE_ID = os.getenv("LAKEHOUSE_DB_ID", "telecom_lakehouse")
OUTPUT_PATH = REPO_ROOT / "data" / "lakehouse" / "tables.json"


def _raw_catalog_by_fqn() -> dict[str, dict]:
    raw_tables = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {f"{raw['schema']}.{raw['table']}": raw for raw in raw_tables}


def main() -> int:
    scope = os.getenv("LAKEHOUSE_SCOPE", "sample8")
    if scope not in SCOPE_CHOICES:
        raise SystemExit(f"LAKEHOUSE_SCOPE không hợp lệ: {scope!r}. Chọn một trong {SCOPE_CHOICES}.")

    specs = resolve_scope(scope)
    raw_by_fqn = _raw_catalog_by_fqn()
    table_index = {spec.fqn: index for index, spec in enumerate(specs)}

    table_names_original: list[str] = []
    table_names: list[str] = []
    column_names_original: list[list] = [[-1, "*"]]
    column_names: list[list] = [[-1, "*"]]
    column_types: list[str] = ["text"]
    primary_keys: list = []
    foreign_keys: list[list[int]] = []

    column_index_by_key: dict[tuple[str, str], int] = {}

    for table_position, spec in enumerate(specs):
        raw = raw_by_fqn[spec.fqn]
        table_names_original.append(spec.fqn)
        table_names.append(raw.get("description") or spec.fqn)

        for column in spec.columns:
            column_index_by_key[(spec.fqn, column.name)] = len(column_names_original)
            column_names_original.append([table_position, column.name])

            described = next(
                (
                    c.get("source_description")
                    for c in raw["columns"]
                    if c["name"] == column.name and c.get("source_description")
                ),
                None,
            )
            column_names.append([table_position, described or column.name])
            column_types.append(column.trino_type.lower())

    for spec in specs:
        raw = raw_by_fqn[spec.fqn]
        for key_column in raw.get("primary_key") or []:
            index = column_index_by_key.get((spec.fqn, key_column))
            if index is not None:
                primary_keys.append(index)

        for foreign_key in raw.get("foreign_keys") or []:
            source = column_index_by_key.get((spec.fqn, foreign_key["column"]))
            reference = str(foreign_key.get("references") or "")
            schema_name, _, remainder = reference.partition(".")
            table_name, _, column_name = remainder.partition(".")
            target = column_index_by_key.get((f"{schema_name}.{table_name}", column_name))
            if source is not None and target is not None:
                foreign_keys.append([source, target])

    document = {
        "db_id": DATABASE_ID,
        "table_names_original": table_names_original,
        "table_names": table_names,
        "column_names_original": column_names_original,
        "column_names": column_names,
        "column_types": column_types,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps([document], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dropped = sum(len(raw_by_fqn[s.fqn].get("foreign_keys") or []) for s in specs) - len(foreign_keys)
    print(f"Phạm vi {scope}: {len(specs)} bảng, {len(column_names_original) - 1} cột")
    print(f"  khóa chính: {len(primary_keys)}")
    print(f"  khóa ngoại giữ lại: {len(foreign_keys)} (bỏ {dropped} tham chiếu ra ngoài phạm vi)")
    print(f"  đã ghi: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
