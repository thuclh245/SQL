import json
from pathlib import Path

from t2s.catalog import CatalogSearchDocumentBuilder, CatalogTable
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.catalog.schema_manifest_loader import load_catalog_tables_from_manifest
from t2s.configuration import Settings
from t2s.database import (
    PostgresReadOnlyQueryExecutor,
    QueryExecutionPolicy,
    QueryExecutorPort,
    SqliteReadOnlyQueryExecutor,
)
from t2s.errors import ConfigurationError
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.integrations.vllm import VllmChatClient
from t2s.orchestration import AdaptiveOrchestrator, EscalationBudget, EscalationPolicy
from t2s.runtime import TextToSqlRuntime
from t2s.runtime.runtime_contracts import ValidatorMode
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.verification import SqlAccessValidator, SqlAstParser, SqlSafetyValidator


class AllTablesRuntimeAccessPolicy:
    """Initial API policy granting runtime access to every configured table."""

    def __init__(self, authorized_resources: list[AuthorizedSqlResource]) -> None:
        self.authorized_resources = authorized_resources

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return list(self.authorized_resources)


def build_runtime_from_settings(settings: Settings) -> TextToSqlRuntime | None:
    catalog_tables_path = settings.runtime_catalog_tables_path
    if not _is_runtime_requested(settings):
        return None
    if catalog_tables_path is None:
        raise ConfigurationError(
            "runtime_catalog_tables_path is required when the API runtime is configured."
        )
    if settings.vllm_base_url is None:
        raise ConfigurationError("vllm_base_url is required when API runtime is configured.")

    query_executor = _build_query_executor(settings)

    catalog_tables = _load_catalog_tables(settings, catalog_tables_path)
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
    authorization_service = AuthorizationService(AllTablesRuntimeAccessPolicy(authorized_resources))
    grounding_context_builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=schema_retriever,
        authorization_service=authorization_service,
        grounding_budget=GroundingBudget(),
    )

    chat_client = VllmChatClient(
        base_url=settings.vllm_base_url,
        api_key=settings.llm_api_key,
        request_timeout_seconds=settings.llm_request_timeout_seconds,
    )
    solver = DirectSqlSolver(
        chat_client=chat_client,
        prompt_builder=DirectSqlPromptBuilder(
            prompt_directory=settings.runtime_prompt_directory,
            prompt_version=settings.runtime_prompt_version,
        ),
        model_name=settings.llm_model_name,
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
        query_executor=query_executor,
        sql_ast_parser=SqlAstParser(),
        sql_safety_validator=SqlSafetyValidator(),
        execution_policy=QueryExecutionPolicy(
            maximum_result_rows=settings.database_max_result_rows,
            statement_timeout_seconds=settings.database_statement_timeout_seconds,
        ),
        default_dialect=settings.runtime_default_dialect,
        validator_mode=ValidatorMode(settings.validator_mode),
    )


def _is_runtime_requested(settings: Settings) -> bool:
    """A runtime is wired only once the operator points at a catalog or a database."""
    return any(
        (
            settings.runtime_catalog_tables_path is not None,
            settings.runtime_sqlite_database_path is not None,
            settings.runtime_database_url is not None,
        )
    )


def _build_query_executor(settings: Settings) -> QueryExecutorPort:
    """Pick the executor for the configured dialect, failing closed on anything else.

    A missing or unsupported configuration raises: the runtime never silently falls
    back to another dialect's database.
    """
    dialect = settings.runtime_default_dialect
    if dialect == "sqlite":
        if settings.runtime_sqlite_database_path is None:
            raise ConfigurationError(
                "runtime_sqlite_database_path is required for the sqlite dialect."
            )
        return SqliteReadOnlyQueryExecutor(settings.runtime_sqlite_database_path)
    if dialect == "postgres":
        if settings.runtime_database_url is None:
            raise ConfigurationError("runtime_database_url is required for the postgres dialect.")
        return PostgresReadOnlyQueryExecutor(
            database_url=settings.runtime_database_url,
            connect_timeout_seconds=settings.runtime_database_connect_timeout_seconds,
        )
    raise ConfigurationError(f"No read-only query executor is implemented for dialect '{dialect}'.")


def _load_catalog_tables(settings: Settings, catalog_tables_path: Path) -> list[CatalogTable]:
    if settings.runtime_catalog_database_id:
        return load_catalog_tables_from_manifest(
            database_id=settings.runtime_catalog_database_id,
            manifest_path=catalog_tables_path,
        )

    payload = json.loads(catalog_tables_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ConfigurationError("runtime_catalog_tables_path must contain a JSON list.")
    return [CatalogTable.model_validate(item) for item in payload]
