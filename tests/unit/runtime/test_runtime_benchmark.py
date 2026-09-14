"""Benchmark harness test executing a suite of scenarios through TextToSqlRuntime."""

from pathlib import Path

import pytest

from t2s.contracts import QueryRequest
from t2s.evaluation import RuntimeEvaluationCollector, RuntimeEvaluationResult
from t2s.runtime import RuntimeStatus
from t2s.security import AuthorizedSqlResource, UserIdentity
from tests.integration.runtime.test_text_to_sql_runtime import (
    _build_runtime,
    _customers_catalog_table,
    _secret_payroll_catalog_table,
    _setup_sqlite_db,
)


@pytest.mark.anyio
async def test_runtime_benchmark_suite_execution(tmp_path: Path) -> None:
    """Execute a representative benchmark suite and verify runtime metrics."""
    db_path = tmp_path / "bench.db"
    _setup_sqlite_db(db_path)
    cust = _customers_catalog_table()
    secret = _secret_payroll_catalog_table()

    collector = RuntimeEvaluationCollector()

    # Case 1: Clean successful execution
    runtime1, exec1, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT id, name FROM customers",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": ["customers.id", "customers.name"],
            "expected_columns": ["id", "name"],
            "assumptions": [],
            "unresolved": [],
        },
    )
    res1 = await runtime1.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="bench-case-1",
    )
    collector.add_result(res1, executor_calls=exec1.call_count)

    # Case 2: Unsafe SQL (DELETE) -> Safety rejection
    runtime2, exec2, _ = _build_runtime(
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
    res2 = await runtime2.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="bench-case-2",
    )
    collector.add_result(res2, executor_calls=exec2.call_count)

    # Case 3: Unauthorized table access -> Access denial
    runtime3, exec3, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust, secret],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT salary FROM secret_payroll",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": ["salary"],
            "expected_columns": ["salary"],
            "assumptions": [],
            "unresolved": [],
        },
    )
    res3 = await runtime3.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="bench-case-3",
    )
    collector.add_result(res3, executor_calls=exec3.call_count)

    # Case 4: Execution failure (Bad column)
    runtime4, exec4, _ = _build_runtime(
        database_path=db_path,
        catalog_tables=[cust],
        authorized_resources=[
            AuthorizedSqlResource(catalog_fqn=cust.table_fqn, sql_identifier="customers")
        ],
        solver_content_fn=lambda: {
            "sql": "SELECT non_existent FROM customers",
            "dialect": "sqlite",
            "referenced_tables": ["customers"],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
    )
    res4 = await runtime4.execute_query_pipeline(
        query_request=QueryRequest(question="List customers"),
        user_identity=UserIdentity(user_id="analyst"),
        run_id="bench-case-4",
    )
    collector.add_result(res4, executor_calls=exec4.call_count)

    metrics = collector.compute_metrics()

    assert isinstance(metrics, RuntimeEvaluationResult)
    assert metrics.case_count == 4
    assert metrics.completed_count == 1
    assert metrics.safety_rejected_count == 1
    assert metrics.access_denied_count == 1
    assert metrics.execution_failed_count == 1
    # 2 calls: Case 1 (success) + Case 4 (driver error), zero for cases 2 and 3
    assert metrics.total_executor_calls == 2
    assert metrics.average_runtime_latency_ms >= 0.0
    assert res1.status == RuntimeStatus.COMPLETED
    assert res2.status == RuntimeStatus.SAFETY_REJECTED
    assert res3.status == RuntimeStatus.ACCESS_DENIED
    assert res4.status == RuntimeStatus.EXECUTION_FAILED
