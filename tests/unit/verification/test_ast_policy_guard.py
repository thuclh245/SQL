from t2s.verification.ast_policy_guard import AstPolicyGuard, PolicyCatalog


def _guard(partitions: dict[str, str], severity: str = "block", dialect: str = "trino") -> AstPolicyGuard:
    return AstPolicyGuard(
        PolicyCatalog(partition_columns=partitions, nm_pairs=set(), partition_severity=severity),
        dialect=dialect,
    )


def test_unfiltered_table_is_flagged_and_filtered_table_passes() -> None:
    guard = _guard({"cell_hourly": "date_hour"})

    assert [f.code for f in guard.validate("SELECT * FROM cell_hourly")] == ["PARTITION"]
    assert guard.validate("SELECT * FROM cell_hourly WHERE date_hour >= '2026081900'") == []


def test_column_must_be_a_real_column_not_a_substring_of_the_where_text() -> None:
    guard = _guard({"events": "dt"})

    findings = guard.validate("SELECT * FROM events WHERE district = 'A'")

    assert [f.code for f in findings] == ["PARTITION"]


def test_severity_comes_from_the_catalog() -> None:
    guard = _guard({"t": "date_hour"}, severity="warning")

    findings = guard.validate("SELECT * FROM t")

    assert findings[0].severity == "warning"
    assert not guard.is_blocked(findings)


def test_qualified_key_matches_only_that_schema() -> None:
    guard = _guard({"ran_kpi.cell_hourly": "date_hour"})

    assert guard.validate("SELECT * FROM hive.ran_kpi.cell_hourly")
    assert guard.validate("SELECT * FROM hive.other.cell_hourly") == []


def test_filter_on_another_table_does_not_satisfy_the_requirement() -> None:
    guard = _guard({"a": "date_hour"})
    sql = "SELECT * FROM a JOIN b ON a.id = b.id WHERE b.date_hour = '2026081900'"

    assert [f.code for f in guard.validate(sql)] == ["PARTITION"]
    assert guard.validate(
        "SELECT * FROM a x JOIN b ON x.id = b.id WHERE x.date_hour = '2026081900'"
    ) == []


def test_unreferenced_table_needs_no_filter() -> None:
    assert _guard({"cell_hourly": "date_hour"}).validate("SELECT 1 FROM customers") == []
