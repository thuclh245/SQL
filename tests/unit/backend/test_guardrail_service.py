import pytest

from backend.config import LAKEHOUSE_DB_ID
from backend.services.guardrail_service import validate_query_safety
from backend.services.schema_service import get_db_schema_details


@pytest.fixture(scope="module")
def schema_info() -> dict:
    return get_db_schema_details(LAKEHOUSE_DB_ID)


def _time_rule(result: dict) -> dict:
    return next(item for item in result["checklist"] if "thời gian" in item["rule"])


def test_lakehouse_time_filter_missing_warns_but_does_not_block(schema_info: dict) -> None:
    result = validate_query_safety(
        LAKEHOUSE_DB_ID, "SELECT * FROM hive.ran_kpi.cell_hourly", schema_info
    )

    assert not result["is_blocked"]
    assert [f["severity"] for f in result["findings"]] == ["warning"]
    assert _time_rule(result)["status"] == "warning"
    assert "date_hour" in result["advice"]


def test_lakehouse_time_filter_present_passes(schema_info: dict) -> None:
    sql = "SELECT * FROM hive.ran_kpi.cell_hourly WHERE date_hour >= '2026081900'"

    result = validate_query_safety(LAKEHOUSE_DB_ID, sql, schema_info)

    assert result["findings"] == []
    assert _time_rule(result)["status"] == "passed"


def test_lakehouse_table_without_time_column_is_not_flagged(schema_info: dict) -> None:
    result = validate_query_safety(
        LAKEHOUSE_DB_ID, "SELECT count(*) FROM hive.customer.subscriber", schema_info
    )

    assert result["findings"] == []


def test_lakehouse_sql_is_parsed_as_trino(schema_info: dict) -> None:
    sql = "SELECT v FROM hive.ran_kpi.cell_hourly CROSS JOIN UNNEST(ARRAY[1, 2]) AS u(v) WHERE date_hour = '1'"

    result = validate_query_safety(LAKEHOUSE_DB_ID, sql, schema_info)

    assert result.get("block_reason") != "PARSE_ERROR"


def test_write_statements_stay_blocked(schema_info: dict) -> None:
    result = validate_query_safety(LAKEHOUSE_DB_ID, "DROP TABLE hive.ran_kpi.cell_hourly", schema_info)

    assert result["is_blocked"]
    assert result["block_reason"] == "READ_ONLY_VIOLATION"
