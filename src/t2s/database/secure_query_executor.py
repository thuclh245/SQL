from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from t2s.contracts import SqlCandidate
from t2s.database.query_execution_policy import QueryExecutionPolicy
from t2s.database.query_execution_result import QueryExecutionResult
from t2s.database.query_executor_port import QueryExecutorPort
from t2s.database.query_explain_result import QueryExplainResult
from t2s.observability.correlation import read_correlation_context
from t2s.security.user_identity import UserIdentity
from t2s.verification.sql_access_validator import SqlAccessValidator
from t2s.verification.sql_ast_parser import SqlAstParser
from t2s.verification.sql_safety_validator import SqlSafetyValidator


class QueryAuditEvent(BaseModel):
    action: Literal["explain", "execute"]
    outcome: Literal["blocked", "failed", "succeeded"]
    user_id: str
    run_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    dialect: str
    sql: str
    reason: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QueryAuditSinkPort(Protocol):
    def record_query_audit_event(self, audit_event: QueryAuditEvent) -> None:
        ...


class SecureQueryExecutor:
    def __init__(
        self,
        sql_ast_parser: SqlAstParser,
        sql_safety_validator: SqlSafetyValidator,
        sql_access_validator: SqlAccessValidator,
        query_executor: QueryExecutorPort,
        query_audit_sink: QueryAuditSinkPort,
        execution_policy: QueryExecutionPolicy,
    ) -> None:
        self.sql_ast_parser = sql_ast_parser
        self.sql_safety_validator = sql_safety_validator
        self.sql_access_validator = sql_access_validator
        self.query_executor = query_executor
        self.query_audit_sink = query_audit_sink
        self.execution_policy = execution_policy

    def explain_sql_candidate(
        self,
        user_identity: UserIdentity,
        sql_candidate: SqlCandidate,
    ) -> QueryExplainResult:
        self._validate_sql_candidate(user_identity, sql_candidate, action="explain")
        try:
            explain_result = self.query_executor.explain_query(
                sql=sql_candidate.sql,
                execution_policy=self.execution_policy,
            )
        except Exception as exc:
            self._record_audit_event(user_identity, sql_candidate, "explain", "failed", str(exc))
            raise
        self._record_audit_event(user_identity, sql_candidate, "explain", "succeeded")
        return explain_result

    def execute_sql_candidate(
        self,
        user_identity: UserIdentity,
        sql_candidate: SqlCandidate,
    ) -> QueryExecutionResult:
        self._validate_sql_candidate(user_identity, sql_candidate, action="execute")
        try:
            execution_result = self.query_executor.execute_read_only_query(
                sql=sql_candidate.sql,
                execution_policy=self.execution_policy,
            )
        except Exception as exc:
            self._record_audit_event(user_identity, sql_candidate, "execute", "failed", str(exc))
            raise
        self._record_audit_event(user_identity, sql_candidate, "execute", "succeeded")
        return execution_result

    def _validate_sql_candidate(
        self,
        user_identity: UserIdentity,
        sql_candidate: SqlCandidate,
        action: Literal["explain", "execute"],
    ) -> None:
        try:
            parsed_sql = self.sql_ast_parser.parse_single_statement(
                sql=sql_candidate.sql,
                dialect=sql_candidate.dialect,
            )
            self.sql_safety_validator.validate_read_only_sql(parsed_sql)
            self.sql_access_validator.validate_table_access(user_identity, parsed_sql)
        except Exception as exc:
            self._record_audit_event(user_identity, sql_candidate, action, "blocked", str(exc))
            raise

    def _record_audit_event(
        self,
        user_identity: UserIdentity,
        sql_candidate: SqlCandidate,
        action: Literal["explain", "execute"],
        outcome: Literal["blocked", "failed", "succeeded"],
        reason: str | None = None,
    ) -> None:
        correlation_context = read_correlation_context()
        self.query_audit_sink.record_query_audit_event(
            QueryAuditEvent(
                action=action,
                outcome=outcome,
                user_id=user_identity.user_id,
                run_id=correlation_context.get("run_id")
                or sql_candidate.generation_trace.run_id,
                request_id=correlation_context.get("request_id"),
                trace_id=correlation_context.get("trace_id"),
                dialect=sql_candidate.dialect,
                sql=sql_candidate.sql,
                reason=reason,
            )
        )
