"""Value-grounding behaviour over a synthetic schema.

The fixture schema deliberately shares no names with any benchmark dataset, so a
rule accidentally tuned to a benchmark table, column or literal would not pass
here.
"""

import sqlite3
from pathlib import Path

import pytest

from t2s.catalog import CatalogColumn, CatalogForeignKey, CatalogTable
from t2s.grounding.value_grounding import (
    SqliteValueProbe,
    ValueGrounder,
    ValueGroundingBudget,
    ValueMatchType,
)

TIER_VALUES = ("enterprise", "small_business", "consumer")


def _build_accounts_database(directory: Path) -> Path:
    """Create a small database with an enum-like column and a free-text column."""
    database_path = directory / "workspace.sqlite"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE regions (region_id INTEGER PRIMARY KEY, region_label TEXT);
        CREATE TABLE accounts (
            account_id INTEGER PRIMARY KEY,
            region_id INTEGER,
            tier TEXT,
            display_note TEXT,
            contact_email TEXT
        );
        CREATE TABLE usage_events (
            event_id INTEGER PRIMARY KEY,
            account_id INTEGER,
            usage_amount REAL
        );
        """
    )
    connection.executemany(
        "INSERT INTO regions (region_id, region_label) VALUES (?, ?)",
        [(1, "Northern"), (2, "Southern")],
    )
    connection.executemany(
        "INSERT INTO accounts VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, "enterprise", "a long free form note about this account", "a@example.test"),
            (2, 1, "small_business", "another entirely different free note", "b@example.test"),
            (3, 2, "consumer", "yet another unique free form remark", "c@example.test"),
            (4, 2, None, "note with a null tier", "d@example.test"),
        ],
    )
    connection.executemany(
        "INSERT INTO usage_events VALUES (?, ?, ?)",
        [(1, 1, 10.5), (2, 2, 3.25)],
    )
    connection.commit()
    connection.close()
    return database_path


def _build_catalog_tables(
    tier_column_name: str = "tier",
    accounts_table_name: str = "accounts",
    tier_tags: list[str] | None = None,
) -> list[CatalogTable]:
    """Build catalog metadata, parameterised so identifiers can be renamed in tests."""
    return [
        CatalogTable(
            table_fqn=f"svc.db.main.{accounts_table_name}",
            service_name="svc",
            database_name="db",
            schema_name="main",
            table_name=accounts_table_name,
            sql_identifier=accounts_table_name,
            columns=[
                CatalogColumn(
                    column_fqn=f"svc.db.main.{accounts_table_name}.account_id",
                    column_name="account_id",
                    data_type="integer",
                    is_primary_key=True,
                ),
                CatalogColumn(
                    column_fqn=f"svc.db.main.{accounts_table_name}.region_id",
                    column_name="region_id",
                    data_type="integer",
                ),
                CatalogColumn(
                    column_fqn=f"svc.db.main.{accounts_table_name}.{tier_column_name}",
                    column_name=tier_column_name,
                    data_type="text",
                    tags=tier_tags or [],
                ),
                CatalogColumn(
                    column_fqn=f"svc.db.main.{accounts_table_name}.display_note",
                    column_name="display_note",
                    data_type="text",
                ),
                CatalogColumn(
                    column_fqn=f"svc.db.main.{accounts_table_name}.contact_email",
                    column_name="contact_email",
                    data_type="text",
                    tags=["PII"],
                ),
            ],
            primary_key_column_names=["account_id"],
        ),
        CatalogTable(
            table_fqn="svc.db.main.regions",
            service_name="svc",
            database_name="db",
            schema_name="main",
            table_name="regions",
            sql_identifier="regions",
            columns=[
                CatalogColumn(
                    column_fqn="svc.db.main.regions.region_id",
                    column_name="region_id",
                    data_type="integer",
                    is_primary_key=True,
                ),
                CatalogColumn(
                    column_fqn="svc.db.main.regions.region_label",
                    column_name="region_label",
                    data_type="text",
                ),
            ],
            primary_key_column_names=["region_id"],
        ),
    ]


def _ground(
    database_path: Path,
    question: str,
    catalog_tables: list[CatalogTable] | None = None,
    budget: ValueGroundingBudget | None = None,
    excluded_column_names: set[str] | None = None,
    relationships: list[CatalogForeignKey] | None = None,
):
    tables = catalog_tables if catalog_tables is not None else _build_catalog_tables()
    excluded = excluded_column_names or set()
    selected = {
        table.table_fqn: {
            column.column_name for column in table.columns if column.column_name not in excluded
        }
        for table in tables
    }
    grounder = ValueGrounder(
        value_probe=SqliteValueProbe(database_path),
        budget=budget or ValueGroundingBudget(),
    )
    return grounder.ground_values(
        question=question,
        catalog_tables=tables,
        selected_column_names_by_table_fqn=selected,
        relationships=relationships or [],
    )


def test_exact_value_match_is_bound_with_database_spelling(tmp_path: Path) -> None:
    database_path = _build_accounts_database(tmp_path)

    result = _ground(database_path, "How many enterprise accounts are there?")

    bindings = [b for b in result.bindings if b.candidate_value == "enterprise"]
    assert len(bindings) == 1
    assert bindings[0].column_name == "tier"
    assert bindings[0].match_type == ValueMatchType.EXACT
    assert bindings[0].evidence_score == 1.0


def test_case_insensitive_match_preserves_stored_literal(tmp_path: Path) -> None:
    """The binding must carry the database's spelling, not the question's."""
    database_path = _build_accounts_database(tmp_path)

    result = _ground(database_path, "How many ENTERPRISE accounts are there?")

    bindings = [b for b in result.bindings if b.column_name == "tier"]
    assert len(bindings) == 1
    assert bindings[0].candidate_value == "enterprise"
    assert bindings[0].phrase == "ENTERPRISE"
    assert bindings[0].match_type == ValueMatchType.CASE_INSENSITIVE


def test_multi_word_value_binds_from_adjacent_question_words(tmp_path: Path) -> None:
    database_path = _build_accounts_database(tmp_path)

    result = _ground(database_path, "revenue for small_business accounts")

    assert any(b.candidate_value == "small_business" for b in result.bindings)


def test_question_without_any_stored_value_produces_no_bindings(tmp_path: Path) -> None:
    database_path = _build_accounts_database(tmp_path)

    result = _ground(database_path, "How many accounts churned last quarter?")

    assert result.bindings == []
    assert result.diagnostics.probe_count > 0


def test_null_values_are_never_bound(tmp_path: Path) -> None:
    database_path = _build_accounts_database(tmp_path)

    result = _ground(database_path, "accounts where tier is null or none")

    assert all(b.candidate_value is not None for b in result.bindings)
    assert all(b.candidate_value != "" for b in result.bindings)


def test_unicode_values_match_case_insensitively(tmp_path: Path) -> None:
    """Case folding happens in Python, so it must work outside ASCII."""
    database_path = tmp_path / "unicode.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, tier TEXT)")
    connection.execute("INSERT INTO accounts VALUES (1, 'Doanh Nghiệp')")
    connection.commit()
    connection.close()

    result = _ground(
        database_path,
        "how many doanh nghiệp accounts are there?",
        catalog_tables=[
            CatalogTable(
                table_fqn="svc.db.main.accounts",
                service_name="svc",
                database_name="db",
                schema_name="main",
                table_name="accounts",
                sql_identifier="accounts",
                columns=[
                    CatalogColumn(
                        column_fqn="svc.db.main.accounts.account_id",
                        column_name="account_id",
                        data_type="integer",
                        is_primary_key=True,
                    ),
                    CatalogColumn(
                        column_fqn="svc.db.main.accounts.tier",
                        column_name="tier",
                        data_type="text",
                    ),
                ],
                primary_key_column_names=["account_id"],
            )
        ],
    )

    assert [b.candidate_value for b in result.bindings] == ["Doanh Nghiệp"]


def test_multiple_candidate_columns_are_each_probed(tmp_path: Path) -> None:
    database_path = _build_accounts_database(tmp_path)

    result = _ground(database_path, "enterprise accounts in the Northern region")

    bound_columns = {b.column_name for b in result.bindings}
    assert {"tier", "region_label"} <= bound_columns


def test_column_excluded_from_grounding_context_is_not_probed(tmp_path: Path) -> None:
    """Value lookup may only touch columns the grounding context already carries."""
    database_path = _build_accounts_database(tmp_path)

    result = _ground(
        database_path,
        "How many enterprise accounts are there?",
        excluded_column_names={"tier"},
    )

    assert all(b.column_name != "tier" for b in result.bindings)


def test_high_cardinality_domain_is_not_enumerated_into_bindings(tmp_path: Path) -> None:
    """A column whose domain exceeds the budget is dropped, not partially surfaced."""
    database_path = tmp_path / "wide.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, label TEXT)")
    connection.executemany(
        "INSERT INTO accounts VALUES (?, ?)",
        [(i, f"distinct_label_{i}") for i in range(200)],
    )
    connection.commit()
    connection.close()

    result = _ground(
        database_path,
        "show me the distinct label breakdown",
        catalog_tables=[
            CatalogTable(
                table_fqn="svc.db.main.accounts",
                service_name="svc",
                database_name="db",
                schema_name="main",
                table_name="accounts",
                sql_identifier="accounts",
                columns=[
                    CatalogColumn(
                        column_fqn="svc.db.main.accounts.account_id",
                        column_name="account_id",
                        data_type="integer",
                        is_primary_key=True,
                    ),
                    CatalogColumn(
                        column_fqn="svc.db.main.accounts.label",
                        column_name="label",
                        data_type="text",
                    ),
                ],
                primary_key_column_names=["account_id"],
            )
        ],
        budget=ValueGroundingBudget(max_enumerated_domain_values=5),
    )

    assert result.bindings == []


def test_probe_count_stays_within_the_configured_ceiling(tmp_path: Path) -> None:
    database_path = _build_accounts_database(tmp_path)
    budget = ValueGroundingBudget(max_value_columns=2)

    result = _ground(database_path, "enterprise accounts in the Northern region", budget=budget)

    assert result.diagnostics.probe_count <= budget.max_probes_per_request
    assert result.diagnostics.probed_column_count <= budget.max_value_columns


def test_join_and_key_columns_are_not_probed(tmp_path: Path) -> None:
    """Keys identify rows rather than categorise them, so probing them is waste."""
    database_path = _build_accounts_database(tmp_path)
    relationships = [
        CatalogForeignKey(
            from_table_fqn="svc.db.main.accounts",
            from_column_names=["region_id"],
            to_table_fqn="svc.db.main.regions",
            to_column_names=["region_id"],
        )
    ]

    result = _ground(
        database_path,
        "enterprise accounts by region_id and account_id",
        relationships=relationships,
    )

    assert all(b.column_name not in {"account_id", "region_id"} for b in result.bindings)


def test_probe_failure_degrades_to_no_bindings(tmp_path: Path) -> None:
    """A broken probe must not fail the pipeline; evidence is always optional."""
    database_path = _build_accounts_database(tmp_path)
    tables = _build_catalog_tables(accounts_table_name="table_that_does_not_exist")

    result = _ground(database_path, "enterprise accounts", catalog_tables=tables)

    assert result.bindings == []
    assert result.diagnostics.error_messages


@pytest.mark.parametrize("tier_tag", ["PII", "sensitive", "Confidential", "pci"])
def test_columns_tagged_sensitive_are_never_probed(tmp_path: Path, tier_tag: str) -> None:
    database_path = _build_accounts_database(tmp_path)
    tables = _build_catalog_tables(tier_tags=[tier_tag])

    result = _ground(database_path, "How many enterprise accounts?", catalog_tables=tables)

    assert all(b.column_name != "tier" for b in result.bindings)
