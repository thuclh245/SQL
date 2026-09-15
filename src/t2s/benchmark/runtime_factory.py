from pathlib import Path

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.database import QueryExecutionPolicy
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.orchestration import AdaptiveOrchestrator, EscalationBudget, EscalationPolicy
from t2s.runtime import TextToSqlRuntime
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.solver.chat_client import StructuredChatClient
from t2s.verification import SqlAccessValidator, SqlAstParser, SqlSafetyValidator


class AllTablesBenchmarkAccessPolicy:
    """Benchmark policy granting access to every executable table in one DB."""

    def __init__(self, authorized_resources: list[AuthorizedSqlResource]) -> None:
        self.authorized_resources = authorized_resources

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return list(self.authorized_resources)


def build_bird_runtime_for_database(
    db_id: str,
    db_path: Path,
    tables_json_path: Path,
    chat_client: StructuredChatClient,
    model_name: str,
    prompt_directory: Path,
    query_execution_policy: QueryExecutionPolicy | None = None,
    prompt_version: str = "v001",
) -> TextToSqlRuntime:
    if not db_path.exists():
        raise FileNotFoundError(f"Official SQLite database not found for {db_id}: {db_path}")

    catalog_tables = load_bird_catalog_tables(db_id=db_id, tables_json_path=tables_json_path)
    catalog = InMemoryCatalog()
    catalog.upsert_tables(catalog_tables)

    document_builder = CatalogSearchDocumentBuilder()
    search_documents = [
        document
        for catalog_table in catalog_tables
        for document in document_builder.build_search_documents(catalog_table)
    ]
    schema_retriever = SchemaRetriever(InMemorySchemaSearch(search_documents))

    authorized_resources = [
        AuthorizedSqlResource(
            catalog_fqn=catalog_table.table_fqn,
            sql_identifier=catalog_table.sql_identifier,
        )
        for catalog_table in catalog_tables
        if catalog_table.sql_identifier is not None
    ]
    authorization_service = AuthorizationService(
        AllTablesBenchmarkAccessPolicy(authorized_resources)
    )
    grounding_context_builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=schema_retriever,
        authorization_service=authorization_service,
        grounding_budget=GroundingBudget(),
    )

    solver = DirectSqlSolver(
        chat_client=chat_client,
        prompt_builder=DirectSqlPromptBuilder(
            prompt_directory=prompt_directory,
            prompt_version=prompt_version,
        ),
        model_name=model_name,
    )
    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=grounding_context_builder,
        solver=solver,
        escalation_policy=EscalationPolicy(),
        escalation_budget=EscalationBudget(max_escalations=1),
    )

    return TextToSqlRuntime(
        adaptive_orchestrator=orchestrator,
        sql_access_validator=SqlAccessValidator(authorization_service),
        query_executor=SqliteReadOnlyQueryExecutor(db_path),
        sql_ast_parser=SqlAstParser(),
        sql_safety_validator=SqlSafetyValidator(),
        execution_policy=query_execution_policy
        or QueryExecutionPolicy(maximum_result_rows=1000, statement_timeout_seconds=30),
        default_dialect="sqlite",
    )


def build_query_request_from_benchmark_case(question: str, evidence: str | None) -> QueryRequest:
    question_with_evidence = question
    if evidence:
        question_with_evidence = f"{question}\n\nEvidence: {evidence}"
    return QueryRequest(question=question_with_evidence, database_dialect="sqlite")
