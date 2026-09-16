from pathlib import Path
import pytest

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
    assert "catalog_fqn: postgres_prod.warehouse.finance.sales_orders" in user_message
    assert "sql_identifier: finance.sales_orders" in user_message
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
    assert "from_fqn: postgres_prod.warehouse.finance.sales_orders" in user_message
    assert "to_fqn: postgres_prod.warehouse.crm.customers" in user_message
    assert "sql_identifier: finance.sales_orders" in user_message
    assert "sql_identifier: crm.customers" in user_message
    assert "warehouse.marketing.leads" not in user_message


def test_prompt_builder_uses_sql_identifier_when_fqn_differs() -> None:
    prompt_builder = DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql"))

    messages = prompt_builder.build_solver_messages(
        query_request=QueryRequest(question="Revenue by region"),
        grounding_context=build_single_table_sales_grounding_context(),
        target_dialect="postgres",
    )

    user_message = messages[1]["content"]
    assert "sql_identifier: finance.sales_orders" in user_message
    assert "catalog_fqn: postgres_prod.warehouse.finance.sales_orders" in user_message
    assert "table: postgres_prod.warehouse.finance.sales_orders" not in user_message


def test_default_prompt_loading_does_not_depend_on_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    prompt_builder = DirectSqlPromptBuilder()

    messages = prompt_builder.build_solver_messages(
        query_request=QueryRequest(question="Revenue by region"),
        grounding_context=build_single_table_sales_grounding_context(),
        target_dialect="postgres",
    )

    assert messages[0]["content"].startswith("You are a read-only enterprise SQL solver.")


def test_prompt_builder_formats_complete_semantic_plan() -> None:
    from t2s.semantics.semantic_plan import (
        ExpectedValueType,
        MetricAggregation,
        PlannerStatus,
        ResultExpectation,
        ResultShape,
        SemanticFilter,
        SemanticPlan,
    )

    prompt_builder = DirectSqlPromptBuilder()
    plan = SemanticPlan(
        plan_id="plan-fmt-1",
        status=PlannerStatus.READY,
        metric_name="net_revenue",
        aggregation=MetricAggregation.SUM,
        dimensions=["region", "quarter"],
        population_scope="active customers",
        time_scope="2026-Q1 to 2026-Q3",
        filters=[
            SemanticFilter(column_name="status", operator="=", target_value="PAID"),
        ],
        relevant_tables=["sales_orders"],
        expectation=ResultExpectation(
            expected_shape=ResultShape.GROUPED_TABLE,
            expected_value_type=ExpectedValueType.NUMERIC,
            can_be_empty=False,
        ),
    )

    messages = prompt_builder.build_solver_messages(
        query_request=QueryRequest(question="Revenue by region and quarter"),
        grounding_context=build_single_table_sales_grounding_context(),
        target_dialect="postgres",
        semantic_plan=plan,
    )

    user_msg = messages[1]["content"]
    assert "- metric: net_revenue" in user_msg
    assert "- aggregation: SUM" in user_msg
    assert "- dimensions: region, quarter" in user_msg
    assert "- population_scope: active customers" in user_msg
    assert "- time_scope: 2026-Q1 to 2026-Q3" in user_msg
    assert "- filters: status = PAID" in user_msg
    assert "- expected_shape: GROUPED_TABLE" in user_msg
    assert "- expected_value_type: NUMERIC" in user_msg
    assert "- can_be_empty: False" in user_msg
