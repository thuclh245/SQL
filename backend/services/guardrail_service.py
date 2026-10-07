"""Domain-aware AST policy guardrail service."""

from __future__ import annotations

from typing import Any
import sqlglot
from sqlglot import exp

from backend.config import LAKEHOUSE_DB_ID, LAKEHOUSE_TIME_COLUMN
from t2s.verification.ast_policy_guard import AstPolicyGuard, PolicyCatalog


def _time_filter_requirements(schema_info: dict[str, Any] | None) -> dict[str, str]:
    """Bảng nào có cột thời gian thì cần lọc theo cột đó, lấy từ metadata schema.

    Khoá là tên trần nếu duy nhất trong CSDL, ngược lại là `schema.bảng`, để một
    tham chiếu không chỉ rõ schema vẫn khớp mà không bắt nhầm bảng cùng tên.
    """
    if not schema_info:
        return {}
    tables = schema_info.get("tables", [])
    columns = schema_info.get("columns", {})
    bare_counts: dict[str, int] = {}
    for table in tables:
        bare = table.rsplit(".", 1)[-1].lower()
        bare_counts[bare] = bare_counts.get(bare, 0) + 1

    required: dict[str, str] = {}
    for table in tables:
        if LAKEHOUSE_TIME_COLUMN in (c.lower() for c in columns.get(table, [])):
            bare = table.rsplit(".", 1)[-1]
            unique = bare_counts[bare.lower()] == 1
            required[bare if unique else table] = LAKEHOUSE_TIME_COLUMN
    return required


def validate_query_safety(db_id: str, sql: str, schema_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Kiểm tra an toàn câu lệnh SQL theo từng domain cơ sở dữ liệu."""
    if not sql or not sql.strip():
        return {
            "is_blocked": True,
            "block_reason": "SQL_EMPTY",
            "findings": [{"code": "EMPTY", "severity": "block", "message": "Không có câu lệnh SQL hợp lệ nào được sinh ra."}],
            "checklist": [
                {
                    "rule": "Cú pháp SQL",
                    "status": "failed",
                    "detail": "Câu lệnh SQL rỗng hoặc không được sinh thành công từ mô hình.",
                }
            ],
            "advice": "Mô hình không sinh được câu lệnh phù hợp cho câu hỏi này. Vui lòng thử diễn đạt lại câu hỏi rõ ràng hơn.",
        }

    # 1. Parse SQL syntax
    dialect = "trino" if db_id == LAKEHOUSE_DB_ID else "sqlite"
    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as exc:
        return {
            "is_blocked": True,
            "block_reason": "PARSE_ERROR",
            "findings": [{"code": "PARSE", "severity": "block", "message": f"Cú pháp SQL không hợp lệ: {exc}"}],
            "checklist": [
                {
                    "rule": "Kiểm tra Cú pháp AST",
                    "status": "failed",
                    "detail": f"Không thể phân tích cây cú pháp: {exc}",
                }
            ],
            "advice": "Câu lệnh SQL bị lỗi cú pháp khi phân tích cây ngữ pháp (AST). Vui lòng thử lại với một mô hình khác.",
        }

    # 2. General Read-Only Guard (áp dụng cho TOÀN BỘ mọi cơ sở dữ liệu)
    forbidden_exprs = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
        exp.Alter, exp.TruncateTable
    )
    for bad in forbidden_exprs:
        if tree.find(bad):
            msg = f"Phát hiện lệnh ghi/thay đổi cấu trúc dữ liệu nguy hại: {bad.__name__}"
            return {
                "is_blocked": True,
                "block_reason": "READ_ONLY_VIOLATION",
                "findings": [{"code": "READ_ONLY", "severity": "block", "message": msg}],
                "checklist": [
                    {
                        "rule": "Chỉ đọc (Read-Only Guard)",
                        "status": "failed",
                        "detail": "Hệ thống chỉ cho phép các câu lệnh SELECT đọc dữ liệu an toàn.",
                    }
                ],
                "advice": "Hệ thống hoạt động ở chế độ 100% Read-Only để bảo vệ toàn vẹn dữ liệu. Mọi lệnh ghi hoặc xóa bảng đều bị từ chối.",
            }

    # 3. Domain-Specific Policy Guards
    checklist = [
        {
            "rule": "Chỉ đọc (Read-Only Guard)",
            "status": "passed",
            "detail": "Không chứa lệnh ghi dữ liệu nguy hại (INSERT/UPDATE/DROP/ALTER)",
        }
    ]
    findings: list[dict[str, Any]] = []
    is_blocked = False
    advice = ""

    if db_id == LAKEHOUSE_DB_ID:
        # Lakehouse: đòi lọc theo cột thời gian trên bảng có cột đó để tránh quét toàn bảng.
        # Mức cảnh báo, không chặn: đây là quy ước suy ra từ metadata chứ chưa phải partition thật.
        requirements = _time_filter_requirements(schema_info)
        telecom_guard = AstPolicyGuard(
            catalog=PolicyCatalog(
                partition_columns=requirements,
                nm_pairs=set(),
                partition_severity="warning",
            ),
            dialect=dialect,
        )
        raw_findings = telecom_guard.validate(sql)
        is_blocked = telecom_guard.is_blocked(raw_findings)
        findings = [{"code": f.code, "severity": f.severity, "message": f.message} for f in raw_findings]

        has_time_filter_warning = any(f["code"] == "PARTITION" for f in findings)
        checklist.append({
            "rule": f"Lọc theo cột thời gian ({LAKEHOUSE_TIME_COLUMN})",
            "status": "warning" if has_time_filter_warning else "passed",
            "detail": (
                f"Bảng có cột '{LAKEHOUSE_TIME_COLUMN}' nên được lọc theo cột đó để tránh quét toàn bảng"
                if requirements
                else "Metadata không có bảng nào cần lọc theo cột thời gian"
            ),
        })

        if has_time_filter_warning:
            advice = (
                f"Thêm điều kiện lọc trên cột '{LAKEHOUSE_TIME_COLUMN}' "
                f"(ví dụ: WHERE {LAKEHOUSE_TIME_COLUMN} >= '2026081900') để giảm khối lượng quét."
            )
    else:
        # Các CSDL khác (california_schools, financial, codebase_community, imported_databases):
        # Kiểm tra tính toàn vẹn cú pháp chung
        checklist.append({
            "rule": "Phân tích Cú pháp SQLite",
            "status": "passed",
            "detail": "Cấu trúc truy vấn SELECT tuân thủ chuẩn SQLite",
        })

    return {
        "is_blocked": is_blocked,
        "findings": findings,
        "checklist": checklist,
        "advice": advice,
    }
