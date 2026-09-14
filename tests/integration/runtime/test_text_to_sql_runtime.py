"""Integration tests for TextToSqlRuntime.

Covers all required scenarios A–J and negative security invariants.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from t2s.catalog import (
    CatalogColumn,
    CatalogForeignKey,
    CatalogSearchDocumentBuilder,
    CatalogTable,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.database import (
    QueryExecutionPolicy,
    QueryExecutionResult,
    QueryExecutorPort,
    QueryExplainResult,
)
from t2s.database.secure_query_executor import QueryAuditEvent
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.grounding import (
    GroundingBudget,
    GroundingContextBuilder,
    InMemorySchemaSearch,
    SchemaRetriever,
)
from t2s.orchestration import (
    AdaptiveOrchestrator,
    EscalationBudget,
    EscalationPolicy,
)
from t2s.runtime import RuntimeStatus, TextToSqlRuntime
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.solver.solver_response import StructuredChatResponse
from t2s.verification import SqlAccessValidator, SqlAstParser, SqlSafetyValidator


class StaticAccessPolicy:
    def __init__(self, authorized_resources: list[AuthorizedSqlResource]) -> None:
        self.authorized_resources = authorized_resources

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return self.authorized_resources


class CountingQueryExecutor:
    """Wraps QueryExecutorPort and counts invocation calls to prove fail-closed invariants."""

    def __init__(self, delegate: QueryExecutorPort) -> None:
        self.delegate = delegate
        self.call_count = 0

    def explain_query(
        self,
        sql: str,
        execution_policy: QueryExecutionPolicy,
    ) -> QueryExplainResult:
        self.call_count += 1
        return self.delegate.explain_query(sql, execution_policy)

    def execute_read_only_query(
        self,
        sql: str,
        execution_policy: QueryExecutionPolicy,
    ) -> QueryExecutionResult:
        self.call_count += 1
        return self.delegate.execute_read_only_query(sql, execution_policy)


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.audit_events: list[QueryAuditEvent] = []

    def record_query_audit_event(self, audit_event: QueryAuditEvent) -> None:
        self.audit_events.append(audit_event)


class FakeStructuredChatClient:
    def __init__(self, response_generator: Callable[[], dict[str, Any]]) -> None:
        self.response_generator = response_generator
        self.call_count = 0

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        self.call_count += 1
        return StructuredChatResponse(
            content=self.response_generator(),
            model_name=model_name,
            elapsed_ms=15,
            prompt_tokens=150,
            output_tokens=60,
        )


def _setup_sqlite_db(database_path: Path) -> None:
    conn = sqlite3.connect(database_path)
    conn.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, segment TEXT)")
    conn.execute(
        "CREATE TABLE orders(order_id INTEGER PRIMARY KEY, customer_id INTEGER, net_revenue REAL)"
    )
    conn.execute("CREATE TABLE secret_payroll(id INTEGER PRIMARY KEY, salary INTEGER)")
    conn.executemany(
        "INSERT INTO customers(id, name, segment) VALUES (?, ?, ?)",
        [(1, "Ada", "tech"), (2, "Grace", "tech"), (3, "Katherine", "science")],
    )
    conn.executemany(
        "INSERT INTO orders(order_id, customer_id, net_revenue) VALUES (?, ?, ?)",
        [(101, 1, 150.0), (102, 1, 250.0), (103, 2, 500.0)],
    )
    conn.execute("INSERT INTO secret_payroll(id, salary) VALUES (1, 1000000)")
    conn.commit()
    conn.close()


def _build_runtime(
    database_path: Path,
    catalog_tables: list[CatalogTable],
    authorized_resources: list[AuthorizedSqlResource],
    solver_content_fn: Callable[[], dict[str, Any]],
    execution_policy: QueryExecutionPolicy | None = None,
    grounding_budget: GroundingBudget | None = None,
    escalation_budget: EscalationBudget | None = None,
) -> tuple[TextToSqlRuntime, CountingQueryExecutor, InMemoryAuditSink]:
    catalog = InMemoryCatalog()
    catalog.upsert_tables(catalog_tables)

    doc_builder = CatalogSearchDocumentBuilder()
    docs = [
        doc
        for table in catalog_tables
        for doc in doc_builder.build_search_documents(table)
    ]
    schema_retriever = SchemaRetriever(InMemorySchemaSearch(docs))
    auth_service = AuthorizationService(StaticAccessPolicy(authorized_resources))

    grounding_builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=schema_retriever,
        authorization_service=auth_service,
        grounding_budget=grounding_budget,
    )

    fake_client = FakeStructuredChatClient(solver_content_fn)
    solver = DirectSqlSolver(
        chat_client=fake_client,
        prompt_builder=DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql")),
        model_name="test-model",
    )

    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=grounding_builder,
        solver=solver,
        escalation_policy=EscalationPolicy(),
        escalation_budget=escalation_budget,
    )

    base_executor = SqliteReadOnlyQueryExecutor(database_path)
    counting_executor = CountingQueryExecutor(base_executor)
    audit_sink = InMemoryAuditSink()

    runtime = TextToSqlRuntime(
        adaptive_orchestrator=orchestrator,
        sql_ast_parser=SqlAstParser(),
        sql_safety_validator=SqlSafetyValidator(),
        sql_access_validator=SqlAccessValidator(auth_service),
        query_executor=counting_executor,
        execution_policy=execution_policy or QueryExecutionPolicy(),
        query_audit_sink=audit_sink,
        default_dialect="sqlite",
    )
    return runtime, counting_executor, audit_sink


def _customers_catalog_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="warehouse.main.customers",
        service_name="sqlite",
        database_name="warehouse",
        schema_name="main",
        table_name="customers",
        sql_identifier="customers",
        description="Customer dimensions",
        columns=[
            CatalogColumn(
                column_fqn="warehouse.main.customers.id",
                column_name="id",
                data_type="INTEGER",
                is_primary_key=True,
            ),
            CatalogColumn(
                column_fqn="warehouse.main.customers.name",
                column_name="name",
                data_type="TEXT",
            ),
            CatalogColumn(
                column_fqn="warehouse.main.customers.segment",
                column_name="segment",
                data_type="TEXT",
            ),
        ],
        primary_key_column_names=["id"],
    )


def _orders_catalog_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="warehouse.main.orders",
        service_name="sqlite",
        database_name="warehouse",
        schema_name="main",
        table_name="orders",
        sql_identifier="orders",
        description="Customer orders",
        columns=[
            CatalogColumn(
                column_fqn="warehouse.main.orders.order_id",
                column_name="order_id",
                data_type="INTEGER",
                is_primary_key=True,
            ),
            CatalogColumn(
                column_fqn="warehouse.main.orders.customer_id",
                column_name="customer_id",
                data_type="INTEGER",
            ),
            CatalogColumn(
                column_fqn="warehouse.main.orders.net_revenue",
                column_name="net_revenue",
                data_type="REAL",
            ),
        ],
        primary_key_column_names=["order_id"],
        foreign_keys=[
            CatalogForeignKey(
                from_table_fqn="warehouse.main.orders",
                from_column_names=["customer_id"],
                to_table_fqn="warehouse.main.customers",
                to_column_names=["id"],
            )
        ],
    )


def _secret_payroll_catalog_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="warehouse.main.secret_payroll",
        service_name="sqlite",
        database_name="warehouse",
        schema_name="main",
        table_name="secret_payroll",
        sql_identifier="secret_payroll",
        description="Secret payroll salaries",
        columns=[
            CatalogColumn(
                column_fqn="warehouse.main.secret_payroll.id",
                column_name="id",
                data_type="INTEGER",
            ),
            CatalogColumn(
                column_fqn="warehouse.main.secret_payroll.salary",
                column_name="salary",
                data_type="INTEGER",
            ),
        ],
    )


# =============================================================================
# Case A: Successful single-table request
# =============================================================================


@pytest.mark.anyio
async def test_case_a_successful_single_table_request(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()

    runtime, executor, audit = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT id, name FROM customers ORDER BY id",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": ["customers.id", "customers.name"],
            "expected_columns": ["id", "name"],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-a",
    )

    assert result.status == RuntimeStatus.COMPLETED
    assert result.row_count == 3
    assert result.rows[0]["name"] == "Ada"
    assert executor.call_count == 1
    assert result.trace.safety_check_passed is True
    assert result.trace.access_check_passed is True
    assert result.trace.execution_passed is True
    assert audit.audit_events[-1].outcome == "succeeded"


# =============================================================================
# Case B: Successful join query with composite/relationship context
# =============================================================================


@pytest.mark.anyio
async def test_case_b_successful_join_request(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()
    orders = _orders_catalog_table()

    runtime, executor, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust, orders],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers"),
            AuthorizedSqlResource(catalog_fqn=orders.table_fqn, sql_identifier="orders"),
        ],
        solver_content_fn=lambda: {
            "sql": (
                "SELECT c.name, SUM(o.net_revenue) AS total_rev "
                "FROM customers AS c JOIN orders AS o ON c.id = o.customer_id "
                "GROUP BY c.name ORDER BY total_rev DESC"
            ),
            "dialect": "sqlite",
            "referenced_tables": ["customers", "orders"],
            "referenced_columns": ["customers.name", "orders.net_revenue"],
            "expected_columns": ["name", "total_rev"],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="Total revenue per customer"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-b",
    )

    assert result.status == RuntimeStatus.COMPLETED
    assert result.row_count == 2
    assert executor.call_count == 1
    assert "customers" in result.trace.ast_referenced_tables
    assert "orders" in result.trace.ast_referenced_tables


# =============================================================================
# Case C: Unsafe generated SQL (DELETE statement)
# =============================================================================


@pytest.mark.anyio
async def test_case_c_unsafe_generated_sql_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()

    runtime, executor, audit = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "DELETE FROM customers",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="Remove customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-c",
    )

    assert result.status == RuntimeStatus.SAFETY_REJECTED
    assert executor.call_count == 0  # CRITICAL: DB executor was never called
    assert result.trace.safety_check_passed is False
    assert result.trace.execution_passed is False
    assert audit.audit_events[-1].outcome == "blocked"


# =============================================================================
# Case D: Hallucinated unauthorized table
# =============================================================================


@pytest.mark.anyio
async def test_case_d_unauthorized_table_access_denied(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()
    secret = _secret_payroll_catalog_table()

    runtime, executor, audit = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust, secret],
        # User is ONLY authorized for customers, NOT secret_payroll
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT salary FROM secret_payroll",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": ["customers.id"],
            "expected_columns": ["salary"],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-d",
    )

    assert result.status == RuntimeStatus.ACCESS_DENIED
    assert executor.call_count == 0  # CRITICAL: DB executor was never called
    assert result.trace.access_check_passed is False
    assert audit.audit_events[-1].outcome == "blocked"


# =============================================================================
# Case E: P5 Unresolved (Missing SQL Identifier in Catalog)
# =============================================================================


@pytest.mark.anyio
async def test_case_e_p5_unresolved_halts_without_execution(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    leads_table = CatalogTable(
        table_fqn="warehouse.main.leads",
        service_name="sqlite",
        database_name="warehouse",
        schema_name="main",
        table_name="leads",
        sql_identifier=None,  # No executable SQL identifier
        description="Marketing leads",
    )

    runtime, executor, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[leads_table],
        authorized_resources=[
            AuthorizedSqlResource(
                catalog_fqn=leads_table.table_fqn,
                sql_identifier="unresolved.placeholder",
            )
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT 1",
            "dialect": "sqlite",
            "referenced_tables": [],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List leads"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-e",
    )

    assert result.status == RuntimeStatus.UNRESOLVED
    assert executor.call_count == 0  # CRITICAL: DB executor was never called
    assert result.sql is None


# =============================================================================
# Case F: Solver Failure
# =============================================================================


@pytest.mark.anyio
async def test_case_f_solver_failure_halts_without_execution(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()

    # Solver returns empty SQL which causes MalformedSolverOutputError in P4
    runtime, executor, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": " ",
            "dialect": "sqlite",
            "referenced_tables": [],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-f",
    )

    # Empty SQL causes solver failure, which P5 handles and runtime marks as GENERATION_FAILED
    assert result.status == RuntimeStatus.GENERATION_FAILED
    assert executor.call_count == 0  # CRITICAL: DB executor was never called


# =============================================================================
# Case G: Multi-statement injection
# =============================================================================


@pytest.mark.anyio
async def test_case_g_multi_statement_injection_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()

    runtime, executor, audit = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT * FROM customers; DROP TABLE customers",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-g",
    )

    assert result.status == RuntimeStatus.SAFETY_REJECTED
    assert executor.call_count == 0  # CRITICAL: DB executor was never called
    assert audit.audit_events[-1].outcome == "blocked"


# =============================================================================
# Case H: Execution error / statement timeout
# =============================================================================


@pytest.mark.anyio
async def test_case_h_execution_error_fails_structured_without_retry(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()

    # Query refers to non-existent column in DB
    runtime, executor, audit = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT non_existent_column FROM customers",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-h",
    )

    assert result.status == RuntimeStatus.EXECUTION_FAILED
    assert executor.call_count == 1  # Called once, failed, NO RETRY
    assert audit.audit_events[-1].outcome == "failed"


# =============================================================================
# Case I: Result row limit enforced
# =============================================================================


@pytest.mark.anyio
async def test_case_i_result_row_limit_enforced(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()

    runtime, _, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT id, name FROM customers ORDER BY id",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
        execution_policy=QueryExecutionPolicy(maximum_result_rows=2),
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-i",
    )

    assert result.status == RuntimeStatus.COMPLETED
    assert result.row_count == 2
    assert result.has_more_rows is True


# =============================================================================
# Case J: Identity domain separation (table_fqn != sql_identifier)
# =============================================================================


@pytest.mark.anyio
async def test_case_j_identity_domains_separated(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()

    runtime, executor, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        # Authorized resource has distinct FQN and sql_identifier
        authorized_resources=[
            AuthorizedSqlResource(
                catalog_fqn="warehouse.main.customers",
                sql_identifier="customers",
            )
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT id FROM customers",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": ["id"],
            "expected_columns": ["id"],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-case-j",
    )

    assert result.status == RuntimeStatus.COMPLETED
    assert executor.call_count == 1
    assert result.trace.ast_referenced_tables == ["customers"]


# =============================================================================
# Critical Negative Security Test: Model claims referenced_tables cannot bypass AST
# =============================================================================


@pytest.mark.anyio
async def test_critical_negative_model_reported_tables_cannot_bypass_ast(
    tmp_path: Path,
) -> None:
    """Model deceptively reports referenced_tables=['customers'], but SQL accesses secret_payroll.

    AST parser MUST extract 'secret_payroll' and block access, ignoring model claims.
    """
    db_path = tmp_path / "test.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()
    secret = _secret_payroll_catalog_table()

    runtime, executor, audit = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust, secret],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT salary FROM secret_payroll",
            "dialect": "sqlite",
            # Model maliciously lies that it only referenced authorized 'customers' table
            "referenced_tables": ["customers"],
            "referenced_columns": ["customers.id"],
            "expected_columns": ["salary"],
            "assumptions": [],
            "unresolved": [],
        },
    )

    result = await runtime.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="run-spoof-test",
    )

    assert result.status == RuntimeStatus.ACCESS_DENIED
    assert executor.call_count == 0  # CRITICAL: DB executor was never called
    assert audit.audit_events[-1].outcome == "blocked"
