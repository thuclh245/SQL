"""Small AST policy checks used by the web application's telecom guardrail."""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class PolicyFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class PolicyCatalog:
    partition_columns: dict[str, str]
    nm_pairs: set[tuple[str, str]]


class AstPolicyGuard:
    def __init__(self, catalog: PolicyCatalog, dialect: str = "sqlite") -> None:
        self.catalog = catalog
        self.dialect = dialect

    def validate(self, sql: str) -> list[PolicyFinding]:
        try:
            tree = sqlglot.parse_one(sql, dialect=self.dialect)
        except Exception:
            return [PolicyFinding("PARSE", "block", "Không thể phân tích cú pháp SQL.")]

        findings: list[PolicyFinding] = []
        referenced_tables = {table.name for table in tree.find_all(exp.Table) if table.name}
        where_sql = " ".join(where.sql(dialect=self.dialect).lower() for where in tree.find_all(exp.Where))
        for table, partition_column in self.catalog.partition_columns.items():
            if table in referenced_tables and partition_column.lower() not in where_sql:
                findings.append(PolicyFinding(
                    "PARTITION", "block",
                    f"Bảng {table} phải được lọc theo cột phân vùng {partition_column}.",
                ))
        return findings

    @staticmethod
    def is_blocked(findings: list[PolicyFinding]) -> bool:
        return any(finding.severity == "block" for finding in findings)
