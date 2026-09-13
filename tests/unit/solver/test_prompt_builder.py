from pathlib import Path

from t2s.contracts import QueryRequest
from t2s.solver import DirectSqlPromptBuilder
from tests.fixtures.grounding_fixtures import build_single_table_sales_grounding_context


def test_prompt_contains_authorized_schema_from_fixture() -> None:
    prompt_builder = DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql"))
    grounding_context = build_single_table_sales_grounding_context()

    messages = prompt_builder.build_solver_messages(
        query_request=QueryRequest(question="Doanh thu thuần Q3/2026 theo khu vực?", locale="vi"),
        grounding_context=grounding_context,
        target_dialect="postgres",
    )

    user_message = messages[1]["content"]
    assert "warehouse.finance.sales_orders" in user_message
    assert "net_revenue" in user_message
    assert "warehouse.secret.payroll" not in user_message
    assert prompt_builder.prompt_version == "v001"


def test_prompt_includes_join_relationship_without_adding_unrelated_schema() -> None:
    from tests.fixtures.grounding_fixtures import build_two_table_customer_grounding_context

    prompt_builder = DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql"))

    messages = prompt_builder.build_solver_messages(
        query_request=QueryRequest(question="Revenue by customer segment"),
        grounding_context=build_two_table_customer_grounding_context(),
        target_dialect="postgres",
    )

    user_message = messages[1]["content"]
    assert "warehouse.finance.sales_orders.customer_id" in user_message
    assert "warehouse.crm.customers.customer_id" in user_message
    assert "warehouse.marketing.leads" not in user_message
