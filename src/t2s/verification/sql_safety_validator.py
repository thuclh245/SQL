from sqlglot import expressions as exp

from t2s.errors import UnsafeSqlError
from t2s.verification.sql_ast_parser import ParsedSql

READ_ONLY_ROOT_EXPRESSIONS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
MUTATING_EXPRESSION_NAMES = {
    "Alter",
    "Create",
    "Delete",
    "Drop",
    "Grant",
    "Insert",
    "Into",
    "Lock",
    "Merge",
    "Revoke",
    "Truncate",
    "TruncateTable",
    "Update",
}


class SqlSafetyValidator:
    def validate_read_only_sql(self, parsed_sql: ParsedSql) -> None:
        if not isinstance(parsed_sql.ast, READ_ONLY_ROOT_EXPRESSIONS):
            raise UnsafeSqlError("SQL root statement must be a read-only query.")

        mutating_expressions = [
            expression
            for expression in parsed_sql.ast.walk()
            if expression.__class__.__name__ in MUTATING_EXPRESSION_NAMES
        ]
        if mutating_expressions:
            blocked_expression_names = sorted(
                {expression.__class__.__name__ for expression in mutating_expressions}
            )
            joined_expression_names = ", ".join(blocked_expression_names)
            raise UnsafeSqlError(
                f"SQL contains mutation-oriented operations: {joined_expression_names}"
            )
