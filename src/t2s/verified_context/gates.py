"""Deterministic gates that decline before any SQL is generated.

* policy: requests for personal identifying data are refused, even when the
  columns exist (the refusal is a policy decision, not missing data);
* ambiguity: glossary terms with several business meanings trigger a
  clarification question listing the meanings;
* time coverage: dates asked for that fall entirely outside the data held by the
  tables in scope are declined with the actual coverage.

Gates decide from the question, the glossary and the measured profile; the LLM
is not asked to judge whether it should answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from t2s.verified_context.linking import Glossary, normalize

# Định dạng số dd/mm[/yyyy] không phụ thuộc ngôn ngữ; mọi cụm từ nằm trong glossary.
DMY = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])")


@dataclass(frozen=True)
class GateDecision:
    kind: str  # "abstain" | "clarify"
    gate: str
    message: str
    options: tuple[str, ...] = ()


@dataclass
class TimeRequest:
    start: date
    end: date
    text: str


@dataclass
class GateReport:
    decision: GateDecision | None
    checks: list[dict[str, str]] = field(default_factory=list)


def sensitive_gate(question: str, glossary: Glossary) -> GateDecision | None:
    q = normalize(question)
    hits = [t for t in glossary.sensitive_terms if t in q]
    if not hits:
        return None
    return GateDecision(
        "abstain",
        "policy",
        "Yêu cầu dữ liệu định danh cá nhân (" + ", ".join(hits) + "). "
        "Chính sách truy cập không cho phép trích xuất hàng loạt thông tin này.",
    )


def ambiguity_gate(question: str, glossary: Glossary, concepts: set[str]) -> GateDecision | None:
    q = normalize(question)
    if glossary.clarified_marker and normalize(glossary.clarified_marker) in q:
        return None
    for tid, spec in glossary.ambiguous_terms.items():
        match = re.search(spec["pattern"], q)
        if not match:
            continue
        unless = spec.get("unless_pattern")
        if unless and re.search(unless, q):
            continue
        required = set(spec.get("requires_concepts") or [])
        if required and not required <= concepts:
            continue
        if set(spec.get("unless_concepts") or []) & concepts:
            continue
        options = tuple(spec.get("options") or [])
        return GateDecision(
            "clarify",
            f"ambiguity:{tid}",
            f"“{match.group(0).strip()}” có {len(options)} cách hiểu; bạn muốn dùng cách nào?",
            options,
        )
    return None


def requested_periods(question: str, today: date, glossary: Glossary) -> list[TimeRequest]:
    q = normalize(question)
    expr = glossary.time_expressions
    found: list[TimeRequest] = []
    years = [int(y) for y in re.findall(r"/(\d{4})", q)]
    default_year = years[-1] if years else None
    for m in DMY.finditer(q):
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(y) if y else default_year
        if year is None or not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        try:
            day = date(year, mo, d)
        except ValueError:
            continue
        found.append(TimeRequest(day, day, m.group(0)))
    for m in _finditer(expr.get("month_pattern"), q):
        mo, year = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            start = date(year, mo, 1)
            end = date(year + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)
            found.append(TimeRequest(start, end, m.group(0)))
    for m in _finditer(expr.get("year_pattern"), q):
        year = int(m.group(1))
        found.append(TimeRequest(date(year, 1, 1), date(year, 12, 31), m.group(0)))
    for phrase, days in (expr.get("relative_days") or {}).items():
        if normalize(phrase) in q:
            found.append(TimeRequest(today - timedelta(days=int(days)), today, phrase))
    future = expr.get("future_pattern")
    if future and re.search(future, q):
        found.append(
            TimeRequest(today + timedelta(days=1), today + timedelta(days=3650), "tương lai")
        )
    return found


def _finditer(pattern: str | None, text: str) -> list[re.Match[str]]:
    return list(re.finditer(pattern, text)) if pattern else []


def parse_bound(value: str) -> date | None:
    value = value.strip()
    if value.isdigit() and len(value) >= 9:  # epoch giây
        return datetime.fromtimestamp(int(value), tz=UTC).date()
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def coverage_gate(
    question: str, ranges: dict[str, tuple[str, str]], today: date, glossary: Glossary
) -> tuple[GateDecision | None, list[TimeRequest]]:
    periods = requested_periods(question, today, glossary)
    bounds = [(parse_bound(lo), parse_bound(hi)) for lo, hi in ranges.values()]
    spans = [(lo, hi) for lo, hi in bounds if lo is not None and hi is not None]
    if not periods or not spans:
        return None, periods
    lo, hi = min(s[0] for s in spans), max(s[1] for s in spans)
    outside = [p for p in periods if p.end < lo or p.start > hi]
    if not outside:
        return None, periods
    asked = ", ".join(p.text for p in outside)
    return (
        GateDecision(
            "abstain",
            "time_coverage",
            f"Thời gian được hỏi ({asked}) nằm ngoài phạm vi dữ liệu hiện có: "
            f"{lo.isoformat()} → {hi.isoformat()}.",
        ),
        periods,
    )
