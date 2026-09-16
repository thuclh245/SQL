"""Readiness detection for the configured execution database."""

import sqlite3
from pathlib import Path

from t2s.database import DatabaseReadinessStatus, SqliteDatabaseReadinessInspector


def _write_database(directory: Path, *, with_rows: bool, with_relations: bool = True) -> Path:
    database_path = directory / "execution.sqlite"
    connection = sqlite3.connect(database_path)
    if with_relations:
        connection.execute("CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, tier TEXT)")
        connection.execute("CREATE TABLE ledger (entry_id INTEGER PRIMARY KEY)")
        if with_rows:
            connection.execute("INSERT INTO accounts VALUES (1, 'enterprise')")
    else:
        # A file that is valid SQLite but exposes nothing queryable.
        connection.execute("CREATE TABLE placeholder (id INTEGER)")
        connection.execute("DROP TABLE placeholder")
    connection.commit()
    connection.close()
    return database_path


def test_populated_database_is_ready(tmp_path: Path) -> None:
    report = SqliteDatabaseReadinessInspector(
        _write_database(tmp_path, with_rows=True)
    ).inspect_readiness()

    assert report.status == DatabaseReadinessStatus.READY
    assert report.is_ready is True


def test_schema_only_database_is_detected(tmp_path: Path) -> None:
    """The failure this guard exists for: correct schema, no rows anywhere."""
    report = SqliteDatabaseReadinessInspector(
        _write_database(tmp_path, with_rows=False)
    ).inspect_readiness()

    assert report.status == DatabaseReadinessStatus.NO_DATA_ROWS
    assert report.is_ready is False
    assert report.relation_count == 2
    assert report.non_empty_relation_count == 0


def test_one_populated_relation_is_enough(tmp_path: Path) -> None:
    """An individual empty table is normal in production and must not fail the check."""
    report = SqliteDatabaseReadinessInspector(
        _write_database(tmp_path, with_rows=True)
    ).inspect_readiness()

    assert report.status == DatabaseReadinessStatus.READY


def test_database_without_user_relations_is_detected(tmp_path: Path) -> None:
    report = SqliteDatabaseReadinessInspector(
        _write_database(tmp_path, with_rows=False, with_relations=False)
    ).inspect_readiness()

    assert report.status == DatabaseReadinessStatus.NO_USER_RELATIONS


def test_missing_database_file_is_unreachable(tmp_path: Path) -> None:
    report = SqliteDatabaseReadinessInspector(tmp_path / "absent.sqlite").inspect_readiness()

    assert report.status == DatabaseReadinessStatus.UNREACHABLE
    assert report.is_ready is False


def test_non_sqlite_file_is_unreachable(tmp_path: Path) -> None:
    corrupt_path = tmp_path / "not-a-database.sqlite"
    corrupt_path.write_text("this is not a database", encoding="utf-8")

    report = SqliteDatabaseReadinessInspector(corrupt_path).inspect_readiness()

    assert report.status == DatabaseReadinessStatus.UNREACHABLE
