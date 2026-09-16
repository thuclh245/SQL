import json
import sqlite3
from pathlib import Path

import pytest

from t2s.bootstrap.runtime_factory import build_runtime_from_settings
from t2s.configuration import Settings
from t2s.database import PostgresReadOnlyQueryExecutor, SqliteReadOnlyQueryExecutor
from t2s.errors import ConfigurationError
from t2s.runtime import TextToSqlRuntime
from t2s.runtime.runtime_contracts import ValidatorMode
from t2s.security import UserIdentity


def _write_sqlite_database(directory: Path, *, with_rows: bool = True) -> Path:
    """Build a throwaway execution database.

    A row is inserted by default so the fixture passes the startup readiness
    guard; ``with_rows=False`` reproduces the schema-only case on purpose.
    """
    database_path = directory / "sales.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    if with_rows:
        connection.execute("INSERT INTO customers (id, name) VALUES (1, 'Acme')")
    connection.commit()
    connection.close()
    return database_path


def _write_catalog_tables(directory: Path) -> Path:
    catalog_path = directory / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "table_fqn": "sales.main.customers",
                    "service_name": "sales",
                    "database_name": "main",
                    "schema_name": "main",
                    "table_name": "customers",
                    "sql_identifier": "customers",
                    "sql_identifier_source": "explicit",
                    "columns": [
                        {
                            "column_fqn": "sales.main.customers.id",
                            "column_name": "id",
                            "data_type": "INTEGER",
                            "is_primary_key": True,
                        },
                        {
                            "column_fqn": "sales.main.customers.name",
                            "column_name": "name",
                            "data_type": "TEXT",
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return catalog_path


def test_unconfigured_runtime_settings_produce_no_runtime() -> None:
    assert build_runtime_from_settings(Settings(environment="test")) is None


def test_a_database_without_a_catalog_is_rejected(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_sqlite_database_path=_write_sqlite_database(tmp_path),
    )

    with pytest.raises(ConfigurationError, match="runtime_catalog_tables_path"):
        build_runtime_from_settings(settings)


def test_runtime_configuration_requires_a_solver_endpoint(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_sqlite_database_path=_write_sqlite_database(tmp_path),
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        vllm_base_url=None,
    )

    with pytest.raises(ConfigurationError, match="vllm_base_url"):
        build_runtime_from_settings(settings)


@pytest.mark.parametrize("dialect", ["clickhouse", "starrocks"])
def test_dialects_without_an_executor_fail_closed(dialect: str, tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_sqlite_database_path=_write_sqlite_database(tmp_path),
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        runtime_database_url="postgresql://readonly@localhost/warehouse",
        vllm_base_url="http://vllm.example/v1",
        runtime_default_dialect=dialect,
    )

    with pytest.raises(ConfigurationError, match=f"dialect '{dialect}'"):
        build_runtime_from_settings(settings)


def test_postgres_dialect_requires_a_database_url(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        vllm_base_url="http://vllm.example/v1",
        runtime_default_dialect="postgres",
    )

    with pytest.raises(ConfigurationError, match="runtime_database_url"):
        build_runtime_from_settings(settings)


def test_sqlite_dialect_requires_a_database_path(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        runtime_database_url="postgresql://readonly@localhost/warehouse",
        vllm_base_url="http://vllm.example/v1",
        runtime_default_dialect="sqlite",
    )

    with pytest.raises(ConfigurationError, match="runtime_sqlite_database_path"):
        build_runtime_from_settings(settings)


def test_postgres_dialect_builds_a_postgres_executor(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        runtime_database_url="postgresql://readonly@localhost/warehouse",
        runtime_database_connect_timeout_seconds=4,
        vllm_base_url="http://vllm.example/v1",
        runtime_default_dialect="postgres",
        # Wiring-only assertion: there is no PostgreSQL server to inspect here.
        runtime_require_populated_execution_database=False,
    )

    runtime = build_runtime_from_settings(settings)

    assert runtime is not None
    executor = runtime.query_executor
    assert isinstance(executor, PostgresReadOnlyQueryExecutor)
    assert executor.database_url == "postgresql://readonly@localhost/warehouse"
    assert executor.connect_timeout_seconds == 4
    assert runtime.default_dialect == "postgres"


def test_postgres_configuration_never_falls_back_to_a_present_sqlite_file(
    tmp_path: Path,
) -> None:
    """A sqlite file left in the config must not rescue a broken postgres setup."""
    settings = Settings(
        environment="test",
        runtime_sqlite_database_path=_write_sqlite_database(tmp_path),
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        vllm_base_url="http://vllm.example/v1",
        runtime_default_dialect="postgres",
    )

    with pytest.raises(ConfigurationError, match="runtime_database_url"):
        build_runtime_from_settings(settings)


def test_catalog_tables_file_must_contain_a_json_list(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"table_fqn": "sales.main.customers"}), encoding="utf-8")
    settings = Settings(
        environment="test",
        runtime_sqlite_database_path=_write_sqlite_database(tmp_path),
        runtime_catalog_tables_path=catalog_path,
        vllm_base_url="http://vllm.example/v1",
    )

    with pytest.raises(ConfigurationError, match="JSON list"):
        build_runtime_from_settings(settings)


def test_fully_configured_settings_build_a_wired_runtime(tmp_path: Path) -> None:
    database_path = _write_sqlite_database(tmp_path)
    settings = Settings(
        environment="test",
        runtime_sqlite_database_path=database_path,
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        vllm_base_url="http://vllm.example/v1",
        validator_mode="enforce",
        production_enforcement_authorized=True,
        database_max_result_rows=25,
    )

    runtime = build_runtime_from_settings(settings)

    assert isinstance(runtime, TextToSqlRuntime)
    assert isinstance(runtime.query_executor, SqliteReadOnlyQueryExecutor)
    assert runtime.default_dialect == "sqlite"
    assert runtime.validator_mode == ValidatorMode.ENFORCE
    assert runtime.execution_policy.maximum_result_rows == 25


def test_built_runtime_authorizes_every_catalog_table(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        runtime_sqlite_database_path=_write_sqlite_database(tmp_path),
        runtime_catalog_tables_path=_write_catalog_tables(tmp_path),
        vllm_base_url="http://vllm.example/v1",
    )

    runtime = build_runtime_from_settings(settings)

    assert runtime is not None
    authorization_service = runtime.sql_access_validator.authorization_service
    resources = authorization_service.access_policy.get_authorized_resources(
        UserIdentity(user_id="anyone")
    )
    assert [resource.sql_identifier for resource in resources] == ["customers"]
