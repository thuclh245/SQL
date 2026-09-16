"""Unit tests for DiagnosticProbeRunner."""

import sqlite3
import tempfile
from pathlib import Path

from t2s.database import SqliteReadOnlyQueryExecutor
from t2s.security import UserIdentity
from t2s.verification.diagnostic_probes import DiagnosticProbeRunner
from t2s.verification.sql_ast_parser import SqlAstParser
from t2s.verification.sql_safety_validator import SqlSafetyValidator


def test_diagnostic_probe_detects_filter_grounding_failure() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = Path(tmp.name)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE sample_orders (id INT, amount NUMERIC, status TEXT)")
        conn.execute("INSERT INTO sample_orders VALUES (1, 100.5, 'completed')")
        conn.execute("INSERT INTO sample_orders VALUES (2, 250.0, 'completed')")
        conn.commit()
        conn.close()

        executor = SqliteReadOnlyQueryExecutor(db_path)
        runner = DiagnosticProbeRunner(
            query_executor=executor,
            sql_ast_parser=SqlAstParser(),
            sql_safety_validator=SqlSafetyValidator(),
        )
        user = UserIdentity(user_id="analyst_1", roles=("analyst",), tenant_id="tenant_a")

        candidate_sql = "SELECT amount FROM sample_orders WHERE status = 'cancelled'"
        outcome = runner.probe_suspicious_result(
            candidate_sql=candidate_sql,
            dialect="sqlite",
            user_identity=user,
            recommended_probe="POPULATION_COUNT_PROBE",
        )

        assert outcome.probe_executed is True
        assert outcome.probe_type == "POPULATION_COUNT_PROBE"
        assert outcome.failure_code == "FILTER_GROUNDING_FAILURE"
        assert outcome.details is not None
        assert outcome.details["count"] == 2


def test_diagnostic_probe_detects_empty_base_population() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = Path(tmp.name)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE empty_inventory (sku TEXT, qty INT)")
        conn.commit()
        conn.close()

        executor = SqliteReadOnlyQueryExecutor(db_path)
        runner = DiagnosticProbeRunner(
            query_executor=executor,
            sql_ast_parser=SqlAstParser(),
            sql_safety_validator=SqlSafetyValidator(),
        )
        user = UserIdentity(user_id="analyst_1", roles=("analyst",), tenant_id="tenant_a")

        candidate_sql = "SELECT qty FROM empty_inventory WHERE sku = 'ITEM_1'"
        outcome = runner.probe_suspicious_result(
            candidate_sql=candidate_sql,
            dialect="sqlite",
            user_identity=user,
            recommended_probe="POPULATION_COUNT_PROBE",
        )

        assert outcome.probe_executed is True
        assert outcome.failure_code == "BASE_POPULATION_EMPTY"
        assert outcome.details is not None
        assert outcome.details["count"] == 0
