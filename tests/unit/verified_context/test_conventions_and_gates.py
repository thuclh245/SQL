from datetime import date

import pytest

from t2s.verified_context.conventions import (
    ConventionRegistry,
    check_literal_format,
    check_requires_anti_join,
    parse,
)
from t2s.verified_context.gates import (
    ambiguity_gate,
    coverage_gate,
    requested_periods,
    sensitive_gate,
)
from t2s.verified_context.linking import Glossary

KPI = "hive__npms__kpi_access5g_5g_cell_peak_view"
OCEAN = "hive.npms.occean_cell"


@pytest.mark.parametrize(
    "sql",
    [
        f"SELECT t.object_id FROM {KPI} t WHERE NOT EXISTS "
        "(SELECT 1 FROM hive__npms__occean_cell c WHERE c.object_id = t.object_id)",
        f"SELECT k.object_id FROM {KPI} k ANTI JOIN hive__npms__occean_cell o "
        "ON k.object_id = o.object_id",
        "WITH oc AS (SELECT object_id FROM hive__npms__occean_cell) "
        f"SELECT k.object_id FROM {KPI} k LEFT JOIN oc ON k.object_id = oc.object_id "
        "WHERE oc.object_id IS NULL",
    ],
)
def test_anti_join_forms_are_accepted(sql: str) -> None:
    assert check_requires_anti_join(parse(sql), OCEAN, "object_id") == []


def test_inner_join_with_exclusion_table_is_a_violation() -> None:
    sql = (
        f"SELECT k.object_id FROM {KPI} k "
        "JOIN hive__npms__occean_cell c ON k.object_id = c.object_id"
    )
    assert check_requires_anti_join(parse(sql), OCEAN, "object_id")


def test_cast_of_date_hour_is_a_format_violation() -> None:
    sql = f"SELECT 1 FROM {KPI} WHERE CAST(date_hour AS DATE) = DATE '2026-08-20'"
    assert check_literal_format(parse(sql), "date_hour", r"^\d{4}-\d{2}-\d{2}-\d{2}$")


def test_registry_selects_by_question_and_verifies_only_accepted() -> None:
    registry = ConventionRegistry(
        [
            {
                "id": "BAD",
                "status": "accepted",
                "rule": "loại occean",
                "applies_when": {"question_terms": ["cell xấu"]},
                "check": {"kind": "requires_anti_join", "table": OCEAN, "key": "object_id"},
            },
            {
                "id": "PROP",
                "status": "proposed",
                "rule": "đề xuất",
                "applies_when": {},
                "check": {"kind": "not_implemented"},
            },
        ]
    )
    selected = registry.select(question="có bao nhiêu cell xấu", tables=[], columns=set())
    assert [c["id"] for c in selected] == ["BAD", "PROP"]
    assert registry.select(question="lưu lượng", tables=[], columns=set())[0]["id"] == "PROP"
    found = registry.verify(f"SELECT object_id FROM {KPI}", question="cell xấu", tables=[])
    assert [v.convention_id for v in found] == ["BAD"]


GLOSSARY = Glossary(
    concepts={"alarm": {"terms": ["cảnh báo"], "tables": {"hive.gnoc.gnoc": 1.0}}},
    ambiguous_terms={
        "alarm_area": {
            "pattern": "khu vực",
            "unless_pattern": "vùng",
            "requires_concepts": ["alarm"],
            "options": ["region", "tỉnh"],
        }
    },
    sensitive_terms=("số điện thoại",),
    time_expressions={
        "month_pattern": r"tháng\s+(\d{1,2})\s*/\s*(\d{4})",
        "relative_days": {"hôm nay": 0},
    },
    clarified_marker="ý tôi là:",
)


def test_ambiguity_gate_depends_on_concepts_and_unless_pattern() -> None:
    assert ambiguity_gate("Khu vực nào nhiều cảnh báo nhất?", GLOSSARY, {"alarm"}) is not None
    assert ambiguity_gate("Khu vực nào có nhiều tỉnh nhất?", GLOSSARY, set()) is None
    assert ambiguity_gate("Vùng, khu vực nào nhiều cảnh báo?", GLOSSARY, {"alarm"}) is None
    clarified = "Khu vực nào nhiều cảnh báo nhất? (ý tôi là: Tỉnh)"
    assert ambiguity_gate(clarified, GLOSSARY, {"alarm"}) is None


def test_sensitive_gate_refuses_personal_data() -> None:
    decision = sensitive_gate("Cho tôi số điện thoại từng thuê bao", GLOSSARY)
    assert decision is not None and decision.gate == "policy"


def test_periods_inherit_year_and_parse_months_and_relative_dates() -> None:
    today = date(2026, 9, 24)
    texts = [p.text for p in requested_periods("Từ 14/8 đến 20/8/2026", today, GLOSSARY)]
    assert texts == ["14/8", "20/8/2026"]
    month = requested_periods("tháng 12/2025", today, GLOSSARY)[0]
    assert (month.start, month.end) == (date(2025, 12, 1), date(2025, 12, 31))
    assert requested_periods("hôm nay", today, GLOSSARY)[0].start == today


def test_coverage_gate_declines_only_when_no_overlap() -> None:
    ranges = {"kpi.date_hour": ("2026-08-01-00", "2026-08-20-00")}
    today = date(2026, 9, 24)
    assert coverage_gate("ngày 20/8/2026", ranges, today, GLOSSARY)[0] is None
    decision, _ = coverage_gate("tháng 12/2025", ranges, today, GLOSSARY)
    assert decision is not None and "2026-08-20" in decision.message
    assert coverage_gate("hôm nay", ranges, today, GLOSSARY)[0] is not None
    assert coverage_gate("không nêu thời gian", ranges, today, GLOSSARY)[0] is None
