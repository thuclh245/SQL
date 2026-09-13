from pydantic import BaseModel
from sqlglot import expressions as exp
from sqlglot import parse
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import Scope, traverse_scope

from t2s.contracts.sql_candidate import SupportedSqlDialect
from t2s.errors import UnsafeSqlError

SQLGLOT_DIALECTS: dict[SupportedSqlDialect, str] = {
    "postgres": "postgres",
    "clickhouse": "clickhouse",
    "starrocks": "mysql",
    "sqlite": "sqlite",
}


class ParsedSql(BaseModel):
    sql: str
    dialect: SupportedSqlDialect
    ast: exp.Expression

    model_config = {"arbitrary_types_allowed": True}

    def referenced_table_identifiers(self) -> set[str]:
        referenced_tables: set[str] = set()
        for scope in traverse_scope(self.ast):
            for table_expression, resolved_source in scope.selected_sources.values():
                if isinstance(resolved_source, exp.Table):
                    referenced_tables.add(self._table_identifier(resolved_source))
                elif not isinstance(resolved_source, Scope):
                    raise UnsafeSqlError("SQL table source could not be resolved safely.")
                elif table_expression.args.get("db") or table_expression.args.get("catalog"):
                    raise UnsafeSqlError("Qualified SQL table source was ambiguous.")
        return referenced_tables

    def _table_identifier(self, table: exp.Table) -> str:
        table_parts = [
            table_part
            for table_part in [table.catalog, table.db, table.name]
            if table_part
        ]
        return ".".join(table_parts)


class SqlAstParser:
    def parse_single_statement(self, sql: str, dialect: SupportedSqlDialect) -> ParsedSql:
        try:
            parsed_statements = [
                statement
                for statement in parse(sql, read=SQLGLOT_DIALECTS[dialect])
                if statement is not None
            ]
        except ParseError as exc:
            raise UnsafeSqlError("SQL could not be parsed for safety validation.") from exc

        if len(parsed_statements) != 1:
            raise UnsafeSqlError("SQL must contain exactly one statement.")

        return ParsedSql(sql=sql, dialect=dialect, ast=parsed_statements[0])
