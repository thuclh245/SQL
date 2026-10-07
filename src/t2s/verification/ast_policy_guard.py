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
    """Policy inputs. Keys of ``partition_columns`` are bare (``cell``) or
    schema-qualified (``ran_kpi.cell``) table names."""

    partition_columns: dict[str, str]
    nm_pairs: set[tuple[str, str]]
    partition_severity: str = "block"


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
        for table, partition_column in self.catalog.partition_columns.items():
            nodes = [node for node in tree.find_all(exp.Table) if _matches(node, table)]
            if nodes and not any(_is_filtered(tree, node, partition_column) for node in nodes):
                findings.append(PolicyFinding(
                    "PARTITION", self.catalog.partition_severity,
                    f"Bảng {table} phải được lọc theo cột phân vùng {partition_column}.",
                ))
        return findings

    @staticmethod
    def is_blocked(findings: list[PolicyFinding]) -> bool:
        return any(finding.severity == "block" for finding in findings)


def _matches(node: exp.Table, key: str) -> bool:
    """True if a table reference is ``key`` (bare, or ``schema.table``)."""
    if "." in key:
        return bool(node.db) and f"{node.db}.{node.name}".lower() == key.lower()
    return node.name.lower() == key.lower()


def _is_filtered(tree: exp.Expression, node: exp.Table, column: str) -> bool:
    """True if some WHERE clause filters ``column`` of this table reference.

    An unqualified column counts for any table; a qualified one must use this
    reference's alias (or name), so ``WHERE b.date_hour = ...`` does not satisfy
    a requirement on table ``a``.
    """
    reference = node.alias_or_name.lower()
    for where in tree.find_all(exp.Where):
        for col in where.find_all(exp.Column):
            if col.name.lower() == column.lower() and (
                not col.table or col.table.lower() == reference
            ):
                return True
    return False
