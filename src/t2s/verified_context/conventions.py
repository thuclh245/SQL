"""Convention registry: loading, selection for a question, and AST checks.

Each check returns a list of violation strings; an empty list means the SQL
complies.  Checks inspect the parsed tree (sqlglot, DuckDB dialect), so
equivalent spellings are accepted: table aliases, ``x::DOUBLE``, TRY_CAST,
reversed comparisons, and the three common anti-join forms.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlglot
import yaml  # type: ignore[import-untyped]
from sqlglot import exp

Convention = dict[str, Any]

NUMERIC_TYPES = {
    exp.DataType.Type.DOUBLE,
    exp.DataType.Type.FLOAT,
    exp.DataType.Type.DECIMAL,
    exp.DataType.Type.INT,
    exp.DataType.Type.BIGINT,
    exp.DataType.Type.SMALLINT,
    exp.DataType.Type.TINYINT,
}
COMPARISONS: tuple[type[exp.Expression], ...] = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
OPS: dict[str, type[exp.Expression]] = {
    "eq": exp.EQ,
    "gt": exp.GT,
    "gte": exp.GTE,
    "lt": exp.LT,
    "lte": exp.LTE,
}
FLIP: dict[type[exp.Expression], type[exp.Expression]] = {
    exp.GT: exp.LT,
    exp.LT: exp.GT,
    exp.GTE: exp.LTE,
    exp.LTE: exp.GTE,
    exp.EQ: exp.EQ,
    exp.NEQ: exp.NEQ,
}
# Nodes where a bare text column is compared, computed, aggregated or ordered.
VALUE_USES: tuple[type[exp.Expression], ...] = COMPARISONS + (
    exp.Between,
    exp.In,
    exp.AggFunc,
    exp.Binary,
    exp.Ordered,
)
STOP: tuple[type[exp.Expression], ...] = (
    exp.Select,
    exp.Where,
    exp.Having,
    exp.Group,
    exp.From,
    exp.Join,
    exp.Subquery,
    exp.Alias,
    exp.Order,
)
Literal = str | float


def load_registry(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Registry không hợp lệ: {path}")
    return data


def parse(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, dialect="duckdb")


def table_fqn(node: exp.Table) -> str:
    """hive__npms__x and hive.npms.x both normalise to hive.npms.x."""
    parts = [p for p in (node.catalog, node.db, node.name) if p]
    return ".".join(parts).replace("__", ".").lower()


def referenced_tables(tree: exp.Expression) -> set[str]:
    return {table_fqn(t) for t in tree.find_all(exp.Table)}


def unwrap(node: exp.Expression) -> exp.Expression:
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def column_of(node: exp.Expression) -> str | None:
    """Column name if node is a column, possibly wrapped in AVG/MIN/MAX/SUM and/or CAST."""
    node = unwrap(node)
    if isinstance(node, (exp.Avg, exp.Min, exp.Max, exp.Sum)):
        node = unwrap(node.this)
    if isinstance(node, exp.Cast):
        node = unwrap(node.this)
    return node.name.lower() if isinstance(node, exp.Column) else None


def literal_value(node: exp.Expression) -> Literal | None:
    node = unwrap(node)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal):
        return -float(node.this.this)
    if isinstance(node, exp.Literal):
        return str(node.this) if node.is_string else float(node.this)
    return None


def comparisons(tree: exp.Expression) -> Iterator[tuple[str, type[exp.Expression], Literal]]:
    """Yield (column, op_class, literal) with the column normalised to the left."""
    for node in tree.find_all(*COMPARISONS):
        assert isinstance(node, exp.Binary)
        left, right = node.left, node.right
        col, lit = column_of(left), literal_value(right)
        op: type[exp.Expression] = type(node)
        if col is None or lit is None:
            col, lit = column_of(right), literal_value(left)
            op = FLIP[type(node)]
        if col is not None and lit is not None:
            yield col, op, lit


# ---------------------------------------------------------------- checks


def check_requires_cast(tree: exp.Expression, columns: list[str]) -> list[str]:
    wanted = {c.lower() for c in columns}
    bad = []
    for col in tree.find_all(exp.Column):
        if col.name.lower() not in wanted:
            continue
        node = col.parent
        while node is not None and not isinstance(node, STOP):
            if isinstance(node, exp.Cast):
                if node.to.this not in NUMERIC_TYPES:
                    bad.append(f"{col.sql()} được CAST sang kiểu không phải số")
                break
            if isinstance(node, VALUE_USES):
                bad.append(
                    f"{col.sql()} được dùng trong {type(node).__name__} mà không CAST sang số"
                )
                break
            node = node.parent
    return sorted(set(bad))


def check_literal_format(tree: exp.Expression, column: str, pattern: str) -> list[str]:
    rx = re.compile(pattern)
    bad = []
    for col, _op, lit in comparisons(tree):
        if col == column and isinstance(lit, str) and not rx.match(lit):
            bad.append(f"{column} so với '{lit}' sai định dạng")
    for node in tree.find_all(exp.Between, exp.In):
        if column_of(node.this) != column:
            continue
        values = (
            [node.args.get("low"), node.args.get("high")]
            if isinstance(node, exp.Between)
            else list(node.expressions)
        )
        for v in values:
            bound = literal_value(v) if v is not None else None
            if isinstance(bound, str) and not rx.match(bound):
                bad.append(f"{column} so với '{bound}' sai định dạng")
    for cast in tree.find_all(exp.Cast, exp.TryCast):
        if column_of(cast.this) == column:
            bad.append(
                f"{column} bị CAST sang {cast.to.sql()} (mất giờ, không dùng được partition)"
            )
    return sorted(set(bad))


def check_forbidden_table(tree: exp.Expression, table: str) -> list[str]:
    return [f"dùng bảng {table}"] if table.lower() in referenced_tables(tree) else []


def _ctes(tree: exp.Expression) -> dict[str, exp.Expression]:
    return {cte.alias_or_name.lower(): cte.this for cte in tree.find_all(exp.CTE)}


def _selects_from(
    node: exp.Expression, table: str, ctes: dict[str, exp.Expression] | None = None
) -> bool:
    """True if ``node`` reads ``table`` directly or through a CTE defined in the query."""
    ctes = ctes or {}
    for t in node.find_all(exp.Table):
        if table_fqn(t) == table:
            return True
        body = ctes.get(t.name.lower())
        if (
            body is not None
            and body is not node
            and _selects_from(body, table, {k: v for k, v in ctes.items() if k != t.name.lower()})
        ):
            return True
    return False


def _is_null_check(node: exp.Is, alias: str) -> bool:
    col = unwrap(node.this)
    return (
        isinstance(col, exp.Column)
        and col.table.lower() == alias
        and isinstance(node.expression, exp.Null)
    )


def check_requires_anti_join(tree: exp.Expression, table: str, key: str) -> list[str]:
    table = table.lower()
    ctes = _ctes(tree)
    for node in tree.find_all(exp.Not):
        inner = unwrap(node.this)
        if isinstance(inner, exp.Exists) and _selects_from(inner, table, ctes):
            return []
        if (
            isinstance(inner, exp.In)
            and column_of(inner.this) == key
            and _selects_from(inner, table, ctes)
        ):
            return []
    for join in tree.find_all(exp.Join):
        target = join.this
        if not isinstance(target, exp.Table) or not _selects_from(target, table, ctes):
            continue
        if (join.kind or "").upper() == "ANTI":
            return []
        if join.side != "LEFT":
            continue
        alias = (target.alias or target.name).lower()
        select = join.find_ancestor(exp.Select)
        where = select.args.get("where") if select else None
        if where and any(_is_null_check(n, alias) for n in where.find_all(exp.Is)):
            return []
    return [f"thiếu anti-join với {table}"]


def check_requires_filter(tree: exp.Expression, column: str, op: str, value: Any) -> list[str]:
    want_op = OPS[op]
    want: Literal = value if isinstance(value, str) else float(value)
    for col, got_op, lit in comparisons(tree):
        if col == column and got_op is want_op and lit == want:
            return []
    symbol = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
    return [f"thiếu điều kiện {column} {symbol} {value!r}"]


def check_grain_by_key(tree: exp.Expression, key: str) -> list[str]:
    for count in tree.find_all(exp.Count):
        arg = count.this
        if isinstance(arg, exp.Distinct) and any(column_of(e) == key for e in arg.expressions):
            return []
    for group in tree.find_all(exp.Group):
        if any(column_of(e) == key for e in group.expressions):
            return []
    return [f"không đếm/gom theo {key}"]


def check_inclusive_upper_bound(tree: exp.Expression, columns: list[str]) -> list[str]:
    wanted = {c.lower() for c in columns}
    return sorted(
        {
            f"cận trên {col} dùng < thay vì <="
            for col, op, lit in comparisons(tree)
            if col in wanted and op is exp.LT and isinstance(lit, str)
        }
    )


CheckFn = Callable[[exp.Expression, Mapping[str, Any]], list[str]]
CHECKS: dict[str, CheckFn] = {
    "requires_cast": lambda t, c: check_requires_cast(t, c["columns"]),
    "literal_format": lambda t, c: check_literal_format(t, c["column"], c["pattern"]),
    "forbidden_table": lambda t, c: check_forbidden_table(t, c["table"]),
    "requires_anti_join": lambda t, c: check_requires_anti_join(t, c["table"], c["key"]),
    "requires_filter": lambda t, c: check_requires_filter(t, c["column"], c["op"], c["value"]),
    "grain_by_key": lambda t, c: check_grain_by_key(t, c["key"]),
    "inclusive_upper_bound": lambda t, c: check_inclusive_upper_bound(t, c["columns"]),
}


def is_executable(conv: Convention) -> bool:
    return bool(conv.get("check")) and conv["check"]["kind"] in CHECKS


def run_check(sql: str, conv: Convention) -> list[str]:
    return CHECKS[conv["check"]["kind"]](parse(sql), conv["check"])


def applies(
    conv: Convention,
    *,
    question: str,
    tables: list[str],
    sql: str | None = None,
) -> bool:
    """Applicability comes from the question and the tables in scope, never from gold SQL,
    except ``sql_references`` which is an explicit "if you use X" rule."""
    cond = conv.get("applies_when") or {}
    wanted = {t.lower() for t in cond.get("tables", [])}
    if wanted and not wanted & {t.lower() for t in tables}:
        return False
    terms = [t.lower() for t in cond.get("question_terms", [])]
    if terms and not any(t in question.lower() for t in terms):
        return False
    ref = cond.get("sql_references")
    if ref:
        if sql is None:
            # Chưa có SQL: quy ước "nếu dùng X" áp dụng khi X nằm trong phạm vi bảng.
            return str(ref).lower() in {t.lower() for t in tables}
        if str(ref).lower() not in referenced_tables(parse(sql)):
            return False
    return True


@dataclass(frozen=True)
class ConventionViolation:
    convention_id: str
    rule: str
    messages: tuple[str, ...]


class ConventionRegistry:
    """Accepted conventions are enforced; proposed ones are shown to the model only
    when ``include_proposed`` is set, because they still lack a production source."""

    def __init__(self, conventions: list[Convention]) -> None:
        self.conventions = conventions

    @classmethod
    def from_file(cls, path: Path) -> ConventionRegistry:
        return cls(list(load_registry(path)["conventions"]))

    def select(
        self,
        *,
        question: str,
        tables: list[str],
        columns: set[str],
        include_proposed: bool = True,
    ) -> list[Convention]:
        out = []
        for conv in self.conventions:
            status = conv.get("status")
            if status not in ("accepted", "proposed") or (
                status == "proposed" and not include_proposed
            ):
                continue
            if str(conv.get("rule", "")).startswith("Chưa chốt"):
                continue
            if not applies(conv, question=question, tables=tables):
                continue
            chk = conv.get("check") or {}
            cols = [chk["column"]] if "column" in chk else list(chk.get("columns", []))
            if cols and not {c.lower() for c in cols} & columns:
                continue
            forbidden = chk.get("table")
            if chk.get("kind") == "forbidden_table" and forbidden:
                schema = str(forbidden).split(".")[1]
                if not any(f".{schema}." in f".{t}." for t in tables):
                    continue
            out.append(conv)
        return out

    def verify(self, sql: str, *, question: str, tables: list[str]) -> list[ConventionViolation]:
        found = []
        for conv in self.conventions:
            if conv.get("status") != "accepted" or not is_executable(conv):
                continue
            try:
                if not applies(conv, question=question, tables=tables, sql=sql):
                    continue
                messages = run_check(sql, conv)
            except sqlglot.errors.ParseError:
                continue
            if messages:
                found.append(ConventionViolation(conv["id"], conv["rule"], tuple(messages)))
        return found
