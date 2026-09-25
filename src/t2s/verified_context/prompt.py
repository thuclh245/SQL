"""Prompt assembly: fixed rules plus a per-question context bundle.

The context lists only what the model needs (tables in scope, real types,
columns that carry data), and every fact is tagged with where it came from so
that wrong metadata can be traced (``[AI]`` descriptions are unverified).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from t2s.verified_context.conventions import Convention
from t2s.verified_context.linking import CatalogTable, tokens
from t2s.verified_context.profile import TableProfile

KEY_DIMS = {
    "object_id",
    "date_hour",
    "date",
    "province_code",
    "area_code",
    "district_code",
    "country",
}
MAX_COLUMNS_WITHOUT_PROFILE = 40
MAX_DESCRIPTION = 160

BASE_RULES = """Bạn là chuyên gia Text-to-SQL cho kho dữ liệu viễn thông VTNet (DuckDB).
- Chỉ dùng bảng và cột được liệt kê; kiểu dữ liệu ghi bên cạnh là kiểu thật trong CSDL.
- Cột kiểu VARCHAR chứa số phải CAST sang kiểu số trước khi so sánh, tính toán hoặc sắp xếp.
- Khi JOIN, luôn ghi alias bảng cho mọi cột."""

CONTRACT = """Trả về đúng MỘT trong ba dạng, không giải thích thêm:
SQL: <một câu SELECT DuckDB>
CLARIFY: <câu hỏi lại người dùng> | <cách hiểu 1> | <cách hiểu 2>
ABSTAIN: <lý do>
- ABSTAIN khi thông tin cần thiết không có trong các bảng dưới đây.
- CLARIFY khi câu hỏi có từ hai cách hiểu trở lên dẫn tới kết quả khác nhau."""

SQL_ONLY = "Trả về duy nhất một câu SELECT DuckDB, không markdown, không giải thích."


@dataclass
class TableContext:
    fqn: str
    duckdb_table: str
    lines: list[str]
    shown_columns: set[str]
    grain_notes: list[str] = field(default_factory=list)


def _shorten(text: str) -> str:
    return text if len(text) <= MAX_DESCRIPTION else text[: MAX_DESCRIPTION - 1] + "…"


def _clean_description(text: str, source: str) -> str:
    """Tag unverified AI text as [AI] and keep profiler facts as [Profiler]."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    ai_part, _, profiler_part = text.partition("[Profiler]")
    out = []
    ai_part = ai_part.replace("[AI Gen]", "").strip()
    if ai_part:
        out.append(("[AI] " if source.startswith("ai_gen") else "") + _shorten(ai_part))
    if profiler_part:
        facts = re.sub(
            r"Có \d+ giá trị chung với ([\w.]+); có thể dùng làm khóa nối\.",
            lambda m: f"khóa nối với {m.group(1).split('.', 1)[1]}.",
            "[Profiler]" + profiler_part,
        )
        out.append(re.sub(r"\s*\[Profiler\]\s*", " ", facts).strip().join(["[Profiler] ", ""]))
    return " ".join(out)


def table_context(
    table: CatalogTable,
    profile: TableProfile,
    *,
    question: str,
    use_profile: bool,
    with_descriptions: bool,
) -> TableContext:
    q_tokens = tokens(question)
    if use_profile:
        names = [c.name.lower() for c in profile.informative_columns]
    else:
        ranked = sorted(
            profile.columns,
            key=lambda c: (
                -(
                    40 * (c in KEY_DIMS)
                    + 60 * (c in question.lower())
                    + 5 * len(q_tokens & set(c.split("_")))
                ),
                c,
            ),
        )
        names = ranked[:MAX_COLUMNS_WITHOUT_PROFILE]
    header = table.duckdb_table
    if with_descriptions and table.description:
        header += f" — {_clean_description(table.description, 'ai_gen')}"
    if use_profile:
        header += (
            f"  ({profile.rows} dòng; chỉ liệt kê {len(names)}/{len(profile.columns)} "
            "cột có dữ liệu)"
        )
    lines = [header]
    for name in names:
        col = profile.columns[name]
        notes = []
        meta = table.columns.get(name)
        if with_descriptions and meta and meta.description:
            notes.append(_clean_description(meta.description, meta.source))
        if use_profile and col.values:
            notes.append("giá trị: " + ", ".join(repr(v) if v == "" else v for v in col.values))
        if use_profile and col.value_range:
            notes.append(f"phạm vi: {col.value_range[0]} → {col.value_range[1]}")
        lines.append(
            f"  - {col.name} {col.data_type}" + (f" — {'; '.join(notes)}" if notes else "")
        )
    return TableContext(
        fqn=table.fqn,
        duckdb_table=table.duckdb_table,
        lines=lines,
        shown_columns=set(names),
        grain_notes=list(profile.grain_notes) if use_profile else [],
    )


def build_system_prompt(
    tables: list[TableContext],
    conventions: list[Convention],
    *,
    contract: bool,
    definitions: list[str] | None = None,
) -> str:
    parts = [BASE_RULES, CONTRACT if contract else SQL_ONLY, "BẢNG LIÊN QUAN:"]
    parts.append("\n\n".join("\n".join(t.lines) for t in tables) or "(không có bảng nào)")
    grain = [f"- {t.duckdb_table}: {note}" for t in tables for note in t.grain_notes]
    if grain:
        parts.append("ĐỘ HẠT DỮ LIỆU (grain):\n" + "\n".join(grain))
    if definitions:
        parts.append(
            "ĐỊNH NGHĨA NGHIỆP VỤ (glossary):\n" + "\n".join(f"- {d}" for d in definitions)
        )
    if conventions:
        lines = [
            f"- {c['rule']}"
            + ("" if c.get("status") == "accepted" else " (đề xuất, chờ DE xác nhận)")
            for c in conventions
        ]
        parts.append("QUY ƯỚC NGHIỆP VỤ:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def repair_message(question: str, sql: str, problems: list[str]) -> str:
    bullet = "\n".join(f"- {p}" for p in problems)
    return (
        f"{question}\n\nCâu SQL trước đó của bạn:\n{sql}\n\n"
        f"Bộ kiểm chứng phát hiện các vấn đề sau:\n{bullet}\n\n"
        "Hãy sửa và trả lại theo đúng định dạng yêu cầu."
    )
