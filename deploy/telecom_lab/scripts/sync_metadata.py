"""Đẩy mô tả bảng/cột và nhãn nguồn từ catalog của snapshot vào OpenMetadata.

Ingestion từ Trino chỉ lấy được cấu trúc: Hive không lưu comment nên bảng nào
cũng về OM với mô tả rỗng. Phần ngữ nghĩa nằm ở catalog.json của generator, và
cổng G2 yêu cầu mọi mô tả phải mang nhãn nguồn để phân biệt phần có thật trong
mẫu với phần tự sinh.

Chạy:  /home/ubuntu/om-ingest/bin/python sync_metadata.py
Biến môi trường: OPENMETADATA_URL, OPENMETADATA_AUTH_TOKEN, OM_SERVICE_NAME.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lakehouse_catalog import CATALOG_PATH

BASE_URL = os.getenv("OPENMETADATA_URL", "http://127.0.0.1:8585").rstrip("/")
TOKEN = os.getenv("OPENMETADATA_AUTH_TOKEN", "")
SERVICE = os.getenv("OM_SERVICE_NAME", "telecom_lakehouse")
DATABASE = os.getenv("OM_DATABASE_NAME", "hive")

CLASSIFICATION = "provenance"
ORIGIN_DESCRIPTIONS = {
    "provided_sample": "Tên và cấu trúc xuất hiện trong bản mô tả OpenMetadata được cung cấp.",
    "synthetic_core": "Bảng lõi do generator sinh, bám theo cấu trúc mẫu.",
    "synthetic_extension": "Bảng mở rộng hoàn toàn do generator sinh, không có trong mẫu.",
}


def call(method: str, path: str, payload=None, content_type="application/json"):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": content_type,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        # 409 = đã tồn tại; với thao tác tạo nhãn thì đó là kết quả mong muốn.
        if error.code == 409:
            return None
        raise RuntimeError(f"{method} {path} -> {error.code}: {error.read()[:300]}") from error


def ensure_provenance_tags() -> None:
    call("PUT", "/api/v1/classifications", {
        "name": CLASSIFICATION,
        "displayName": "Nguồn dữ liệu",
        "description": "Phân biệt phần có thật trong mẫu với phần do generator sinh.",
    })
    for name, description in ORIGIN_DESCRIPTIONS.items():
        call("PUT", "/api/v1/tags", {
            "classification": CLASSIFICATION,
            "name": name,
            "description": description,
        })


def build_patch(table: dict, spec: dict) -> list[dict]:
    """JSON Patch chỉ chứa những thay đổi thật, để lần chạy sau không tạo version mới."""
    operations: list[dict] = []

    description = spec.get("description")
    if description and table.get("description") != description:
        operations.append({
            "op": "add" if not table.get("description") else "replace",
            "path": "/description",
            "value": description,
        })

    tag_fqn = f"{CLASSIFICATION}.{spec.get('origin') or 'synthetic_extension'}"
    existing = {t.get("tagFQN") for t in (table.get("tags") or [])}
    if tag_fqn not in existing:
        operations.append({
            "op": "add",
            "path": f"/tags/{len(table.get('tags') or [])}",
            "value": {
                "tagFQN": tag_fqn,
                "source": "Classification",
                "labelType": "Manual",
                "state": "Confirmed",
            },
        })

    described = {
        c["name"]: c["source_description"]
        for c in spec["columns"]
        if c.get("source_description")
    }
    for index, column in enumerate(table.get("columns") or []):
        wanted = described.get(column.get("name"))
        if wanted and column.get("description") != wanted:
            operations.append({
                "op": "add" if not column.get("description") else "replace",
                "path": f"/columns/{index}/description",
                "value": wanted,
            })

    return operations


def main() -> int:
    if not TOKEN:
        raise SystemExit("Thiếu OPENMETADATA_AUTH_TOKEN.")

    raw_catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    spec_by_fqn = {f"{t['schema']}.{t['table']}": t for t in raw_catalog}

    ensure_provenance_tags()

    listing = call("GET", f"/api/v1/tables?limit=1000&fields=columns,tags&service={SERVICE}")
    om_tables = listing.get("data", []) if listing else []
    print(f"OpenMetadata đang có {len(om_tables)} bảng trong service {SERVICE}\n")

    updated = 0
    unchanged = 0
    missing: list[str] = []

    for table in om_tables:
        fqn = table["fullyQualifiedName"]
        # FQN: <service>.<database>.<schema>.<table> -> khóa catalog là <schema>.<table>
        parts = fqn.split(".")
        key = ".".join(parts[-2:])
        spec = spec_by_fqn.get(key)
        if spec is None:
            missing.append(fqn)
            continue

        operations = build_patch(table, spec)
        if not operations:
            unchanged += 1
            continue

        call("PATCH", f"/api/v1/tables/{table['id']}", operations,
             content_type="application/json-patch+json")
        updated += 1
        columns_touched = sum(1 for o in operations if o["path"].startswith("/columns/"))
        print(f"  {key:<34} mô tả + nhãn {spec.get('origin'):<20} cột: {columns_touched}")

    print(f"\ncập nhật: {updated}   |   đã đúng sẵn: {unchanged}")
    if missing:
        print(f"\nKhông tìm thấy trong catalog ({len(missing)}):")
        for fqn in missing[:10]:
            print(f"  {fqn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
