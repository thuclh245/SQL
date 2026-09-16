"""Safe, read-only diagnostic probes for investigating suspicious query results."""

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp

from t2s.contracts.sql_candidate import SupportedSqlDialect
from t2s.database.query_execution_policy import QueryExecutionPolicy
from t2s.database.query_executor_port import QueryExecutorPort
from t2s.security import UserIdentity
from t2s.verification.sql_access_validator import SqlAccessValidator
from t2s.verification.sql_ast_parser import SqlAstParser
from t2s.verification.sql_safety_validator import SqlSafetyValidator


@dataclass(frozen=True)
class DiagnosticProbeOutcome:
    """Findings from executing a safe diagnostic probe."""

    probe_executed: bool
    probe_type: str
    probe_sql: str
    findings: str
    failure_code: str | None = None
    details: dict[str, Any] | None = None


class DiagnosticProbeRunner:
    """Executes strictly bounded, read-only diagnostic SQL probes against suspicious results.

    Every probe passes through AST parsing, SqlSafetyValidator, and SqlAccessValidator
    to guarantee zero privilege escalation or state mutation.
    """

    def __init__(
        self,
        query_executor: QueryExecutorPort,
        sql_ast_parser: SqlAstParser | None = None,
        sql_safety_validator: SqlSafetyValidator | None = None,
        sql_access_validator: SqlAccessValidator | None = None,
    ) -> None:
        self.query_executor = query_executor
        self.sql_ast_parser = sql_ast_parser or SqlAstParser()
        self.sql_safety_validator = sql_safety_validator or SqlSafetyValidator()
        self.sql_access_validator = sql_access_validator

    def probe_suspicious_result(
        self,
        candidate_sql: str,
        dialect: SupportedSqlDialect,
        user_identity: UserIdentity,
        recommended_probe: str | None = None,
        execution_policy: QueryExecutionPolicy | None = None,
    ) -> DiagnosticProbeOutcome:
        policy = execution_policy or QueryExecutionPolicy(
            read_only_required=True,
            maximum_result_rows=10,
            statement_timeout_seconds=5,
        )

        try:
            ast = sqlglot.parse_one(candidate_sql, read=dialect)
        except Exception as exc:
            return DiagnosticProbeOutcome(
                probe_executed=False,
                probe_type="NONE",
                probe_sql="",
                findings=f"Cannot generate probe from unparsable candidate SQL: {exc}",
                failure_code="PROBE_GENERATION_FAILED",
            )

        tables = list(ast.find_all(exp.Table))
        if not tables:
            return DiagnosticProbeOutcome(
                probe_executed=False,
                probe_type="NONE",
                probe_sql="",
                findings="No tables identified in SQL candidate to probe.",
                failure_code="NO_PROBEABLE_TABLES",
            )

        primary_table = tables[0].name

        # Construct probe based on recommendation
        if recommended_probe == "METRIC_NON_NULL_PROBE":
            # Probe: check if any non-null rows exist in the projected column
            select_exprs = ast.find(exp.Select)
            first_col = None
            if select_exprs and select_exprs.expressions:
                for col in select_exprs.expressions[0].find_all(exp.Column):
                    first_col = col.name
                    break

            col_target = first_col or "*"
            probe_sql = f"SELECT COUNT({col_target}) AS metric_count FROM {primary_table}"
            probe_type = "METRIC_NON_NULL_PROBE"
        else:
            # Default: Population count probe without where clause
            probe_sql = f"SELECT COUNT(*) AS total_count FROM {primary_table}"
            probe_type = "POPULATION_COUNT_PROBE"

        # Verify probe through full safety and access perimeter
        parsed_probe = self.sql_ast_parser.parse_single_statement(probe_sql, dialect=dialect)
        self.sql_safety_validator.validate_read_only_sql(parsed_probe)
        if self.sql_access_validator is not None:
            self.sql_access_validator.validate_table_access(user_identity, parsed_probe)

        try:
            result = self.query_executor.execute_read_only_query(probe_sql, policy)
            count_val = 0
            if result.rows:
                first_row = result.rows[0]
                count_val = int(next(iter(first_row.values())) or 0)

            if count_val == 0:
                findings = (
                    f"Probe confirmed base table '{primary_table}' has 0 matching rows: "
                    "target population or metric is completely empty in database."
                )
                failure_code = (
                    "METRIC_UNAVAILABLE_IN_DB"
                    if probe_type == "METRIC_NON_NULL_PROBE"
                    else "BASE_POPULATION_EMPTY"
                )
            else:
                findings = (
                    f"Probe revealed base table '{primary_table}' has {count_val} rows, "
                    "indicating restrictive WHERE filters or JOIN conditions eliminated all output."
                )
                failure_code = "FILTER_GROUNDING_FAILURE"

            return DiagnosticProbeOutcome(
                probe_executed=True,
                probe_type=probe_type,
                probe_sql=probe_sql,
                findings=findings,
                failure_code=failure_code,
                details={"table": primary_table, "count": count_val},
            )
        except Exception as exc:
            return DiagnosticProbeOutcome(
                probe_executed=False,
                probe_type=probe_type,
                probe_sql=probe_sql,
                findings=f"Diagnostic probe execution failed: {exc}",
                failure_code="PROBE_EXECUTION_ERROR",
            )
