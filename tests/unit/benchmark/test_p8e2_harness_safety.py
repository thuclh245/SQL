import sqlite3

import pytest

from scripts.run_p8e2_microtest import validate_candidate_sql_for_benchmark
from t2s.benchmark.scoring import execute_evaluation_sql
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity


class StaticPolicy:
    def __init__(self, resources: list[AuthorizedSqlResource]) -> None:
        self.resources = resources

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return list(self.resources)


def build_auth(*tables: str) -> AuthorizationService:
    return AuthorizationService(
        StaticPolicy(
            [
                AuthorizedSqlResource(catalog_fqn=f"test.main.{table}", sql_identifier=table)
                for table in tables
            ]
        )
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM allowed; DROP TABLE allowed",
        "DELETE FROM allowed",
        "CREATE TABLE leaked(id int)",
    ],
)
def test_p8e2_harness_rejects_multi_statement_dml_and_ddl(sql: str) -> None:
    ok, reason = validate_candidate_sql_for_benchmark(
        sql,
        build_auth("allowed"),
        UserIdentity(user_id="tester", roles=["analyst"]),
    )

    assert not ok
    assert reason != "SAFE"


def test_p8e2_harness_rejects_unauthorized_table() -> None:
    ok, reason = validate_candidate_sql_for_benchmark(
        "SELECT id FROM secret",
        build_auth("allowed"),
        UserIdentity(user_id="tester", roles=["analyst"]),
    )

    assert not ok
    assert "UnauthorizedDataAccessError" in reason


def test_p8e2_harness_allows_valid_authorized_select() -> None:
    ok, reason = validate_candidate_sql_for_benchmark(
        "SELECT id FROM allowed",
        build_auth("allowed"),
        UserIdentity(user_id="tester", roles=["analyst"]),
    )

    assert ok
    assert reason == "SAFE"


def test_evaluation_executor_enforces_read_only_sqlite_connection(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE allowed(id integer)")
        conn.execute("INSERT INTO allowed VALUES (1)")

    result = execute_evaluation_sql("CREATE TABLE blocked(id integer)", db_path)

    assert not result.ok
    assert (
        "readonly" in (result.error or "").lower()
        or "not authorized" in (result.error or "").lower()
    )
