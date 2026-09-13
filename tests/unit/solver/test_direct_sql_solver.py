from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from t2s.contracts import QueryRequest
from t2s.contracts.sql_candidate import SqlCandidate
from t2s.errors import MalformedSolverOutputError
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver, SolverRequest
from t2s.solver.solver_request import SolverGenerationSettings
from t2s.solver.solver_response import StructuredChatResponse
from tests.fixtures.grounding_fixtures import build_single_table_sales_grounding_context


class FakeStructuredChatClient:
    def __init__(self, content: dict[str, Any]) -> None:
        self.content = content
        self.captured_messages: list[dict[str, str]] = []
        self.captured_schema: dict[str, Any] = {}

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        self.captured_messages = messages
        self.captured_schema = response_schema
        return StructuredChatResponse(
            content=self.content,
            model_name=model_name,
            elapsed_ms=42,
            prompt_tokens=120,
            output_tokens=80,
        )


def build_solver_request() -> SolverRequest:
    return SolverRequest(
        run_id="run-p4-test",
        query_request=QueryRequest(question="Doanh thu thuần Q3/2026 theo khu vực?", locale="vi"),
        target_dialect="postgres",
        grounding_context=build_single_table_sales_grounding_context(),
        generation_settings=SolverGenerationSettings(
            reasoning_effort="medium",
            max_output_tokens=512,
        ),
    )


@pytest.mark.anyio
async def test_sql_candidate_generated_from_fixture_with_trace_metadata() -> None:
    fake_client = FakeStructuredChatClient(
        {
            "sql": (
                "SELECT region, SUM(net_revenue) AS net_revenue "
                "FROM warehouse.finance.sales_orders "
                "WHERE order_date >= DATE '2026-07-01' "
                "AND order_date < DATE '2026-10-01' "
                "GROUP BY region"
            ),
            "dialect": "postgres",
            "referenced_tables": ["warehouse.finance.sales_orders"],
            "referenced_columns": [
                "warehouse.finance.sales_orders.region",
                "warehouse.finance.sales_orders.net_revenue",
                "warehouse.finance.sales_orders.order_date",
            ],
            "expected_columns": ["region", "net_revenue"],
            "assumptions": [],
            "unresolved": [],
        }
    )
    solver = DirectSqlSolver(
        chat_client=fake_client,
        prompt_builder=DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql")),
        model_name="gpt-oss-120b",
    )

    sql_candidate = await solver.generate_sql_candidate(build_solver_request())

    assert isinstance(sql_candidate, SqlCandidate)
    assert sql_candidate.sql.startswith("SELECT region")
    assert sql_candidate.dialect == "postgres"
    assert sql_candidate.generation_trace.run_id == "run-p4-test"
    assert sql_candidate.generation_trace.model_name == "gpt-oss-120b"
    assert sql_candidate.generation_trace.prompt_version == "v001"
    assert sql_candidate.generation_trace.reasoning_effort == "medium"
    assert fake_client.captured_schema["name"] == "sql_candidate"


@pytest.mark.anyio
async def test_malformed_structured_output_is_rejected() -> None:
    solver = DirectSqlSolver(
        chat_client=FakeStructuredChatClient({"sql": "SELECT 1", "dialect": "postgres"}),
        prompt_builder=DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql")),
    )

    with pytest.raises(MalformedSolverOutputError):
        await solver.generate_sql_candidate(build_solver_request())


@pytest.mark.anyio
async def test_empty_sql_is_rejected() -> None:
    solver = DirectSqlSolver(
        chat_client=FakeStructuredChatClient(
            {
                "sql": " ",
                "dialect": "postgres",
                "referenced_tables": [],
                "referenced_columns": [],
                "expected_columns": [],
                "assumptions": [],
                "unresolved": [],
            }
        ),
        prompt_builder=DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql")),
    )

    with pytest.raises(MalformedSolverOutputError):
        await solver.generate_sql_candidate(build_solver_request())


def test_sql_candidate_contract_rejects_empty_sql() -> None:
    with pytest.raises(ValidationError):
        SqlCandidate(
            sql="",
            dialect="postgres",
            generation_trace={
                "run_id": "run-p4-test",
                "model_name": "gpt-oss-120b",
                "prompt_version": "v001",
            },
        )
