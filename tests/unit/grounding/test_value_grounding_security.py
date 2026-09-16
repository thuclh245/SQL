"""Security properties of value grounding.

Value probing reads real column contents, so it is held to the same boundaries as
query execution: read-only, parameterized, authorization-scoped and bounded.
"""

import sqlite3
from pathlib import Path

import pytest

from t2s.catalog import CatalogColumn, CatalogTable
from t2s.grounding.value_grounding import (
    SqliteValueProbe,
    ValueGrounder,
    ValueGroundingBudget,
    ValueProbeColumn,
    ValueProbeRequest,
)
from t2s.grounding.value_grounding.sqlite_value_probe import quote_sqlite_identifier


def _build_database(directory: Path) -> Path:
    database_path = directory / "secured.sqlite"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, tier TEXT);
        CREATE TABLE restricted_ledger (entry_id INTEGER PRIMARY KEY, tier TEXT);
        """
    )
    connection.execute("INSERT INTO accounts VALUES (1, 'enterprise')")
    connection.execute("INSERT INTO restricted_ledger VALUES (1, 'enterprise')")
    connection.commit()
    connection.close()
    return database_path


def _accounts_catalog() -> list[CatalogTable]:
    return [
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
    ]


def _probe_column(table: str = "accounts", column: str = "tier") -> ValueProbeColumn:
    return ValueProbeColumn(
        table_fqn=f"svc.db.main.{table}",
        sql_identifier=table,
        column_name=column,
        data_type="text",
    )


def test_probe_cannot_write_through_a_mutating_term(tmp_path: Path) -> None:
    """Terms are bound as parameters, so SQL syntax inside one stays inert."""
    database_path = _build_database(tmp_path)
    probe = SqliteValueProbe(database_path)

    outcome = probe.probe_matching_values(
        ValueProbeRequest(
            column=_probe_column(),
            match_terms=("enterprise'); DELETE FROM accounts; --",),
            max_values=5,
        )
    )

    assert outcome.observed_values == []
    connection = sqlite3.connect(database_path)
    assert connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
    connection.close()


def test_probe_connection_rejects_mutation_outright(tmp_path: Path) -> None:
    """The read-only connection is the backstop if a caller ever builds bad SQL."""
    database_path = _build_database(tmp_path)
    probe = SqliteValueProbe(database_path)

    connection = probe._connect_read_only(
        ValueProbeRequest(column=_probe_column(), max_values=1)
    )
    try:
        for statement in (
            "UPDATE accounts SET tier = 'x'",
            "DELETE FROM accounts",
            "DROP TABLE accounts",
        ):
            with pytest.raises(sqlite3.DatabaseError):
                connection.execute(statement)
    finally:
        connection.close()


def test_unauthorized_table_is_never_probed(tmp_path: Path) -> None:
    """A table absent from the grounding context is never reachable by a probe."""
    database_path = _build_database(tmp_path)
    grounder = ValueGrounder(
        value_probe=SqliteValueProbe(database_path),
        budget=ValueGroundingBudget(),
    )

    result = grounder.ground_values(
        question="enterprise entries in the restricted_ledger",
        catalog_tables=_accounts_catalog(),
        selected_column_names_by_table_fqn={"svc.db.main.accounts": {"account_id", "tier"}},
    )

    assert all(b.table_fqn == "svc.db.main.accounts" for b in result.bindings)
    assert all("restricted_ledger" not in b.table_fqn for b in result.bindings)


def test_identifier_quoting_neutralises_embedded_quotes() -> None:
    assert quote_sqlite_identifier('weird"name') == '"weird""name"'
    assert quote_sqlite_identifier("main.accounts") == '"main"."accounts"'


def test_probe_error_message_does_not_leak_database_values(tmp_path: Path) -> None:
    """Diagnostics carry an exception type, never a message quoting a literal."""
    database_path = _build_database(tmp_path)
    probe = SqliteValueProbe(database_path)

    outcome = probe.probe_matching_values(
        ValueProbeRequest(
            column=_probe_column(table="missing_table"),
            match_terms=("enterprise",),
            max_values=5,
        )
    )

    assert outcome.error_message == "OperationalError"
    assert "enterprise" not in (outcome.error_message or "")


def test_returned_value_count_respects_the_budget(tmp_path: Path) -> None:
    database_path = tmp_path / "many.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, tier TEXT)")
    connection.executemany(
        "INSERT INTO accounts VALUES (?, ?)",
        [(i, f"tier_{i}") for i in range(50)],
    )
    connection.commit()
    connection.close()

    outcome = SqliteValueProbe(database_path).probe_column_domain(
        ValueProbeRequest(column=_probe_column(), max_values=4)
    )

    assert len(outcome.observed_values) == 4
    assert outcome.domain_truncated is True
