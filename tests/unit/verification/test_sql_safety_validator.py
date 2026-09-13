import pytest

from t2s.errors import UnsafeSqlError
from t2s.verification import SqlAstParser, SqlSafetyValidator


@pytest.mark.parametrize(
    "unsafe_sql",
    [
        "DROP TABLE customers",
        "DELETE FROM customers",
        "UPDATE customers SET name = 'x'",
        "INSERT INTO customers(id) VALUES (1)",
        "CREATE TABLE leaked(id int)",
        "ALTER TABLE customers ADD COLUMN leaked int",
        "TRUNCATE TABLE customers",
        "SELECT * INTO new_table FROM customers",
        "SELECT * FROM customers FOR UPDATE",
        "SELECT * FROM customers FOR SHARE",
        "SELECT * FROM customers FOR NO KEY UPDATE",
        """
        MERGE INTO customers USING updates ON customers.id = updates.id
        WHEN MATCHED THEN UPDATE SET name = updates.name
        """,
    ],
)
def test_validator_blocks_mutation_oriented_sql(unsafe_sql: str) -> None:
    parsed_sql = SqlAstParser().parse_single_statement(unsafe_sql, "postgres")

    with pytest.raises(UnsafeSqlError):
        SqlSafetyValidator().validate_read_only_sql(parsed_sql)


def test_parser_blocks_multi_statement_payload() -> None:
    with pytest.raises(UnsafeSqlError):
        SqlAstParser().parse_single_statement(
            "SELECT * FROM customers; DROP TABLE customers",
            "sqlite",
        )


def test_validator_allows_single_select_with_cte_and_subquery() -> None:
    parsed_sql = SqlAstParser().parse_single_statement(
        """
        WITH paid_orders AS (
            SELECT customer_id, total
            FROM orders
            WHERE status = 'paid'
        )
        SELECT c.name
        FROM customers AS c
        WHERE c.id IN (SELECT customer_id FROM paid_orders)
        """,
        "sqlite",
    )

    SqlSafetyValidator().validate_read_only_sql(parsed_sql)


def test_parser_extracts_base_table_names_without_aliases_or_cte_names() -> None:
    parsed_sql = SqlAstParser().parse_single_statement(
        """
        WITH paid_orders AS (
            SELECT customer_id, total
            FROM orders AS o
            WHERE status = 'paid'
        )
        SELECT c.name
        FROM main.customers AS c
        JOIN paid_orders ON paid_orders.customer_id = c.id
        """,
        "sqlite",
    )

    assert parsed_sql.referenced_table_identifiers() == {"orders", "main.customers"}


def test_parser_keeps_schema_qualified_table_when_short_name_matches_cte() -> None:
    parsed_sql = SqlAstParser().parse_single_statement(
        """
        WITH secret_credentials AS (
            SELECT 1 AS dummy
        )
        SELECT id, secret_token
        FROM main.secret_credentials
        """,
        "sqlite",
    )

    assert parsed_sql.referenced_table_identifiers() == {"main.secret_credentials"}


def test_parser_handles_nested_cte_subquery_and_quoted_identifiers() -> None:
    parsed_sql = SqlAstParser().parse_single_statement(
        """
        WITH "orders" AS (
            SELECT customer_id FROM "raw"."events"
        ),
        nested AS (
            SELECT customer_id FROM "orders"
        )
        SELECT *
        FROM "analytics"."orders"
        WHERE customer_id IN (SELECT customer_id FROM nested)
        """,
        "postgres",
    )

    assert parsed_sql.referenced_table_identifiers() == {
        "raw.events",
        "analytics.orders",
    }
