import sqlite3
from pathlib import Path

import pytest
from structlog.contextvars import bind_contextvars, clear_contextvars

from t2s.contracts import GenerationTrace, SqlCandidate
from t2s.database import QueryAuditEvent, QueryExecutionPolicy, SecureQueryExecutor
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.errors import (
    QueryExecutionError,
    QueryExecutionTimeoutError,
    SqlExplainError,
    UnauthorizedDataAccessError,
    UnsafeSqlError,
)
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.verification import SqlAccessValidator, SqlAstParser, SqlSafetyValidator


class StaticAccessPolicy:
    def __init__(self, authorized_resources: list[AuthorizedSqlResource]) -> None:
        self.authorized_resources = authorized_resources

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return self.authorized_resources


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.audit_events: list[QueryAuditEvent] = []

    def record_query_audit_event(self, audit_event: QueryAuditEvent) -> None:
        self.audit_events.append(audit_event)


def create_sql_candidate(sql: str) -> SqlCandidate:
    return SqlCandidate(
        sql=sql,
        dialect="sqlite",
        referenced_tables=["model supplied table should not be trusted"],
        referenced_columns=[],
        expected_columns=[],
        generation_trace=GenerationTrace(
            run_id="run-1",
            model_name="fixture",
            prompt_version="test",
        ),
    )


def create_sqlite_database(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT)")
    connection.execute("CREATE TABLE secret_payroll(id INTEGER PRIMARY KEY, salary INTEGER)")
    connection.executemany(
        "INSERT INTO customers(id, name) VALUES (?, ?)",
        [(1, "Ada"), (2, "Grace"), (3, "Katherine")],
    )
    connection.execute("INSERT INTO secret_payroll(id, salary) VALUES (1, 1000000)")
    connection.commit()
    connection.close()


def create_secure_query_executor(
    database_path: Path,
    audit_sink: InMemoryAuditSink,
    maximum_result_rows: int = 1000,
) -> SecureQueryExecutor:
    authorization_service = AuthorizationService(
        StaticAccessPolicy(
            [
                AuthorizedSqlResource(
                    catalog_fqn="warehouse.main.customers",
                    sql_identifier="customers",
                )
            ]
        )
    )
    return SecureQueryExecutor(
        sql_ast_parser=SqlAstParser(),
        sql_safety_validator=SqlSafetyValidator(),
        sql_access_validator=SqlAccessValidator(authorization_service),
        query_executor=SqliteReadOnlyQueryExecutor(database_path),
        query_audit_sink=audit_sink,
        execution_policy=QueryExecutionPolicy(maximum_result_rows=maximum_result_rows),
    )


def test_safe_select_can_be_explained_and_executed(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    audit_sink = InMemoryAuditSink()
    secure_query_executor = create_secure_query_executor(database_path, audit_sink)
    user_identity = UserIdentity(user_id="analyst")

    explain_result = secure_query_executor.explain_sql_candidate(
        user_identity=user_identity,
        sql_candidate=create_sql_candidate("SELECT id, name FROM customers ORDER BY id"),
    )
    execution_result = secure_query_executor.execute_sql_candidate(
        user_identity=user_identity,
        sql_candidate=create_sql_candidate("SELECT id, name FROM customers ORDER BY id"),
    )

    assert "SCAN customers" in explain_result.plan_text
    assert execution_result.row_count == 3
    assert execution_result.rows[0] == {"id": 1, "name": "Ada"}
    assert [audit_event.outcome for audit_event in audit_sink.audit_events] == [
        "succeeded",
        "succeeded",
    ]


def test_unsafe_sql_is_blocked_before_database_execution(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    audit_sink = InMemoryAuditSink()
    secure_query_executor = create_secure_query_executor(database_path, audit_sink)

    with pytest.raises(UnsafeSqlError):
        secure_query_executor.execute_sql_candidate(
            user_identity=UserIdentity(user_id="analyst"),
            sql_candidate=create_sql_candidate("DROP TABLE customers"),
        )

    assert audit_sink.audit_events[-1].outcome == "blocked"


def test_unauthorized_table_is_blocked_from_ast_not_model_references(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    audit_sink = InMemoryAuditSink()
    secure_query_executor = create_secure_query_executor(database_path, audit_sink)

    with pytest.raises(UnauthorizedDataAccessError):
        secure_query_executor.execute_sql_candidate(
            user_identity=UserIdentity(user_id="analyst"),
            sql_candidate=create_sql_candidate("SELECT salary FROM secret_payroll"),
        )

    assert audit_sink.audit_events[-1].outcome == "blocked"


def test_cte_short_name_collision_does_not_bypass_authorization(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    audit_sink = InMemoryAuditSink()
    secure_query_executor = create_secure_query_executor(database_path, audit_sink)

    with pytest.raises(UnauthorizedDataAccessError):
        secure_query_executor.execute_sql_candidate(
            user_identity=UserIdentity(user_id="analyst"),
            sql_candidate=create_sql_candidate(
                """
                WITH secret_payroll AS (
                    SELECT 1 AS dummy
                )
                SELECT id, salary
                FROM main.secret_payroll
                """
            ),
        )

    assert audit_sink.audit_events[-1].outcome == "blocked"


def test_result_row_cap_is_enforced_by_execution_policy(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    audit_sink = InMemoryAuditSink()
    secure_query_executor = create_secure_query_executor(
        database_path,
        audit_sink,
        maximum_result_rows=2,
    )

    execution_result = secure_query_executor.execute_sql_candidate(
        user_identity=UserIdentity(user_id="analyst"),
        sql_candidate=create_sql_candidate("SELECT id, name FROM customers ORDER BY id"),
    )

    assert execution_result.row_count == 2
    assert execution_result.has_more_rows is True


def test_read_only_database_connection_blocks_validator_bypass(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    query_executor = SqliteReadOnlyQueryExecutor(database_path)

    with pytest.raises(QueryExecutionError):
        query_executor.execute_read_only_query(
            "CREATE TABLE bypassed(id INTEGER)",
            QueryExecutionPolicy(),
        )


def test_sqlite_executor_enforces_statement_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    query_executor = SqliteReadOnlyQueryExecutor(database_path)
    monotonic_values = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(
        "t2s.database.sqlite_read_only_query_executor.time.monotonic",
        lambda: next(monotonic_values, 2.0),
    )

    with pytest.raises(QueryExecutionTimeoutError):
        query_executor.execute_read_only_query(
            """
            WITH RECURSIVE counter(value) AS (
                SELECT 1
                UNION ALL
                SELECT value + 1 FROM counter WHERE value < 100000000
            )
            SELECT sum(value) FROM counter
            """,
            QueryExecutionPolicy(statement_timeout_seconds=1),
        )


def test_driver_execution_error_is_normalized_and_audited_as_failed(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    audit_sink = InMemoryAuditSink()
    secure_query_executor = create_secure_query_executor(database_path, audit_sink)

    with pytest.raises(QueryExecutionError) as exc_info:
        secure_query_executor.execute_sql_candidate(
            user_identity=UserIdentity(user_id="analyst"),
            sql_candidate=create_sql_candidate("SELECT missing_column FROM customers"),
        )

    assert isinstance(exc_info.value.__cause__, sqlite3.DatabaseError)
    assert audit_sink.audit_events[-1].outcome == "failed"


def test_audit_event_preserves_correlation_identifiers(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    audit_sink = InMemoryAuditSink()
    secure_query_executor = create_secure_query_executor(database_path, audit_sink)
    clear_contextvars()
    bind_contextvars(request_id="request-1", trace_id="trace-1", run_id="run-context")
    try:
        secure_query_executor.execute_sql_candidate(
            user_identity=UserIdentity(user_id="analyst"),
            sql_candidate=create_sql_candidate("SELECT id FROM customers"),
        )
    finally:
        clear_contextvars()

    audit_event = audit_sink.audit_events[-1]
    assert audit_event.request_id == "request-1"
    assert audit_event.trace_id == "trace-1"
    assert audit_event.run_id == "run-context"


def test_driver_explain_error_is_normalized(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.db"
    query_executor = SqliteReadOnlyQueryExecutor(database_path)

    with pytest.raises(SqlExplainError) as exc_info:
        query_executor.explain_query("SELECT * FROM customers", QueryExecutionPolicy())

    assert isinstance(exc_info.value.__cause__, sqlite3.DatabaseError)


def test_sqlite_connection_closes_after_success_and_driver_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "warehouse.db"
    create_sqlite_database(database_path)
    original_connect = sqlite3.connect
    proxied_connections: list[ClosingConnectionProxy] = []

    def connect_with_proxy(*args: object, **kwargs: object) -> "ClosingConnectionProxy":
        connection = original_connect(*args, **kwargs)
        proxy = ClosingConnectionProxy(connection)
        proxied_connections.append(proxy)
        return proxy

    monkeypatch.setattr(
        "t2s.database.sqlite_read_only_query_executor.sqlite3.connect",
        connect_with_proxy,
    )
    query_executor = SqliteReadOnlyQueryExecutor(database_path)

    query_executor.execute_read_only_query("SELECT id FROM customers", QueryExecutionPolicy())
    with pytest.raises(QueryExecutionError):
        query_executor.execute_read_only_query(
            "SELECT missing_column FROM customers",
            QueryExecutionPolicy(),
        )
    query_executor.explain_query("SELECT id FROM customers", QueryExecutionPolicy())

    assert [connection_proxy.is_closed for connection_proxy in proxied_connections] == [
        True,
        True,
        True,
    ]


class ClosingConnectionProxy:
    def __init__(self, connection: sqlite3.Connection) -> None:
        object.__setattr__(self, "connection", connection)
        object.__setattr__(self, "is_closed", False)

    def __getattr__(self, name: str) -> object:
        return getattr(self.connection, name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in {"connection", "is_closed"}:
            object.__setattr__(self, name, value)
            return
        setattr(self.connection, name, value)

    def close(self) -> None:
        object.__setattr__(self, "is_closed", True)
        self.connection.close()
