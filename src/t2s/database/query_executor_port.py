from typing import Protocol

from t2s.database.query_execution_policy import QueryExecutionPolicy
from t2s.database.query_execution_result import QueryExecutionResult
from t2s.database.query_explain_result import QueryExplainResult


class QueryExecutorPort(Protocol):
    def explain_query(
        self, sql: str, execution_policy: QueryExecutionPolicy
    ) -> QueryExplainResult: ...

    def execute_read_only_query(
        self,
        sql: str,
        execution_policy: QueryExecutionPolicy,
    ) -> QueryExecutionResult: ...
