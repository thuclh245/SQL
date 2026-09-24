"""AST-based checks for conventions/conventions.yaml (shared by validator, builder, audit).

Each check returns a list of violation strings; an empty list means the SQL
complies.  Checks inspect the parsed tree (sqlglot, DuckDB dialect), so
equivalent spellings are accepted: table aliases, `x::DOUBLE`, TRY_CAST,
reversed comparisons, and the three common anti-join forms.
"""
from __future__ import annotations

import re
from pathlib import Path

import sqlglot
import yaml
from sqlglot import exp

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conventions" / "conventions.yaml"

NUMERIC_TYPES = {
    exp.DataType.Type.DOUBLE, exp.DataType.Type.FLOAT, exp.DataType.Type.DECIMAL,
    exp.DataType.Type.INT, exp.DataType.Type.BIGINT, exp.DataType.Type.SMALLINT,
    exp.DataType.Type.TINYINT,
}
COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
OPS = {"eq": exp.EQ, "gt": exp.GT, "gte": exp.GTE, "lt": exp.LT, "lte": exp.LTE}
FLIP = {exp.GT: exp.LT, exp.LT: exp.GT, exp.GTE: exp.LTE, exp.LTE: exp.GTE, exp.EQ: exp.EQ, exp.NEQ: exp.NEQ}
# Nodes where a bare text column is compared, computed, aggregated or ordered.
VALUE_USES = COMPARISONS + (exp.Between, exp.In, exp.AggFunc, exp.Binary, exp.Ordered)
STOP = (exp.Select, exp.Where, exp.Having, exp.Group, exp.From, exp.Join, exp.Subquery, exp.Alias, exp.Order)


def load_registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


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


def literal_value(node: exp.Expression):
    node = unwrap(node)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal):
        return -float(node.this.this)
    if isinstance(node, exp.Literal):
        return node.this if node.is_string else float(node.this)
    return None


def comparisons(tree: exp.Expression):
    """Yield (column, op_class, literal) with the column normalised to the left."""
    for node in tree.find_all(*COMPARISONS):
        left, right = node.left, node.right
        col, lit = column_of(left), literal_value(right)
        op = type(node)
        if col is None or lit is None:
            col, lit = column_of(right), literal_value(left)
            op = FLIP[type(node)]
        if col is not None and lit is not None:
            yield col, op, lit


# ---------------------------------------------------------------- checks

def check_requires_cast(tree, columns) -> list[str]:
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
                bad.append(f"{col.sql()} được dùng trong {type(node).__name__} mà không CAST sang số")
                break
            node = node.parent
    return sorted(set(bad))


def check_literal_format(tree, column, pattern) -> list[str]:
    rx = re.compile(pattern)
    bad = []
    for col, _op, lit in comparisons(tree):
        if col == column and isinstance(lit, str) and not rx.match(lit):
            bad.append(f"{column} so với '{lit}' sai định dạng")
    for node in tree.find_all(exp.Between, exp.In):
        if column_of(node.this) != column:
            continue
        values = [node.args.get("low"), node.args.get("high")] if isinstance(node, exp.Between) else node.expressions
        for v in values:
            lit = literal_value(v) if v is not None else None
            if isinstance(lit, str) and not rx.match(lit):
                bad.append(f"{column} so với '{lit}' sai định dạng")
    return sorted(set(bad))


def check_forbidden_table(tree, table) -> list[str]:
    return [f"dùng bảng {table}"] if table.lower() in referenced_tables(tree) else []


def _selects_from(node: exp.Expression, table: str) -> bool:
    return any(table_fqn(t) == table for t in node.find_all(exp.Table))


def check_requires_anti_join(tree, table, key) -> list[str]:
    table = table.lower()
    for node in tree.find_all(exp.Not):
        inner = unwrap(node.this)
        if isinstance(inner, exp.Exists) and _selects_from(inner, table):
            return []
        if isinstance(inner, exp.In) and column_of(inner.this) == key and _selects_from(inner, table):
            return []
    for join in tree.find_all(exp.Join):
        target = join.this
        if not (isinstance(target, exp.Table) and table_fqn(target) == table and join.side == "LEFT"):
            continue
        alias = (target.alias or target.name).lower()
        select = join.find_ancestor(exp.Select)
        where = select.args.get("where") if select else None
        if where and any(
            isinstance(unwrap(n.this), exp.Column)
            and unwrap(n.this).table.lower() == alias
            and isinstance(n.expression, exp.Null)
            for n in where.find_all(exp.Is)
        ):
            return []
    return [f"thiếu anti-join với {table}"]


def check_requires_filter(tree, column, op, value) -> list[str]:
    want_op = OPS[op]
    want = value if isinstance(value, str) else float(value)
    for col, got_op, lit in comparisons(tree):
        if col == column and got_op is want_op and lit == want:
            return []
    symbol = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
    return [f"thiếu điều kiện {column} {symbol} {value!r}"]


def check_grain_by_key(tree, key) -> list[str]:
    for count in tree.find_all(exp.Count):
        arg = count.this
        if isinstance(arg, exp.Distinct) and any(column_of(e) == key for e in arg.expressions):
            return []
    for group in tree.find_all(exp.Group):
        if any(column_of(e) == key for e in group.expressions):
            return []
    return [f"không đếm/gom theo {key}"]


def check_inclusive_upper_bound(tree, columns) -> list[str]:
    wanted = {c.lower() for c in columns}
    return sorted({
        f"cận trên {col} dùng < thay vì <="
        for col, op, lit in comparisons(tree)
        if col in wanted and op is exp.LT and isinstance(lit, str)
    })


CHECKS = {
    "requires_cast": lambda t, c: check_requires_cast(t, c["columns"]),
    "literal_format": lambda t, c: check_literal_format(t, c["column"], c["pattern"]),
    "forbidden_table": lambda t, c: check_forbidden_table(t, c["table"]),
    "requires_anti_join": lambda t, c: check_requires_anti_join(t, c["table"], c["key"]),
    "requires_filter": lambda t, c: check_requires_filter(t, c["column"], c["op"], c["value"]),
    "grain_by_key": lambda t, c: check_grain_by_key(t, c["key"]),
    "inclusive_upper_bound": lambda t, c: check_inclusive_upper_bound(t, c["columns"]),
}


def is_executable(conv: dict) -> bool:
    return conv["check"]["kind"] in CHECKS


def run_check(sql: str, conv: dict) -> list[str]:
    return CHECKS[conv["check"]["kind"]](parse(sql), conv["check"])


def applies(conv: dict, case: dict, sql: str | None = None) -> bool:
    """Applicability is derived from the question and declared tables, not gold content,
    except `sql_references` which is an explicit "if you use X" rule."""
    cond = conv.get("applies_when") or {}
    tables = {t.lower() for t in cond.get("tables", [])}
    if tables and not tables & {t.lower() for t in case.get("required_tables", [])}:
        return False
    terms = [t.lower() for t in cond.get("question_terms", [])]
    if terms:
        text = " ".join(case.get(k, "") or "" for k in ("question_explicit", "question_natural", "question")).lower()
        if not any(t in text for t in terms):
            return False
    ref = cond.get("sql_references")
    if ref and (sql is None or ref.lower() not in referenced_tables(parse(sql))):
        return False
    return True
