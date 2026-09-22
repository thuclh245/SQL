"""Domain-aware AST policy guardrail service."""

from __future__ import annotations

from typing import Any
import sqlglot
from sqlglot import exp

from t2s.verification.ast_policy_guard import AstPolicyGuard, PolicyCatalog


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
    try:
        tree = sqlglot.parse_one(sql, dialect="sqlite")
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

    if db_id == "telecom_lakehouse":
        # Riêng Viễn thông Lakehouse áp dụng Partition Guard trên bảng cước CDR và rủi ro N:M
        telecom_guard = AstPolicyGuard(
            catalog=PolicyCatalog(
                partition_columns={
                    "cdr_voice": "dt",
                    "cdr_data": "dt",
                    "call_records": "dt",
                },
                nm_pairs={
                    ("cdr_voice", "dim_offer"),
                    ("cdr_voice", "promos"),
                },
            ),
            dialect="sqlite",
        )
        raw_findings = telecom_guard.validate(sql)
        is_blocked = telecom_guard.is_blocked(raw_findings)
        findings = [{"code": f.code, "severity": f.severity, "message": f.message} for f in raw_findings]

        has_partition_err = any(f["code"] == "PARTITION" for f in findings)
        has_fanout_warn = any(f["code"] == "FANOUT" for f in findings)

        checklist.append({
            "rule": "Cột phân vùng Lakehouse (Partition Guard)",
            "status": "failed" if has_partition_err else "passed",
            "detail": "Bắt buộc lọc theo ngày 'dt' trên bảng CDR để ngăn Full-Table Scan",
        })
        checklist.append({
            "rule": "Bảo vệ N:M Fan-out (Card Guard)",
            "status": "warning" if has_fanout_warn else "passed",
            "detail": "Kiểm tra nguy cơ nhân đôi bản ghi khi JOIN nhiều-nhiều thiếu DISTINCT/GROUP BY",
        })

        if is_blocked:
            advice = "Bổ sung điều kiện lọc trực tiếp trên cột phân vùng vật lý (ví dụ: WHERE dt = '...') để tận dụng Partition Pruning thay vì quét toàn bộ bảng."
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
