"""Generic SQL mutation / counterexample operators (E05 §21).

These operators produce *logically wrong* variants of a SQL statement so tests
can verify that the scorer and lucky-match tooling do not mark obviously-wrong
logic as safe. They are **evaluation-only** and never touch runtime generation
(E05 §3, §21).

Operators are intentionally generic (no benchmark-specific questions, E05 §20):
remove a predicate, alter a join key, change an aggregation function, change a
literal, drop a time/range constraint, alter a comparison operator. Each returns
zero or more :class:`Mutant` objects; an operator that cannot apply to a given
statement simply yields nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

_AGG_SWAP = {
    "SUM": "AVG",
    "AVG": "SUM",
    "COUNT": "SUM",
    "MAX": "MIN",
    "MIN": "MAX",
}

_CMP_SWAP: dict[type[exp.Expression], type[exp.Expression]] = {
    exp.GT: exp.LT,
    exp.LT: exp.GT,
    exp.GTE: exp.LTE,
    exp.LTE: exp.GTE,
    exp.EQ: exp.NEQ,
    exp.NEQ: exp.EQ,
}


@dataclass(frozen=True)
class Mutant:
    """A mutated SQL string plus the operator that produced it."""

    operator: str
    sql: str
    note: str


def _parse(sql: str) -> exp.Expression | None:
    try:
        return sqlglot.parse_one(sql, dialect="sqlite")
    except sqlglot.errors.SqlglotError:
        return None


def _render(tree: exp.Expression) -> str:
    return tree.sql(dialect="sqlite")


def remove_predicate(sql: str) -> list[Mutant]:
    """Drop the WHERE clause entirely (removes all filter predicates)."""

    tree = _parse(sql)
    if tree is None:
        return []
    mutants: list[Mutant] = []
    for select in tree.find_all(exp.Select):
        where = select.args.get("where")
        if where is not None:
            clone = tree.copy()
            for clone_select in clone.find_all(exp.Select):
                if clone_select.sql() == select.sql():
                    clone_select.set("where", None)
                    break
            mutants.append(
                Mutant("remove_predicate", _render(clone), "dropped WHERE clause")
            )
            break
    return mutants


def alter_join_key(sql: str) -> list[Mutant]:
    """Corrupt the first join condition by swapping it to a tautology (1=1)."""

    tree = _parse(sql)
    if tree is None:
        return []
    for join in tree.find_all(exp.Join):
        if join.args.get("on") is not None:
            clone = tree.copy()
            for clone_join in clone.find_all(exp.Join):
                if clone_join.args.get("on") is not None:
                    clone_join.set(
                        "on",
                        exp.EQ(this=exp.Literal.number(1), expression=exp.Literal.number(1)),
                    )
                    break
            return [Mutant("alter_join_key", _render(clone), "join ON replaced with 1=1")]
    return []


def change_aggregation(sql: str) -> list[Mutant]:
    """Swap the first aggregation function for a different one (SUM<->AVG, ...)."""

    tree = _parse(sql)
    if tree is None:
        return []
    for func in tree.find_all(exp.AggFunc):
        name = func.key.upper()
        if name in _AGG_SWAP:
            clone = tree.copy()
            for clone_func in clone.find_all(exp.AggFunc):
                if clone_func.key.upper() == name:
                    replacement = getattr(exp, _AGG_SWAP[name].capitalize(), None)
                    if replacement is None:
                        return []
                    clone_func.replace(replacement(this=clone_func.this))
                    break
            return [
                Mutant(
                    "change_aggregation",
                    _render(clone),
                    f"{name} -> {_AGG_SWAP[name]}",
                )
            ]
    return []


def change_literal(sql: str) -> list[Mutant]:
    """Perturb the first numeric literal (+1) or corrupt the first string literal."""

    tree = _parse(sql)
    if tree is None:
        return []
    for lit in tree.find_all(exp.Literal):
        clone = tree.copy()
        target = None
        for clone_lit in clone.find_all(exp.Literal):
            if clone_lit.sql() == lit.sql():
                target = clone_lit
                break
        if target is None:
            continue
        if lit.is_string:
            target.replace(exp.Literal.string(str(lit.this) + "_MUT"))
            note = "string literal corrupted"
        else:
            try:
                new_value = float(lit.this) + 1
            except ValueError:
                continue
            number = int(new_value) if new_value.is_integer() else new_value
            target.replace(exp.Literal.number(number))
            note = "numeric literal +1"
        return [Mutant("change_literal", _render(clone), note)]
    return []


def alter_comparison(sql: str) -> list[Mutant]:
    """Flip the first comparison operator (> to <, = to !=, ...)."""

    tree = _parse(sql)
    if tree is None:
        return []
    for node in tree.walk():
        node_type = type(node)
        if node_type in _CMP_SWAP:
            clone = tree.copy()
            for clone_node in clone.walk():
                if type(clone_node) is node_type and clone_node.sql() == node.sql():
                    swapped = _CMP_SWAP[node_type]
                    clone_node.replace(
                        swapped(this=clone_node.this, expression=clone_node.expression)
                    )
                    break
            return [
                Mutant(
                    "alter_comparison",
                    _render(clone),
                    f"{node_type.__name__} flipped",
                )
            ]
    return []


ALL_OPERATORS = (
    remove_predicate,
    alter_join_key,
    change_aggregation,
    change_literal,
    alter_comparison,
)


def generate_mutants(sql: str) -> list[Mutant]:
    """Apply every operator and return all successfully-produced mutants."""

    mutants: list[Mutant] = []
    for operator in ALL_OPERATORS:
        mutants.extend(operator(sql))
    return mutants
