"""AST Policy Guard for Telecom & Enterprise Lakehouse Text-to-SQL.

Enforces deterministic static checks before execution (0 GPU):
1. READ_ONLY: Blocks any DDL/DML write statements (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER).
2. SCHEMA_CHECK: Verifies tables and referenced columns exist in the catalog.
3. PARTITION_FILTER: Enforces mandatory partition filter (e.g. `dt = '...'`) on large partitioned tables.
4. FANOUT_CHECK: Detects N:M joins lacking aggregation or deduplication (DISTINCT / GROUP BY).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import sqlglot
from sqlglot import exp


@dataclass
class PolicyCatalog:
    tables: dict[str, list[str]] = field(default_factory=dict)       # table_name -> [column_names]
    partition_columns: dict[str, str] = field(default_factory=dict)  # table_name -> partition_col (e.g. "cdr_voice": "dt")
    nm_pairs: set[tuple[str, str]] = field(default_factory=set)      # set of (left_table, right_table) with N:M cardinality

    def has_table(self, table_name: str) -> bool:
        return table_name.lower() in {k.lower() for k in self.tables}

    def get_columns(self, table_name: str) -> list[str]:
        for k, v in self.tables.items():
            if k.lower() == table_name.lower():
                return [c.lower() for c in v]
        return []


@dataclass
class PolicyFinding:
    code: Literal["READ_ONLY", "SCHEMA", "PARTITION", "FANOUT", "PARSE"]
    severity: Literal["block", "warn"]
    message: str


def _extract_tables(tree: exp.Expression) -> list[tuple[str, str]]:
    """Returns list of (table_name, alias or name)."""
    out = []
    for t in tree.find_all(exp.Table):
        if t.name:
            out.append((t.name, (t.alias or t.name)))
    return out


def _extract_filter_columns(tree: exp.Expression) -> set[str]:
    """Extracts column identifiers appearing in WHERE, ON, and HAVING clauses."""
    names: set[str] = set()
    for node in list(tree.find_all(exp.Where)) + list(tree.find_all(exp.Join)) + list(tree.find_all(exp.Having)):
        for c in node.find_all(exp.Column):
            names.add(c.name.lower())
    return names


class AstPolicyGuard:
    """Deterministic AST policy validator for Telecom Lakehouse queries."""

    def __init__(self, catalog: PolicyCatalog | None = None, dialect: str = "sqlite") -> None:
        self.catalog = catalog or PolicyCatalog()
        self.dialect = dialect

    def validate(self, sql: str, dialect: str | None = None) -> list[PolicyFinding]:
        target_dialect = dialect or self.dialect
        findings: list[PolicyFinding] = []

        try:
            tree = sqlglot.parse_one(sql, dialect=target_dialect)
        except Exception as e:
            return [PolicyFinding("PARSE", "block", f"Không thể phân tích cú pháp SQL: {e}")]

        if tree is None:
            return [PolicyFinding("PARSE", "block", "Câu lệnh SQL rỗng")]

        # 1. READ_ONLY Check
        forbidden_exprs = (
            exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
            exp.Alter, exp.TruncateTable
        )
        for bad in forbidden_exprs:
            if tree.find(bad):
                findings.append(PolicyFinding("READ_ONLY", "block", f"Phát hiện lệnh ghi/thay đổi cấu trúc: {bad.__name__}"))
                break

        used_tables = _extract_tables(tree)

        # 2. SCHEMA - Table and Column existence
        if self.catalog.tables:
            for name, _ in used_tables:
                if not self.catalog.has_table(name):
                    findings.append(PolicyFinding("SCHEMA", "block", f"Bảng không tồn tại trong Catalog: {name}"))

            known_cols: set[str] = set()
            for name, _ in used_tables:
                known_cols.update(self.catalog.get_columns(name))

            if known_cols:
                for c in tree.find_all(exp.Column):
                    col_name = c.name.lower()
                    if col_name and col_name != "*" and col_name not in known_cols:
                        findings.append(PolicyFinding("SCHEMA", "block", f"Cột không tồn tại trong Catalog: {c.sql()}"))

        # 3. PARTITION - Mandatory partition filter check (e.g. Hive / Lakehouse safety)
        if self.catalog.partition_columns:
            filter_cols = _extract_filter_columns(tree)
            for name, _ in used_tables:
                for big_table, pcol in self.catalog.partition_columns.items():
                    if big_table.lower() == name.lower() and pcol.lower() not in filter_cols:
                        findings.append(
                            PolicyFinding(
                                "PARTITION",
                                "block",
                                f"Bảng lớn '{name}' bắt buộc phải có điều kiện lọc trên cột phân vùng '{pcol}'"
                            )
                        )

        # 4. FANOUT - N:M Join without deduplication
        if self.catalog.nm_pairs:
            tset = {n.lower() for n, _ in used_tables}
            has_dedup = bool(tree.find(exp.Distinct) or tree.find(exp.Group))
            if not has_dedup:
                for a, b in self.catalog.nm_pairs:
                    if a.lower() in tset and b.lower() in tset:
                        findings.append(
                            PolicyFinding(
                                "FANOUT",
                                "warn",
                                f"Cảnh báo: JOIN quan hệ nhiều-nhiều (N:M) giữa '{a}' và '{b}' có nguy cơ nhân đôi số liệu; cần DISTINCT hoặc GROUP BY"
                            )
                        )

        return findings

    def is_blocked(self, findings: list[PolicyFinding]) -> bool:
        return any(f.severity == "block" for f in findings)
