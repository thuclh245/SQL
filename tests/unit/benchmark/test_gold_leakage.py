from pathlib import Path
from typing import Any

import pytest

from t2s.benchmark.case_loader import load_benchmark_cases
from t2s.benchmark.runtime_factory import build_query_request_from_benchmark_case
from t2s.catalog import CatalogColumn, CatalogSearchDocumentBuilder, CatalogTable
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.grounding import GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.orchestration import AdaptiveOrchestrator, EscalationBudget, EscalationPolicy
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver, SolverRequest
from t2s.solver.solver_response import StructuredChatResponse


class StaticAccessPolicy:
    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return [
            AuthorizedSqlResource(
                catalog_fqn="db.main.customers",
                sql_identifier="customers",
            )
        ]


class CapturingStructuredChatClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        self.messages = messages
        return StructuredChatResponse(
            content={
                "sql": "SELECT name FROM customers",
                "dialect": "sqlite",
                "referenced_tables": ["customers"],
                "referenced_columns": ["customers.name"],
                "expected_columns": ["name"],
                "assumptions": [],
                "unresolved": [],
            },
            model_name=model_name,
            elapsed_ms=1,
            prompt_tokens=None,
            output_tokens=None,
        )


def test_gold_sql_does_not_enter_grounding_context_or_prompt_builder(tmp_path: Path) -> None:
    gold_sql = "SELECT secret_gold FROM private_table"
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        (
            '{"case_id":"case-1","bird_gold_sql":"SELECT secret_gold FROM private_table",'
            '"inference":{"question":"List customers","db_id":"db","evidence":"customer hint"},'
            '"gold":{"sql_original":"SELECT secret_gold FROM private_table"}}\n'
        ),
        encoding="utf-8",
    )
    case_bundle = load_benchmark_cases(dataset_path)[0]
    query_request = build_query_request_from_benchmark_case(
        question=case_bundle.inference_case.question,
        evidence=case_bundle.inference_case.evidence,
    )
    grounding_builder = _build_grounding_context_builder()
    grounding_context = grounding_builder.build_grounding_context(
        query_request=query_request,
        user_identity=UserIdentity(user_id="analyst"),
    )
    prompt_builder = DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql"))
    messages = prompt_builder.build_solver_messages(
        query_request=query_request,
        grounding_context=grounding_context,
        target_dialect="sqlite",
    )

    assert gold_sql not in grounding_context.model_dump_json()
    assert gold_sql not in "\n".join(message["content"] for message in messages)


@pytest.mark.anyio
async def test_gold_sql_does_not_enter_adaptive_orchestrator_or_chat_request(
    tmp_path: Path,
) -> None:
    gold_sql = "SELECT secret_gold FROM private_table"
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        (
            '{"case_id":"case-1","bird_gold_sql":"SELECT secret_gold FROM private_table",'
            '"inference":{"question":"List customers","db_id":"db","evidence":"customer hint"},'
            '"gold":{"sql_original":"SELECT secret_gold FROM private_table"}}\n'
        ),
        encoding="utf-8",
    )
    case_bundle = load_benchmark_cases(dataset_path)[0]
    query_request = build_query_request_from_benchmark_case(
        question=case_bundle.inference_case.question,
        evidence=case_bundle.inference_case.evidence,
    )
    chat_client = CapturingStructuredChatClient()
    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=_build_grounding_context_builder(),
        solver=DirectSqlSolver(
            chat_client=chat_client,
            prompt_builder=DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql")),
            model_name="fake-model",
        ),
        escalation_policy=EscalationPolicy(),
        escalation_budget=EscalationBudget(max_escalations=0),
    )

    result = await orchestrator.run(
        query_request=query_request,
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda context, run_id: SolverRequest(
            run_id=run_id,
            query_request=query_request,
            target_dialect="sqlite",
            grounding_context=context,
        ),
        run_id="run-1",
    )

    serialized_orchestration = result.model_dump_json()
    serialized_messages = "\n".join(message["content"] for message in chat_client.messages)
    assert gold_sql not in serialized_orchestration
    assert gold_sql not in serialized_messages


def _build_grounding_context_builder() -> GroundingContextBuilder:
    table = CatalogTable(
        table_fqn="db.main.customers",
        service_name="sqlite",
        database_name="db",
        schema_name="main",
        table_name="customers",
        sql_identifier="customers",
        sql_identifier_source="explicit",
        columns=[
            CatalogColumn(
                column_fqn="db.main.customers.name",
                column_name="name",
                data_type="TEXT",
            )
        ],
    )
    catalog = InMemoryCatalog()
    catalog.upsert_tables([table])
    documents = CatalogSearchDocumentBuilder().build_search_documents(table)
    return GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=SchemaRetriever(InMemorySchemaSearch(documents)),
        authorization_service=AuthorizationService(StaticAccessPolicy()),
    )
