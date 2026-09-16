from pathlib import Path

from t2s.catalog import (
    CatalogSearchDocumentBuilder,
    CatalogTable,
    MetadataProviderFactory,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.configuration import Settings
from t2s.database import (
    DatabaseReadinessInspectorPort,
    PostgresDatabaseReadinessInspector,
    PostgresReadOnlyQueryExecutor,
    QueryExecutionPolicy,
    QueryExecutorPort,
    SqliteDatabaseReadinessInspector,
    SqliteReadOnlyQueryExecutor,
)
from t2s.errors import ConfigurationError
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.grounding.value_grounding import (
    PostgresValueProbe,
    SqliteValueProbe,
    ValueGrounder,
    ValueGroundingBudget,
    ValueProbePort,
)
from t2s.integrations.vllm import VllmChatClient
from t2s.orchestration import AdaptiveOrchestrator, EscalationBudget, EscalationPolicy
from t2s.runtime import TextToSqlRuntime
from t2s.runtime.runtime_contracts import ValidatorMode
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.semantics import GroundedSemanticPlanner, SemanticPlanConsistencyChecker
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.verification import (
    DiagnosticProbeRunner,
    ResultVerifier,
    SqlAccessValidator,
    SqlAstParser,
    SqlSafetyValidator,
)


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
    if catalog_tables_path is None and settings.metadata_provider != "postgres":
        raise ConfigurationError(
            "runtime_catalog_tables_path is required when the API runtime is configured."
        )
    if settings.vllm_base_url is None:
        raise ConfigurationError("vllm_base_url is required when API runtime is configured.")

    query_executor = _build_query_executor(settings)
    _verify_execution_database_readiness(settings)

    provider = MetadataProviderFactory.create_provider(settings)
    catalog_tables = provider.fetch_metadata()
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
        grounding_budget=GroundingBudget(small_db_threshold=10),
        value_grounder=_build_value_grounder(settings),
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
    semantic_planner = GroundedSemanticPlanner(
        chat_client=chat_client,
        model_name=settings.llm_model_name,
    )
    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=grounding_context_builder,
        solver=solver,
        escalation_policy=EscalationPolicy(
            release_candidates_with_caveats=settings.release_candidates_with_caveats
        ),
        escalation_budget=EscalationBudget(max_escalations=1),
        semantic_planner=semantic_planner,
    )

    access_validator = SqlAccessValidator(authorization_service)
    ast_parser = SqlAstParser()
    safety_validator = SqlSafetyValidator()

    diagnostic_probe_runner = DiagnosticProbeRunner(
        query_executor=query_executor,
        sql_ast_parser=ast_parser,
        sql_safety_validator=safety_validator,
        sql_access_validator=access_validator,
    )

    return TextToSqlRuntime(
        adaptive_orchestrator=orchestrator,
        sql_access_validator=access_validator,
        query_executor=query_executor,
        sql_ast_parser=ast_parser,
        sql_safety_validator=safety_validator,
        execution_policy=QueryExecutionPolicy(
            maximum_result_rows=settings.database_max_result_rows,
            statement_timeout_seconds=settings.database_statement_timeout_seconds,
        ),
        default_dialect=settings.runtime_default_dialect,
        validator_mode=ValidatorMode(settings.validator_mode),
        plan_consistency_checker=SemanticPlanConsistencyChecker(),
        result_verifier=ResultVerifier(),
        diagnostic_probe_runner=diagnostic_probe_runner,
    )


def _verify_execution_database_readiness(settings: Settings) -> None:
    """Fail startup when the configured execution database holds no data at all.

    Without this the runtime starts cleanly, answers every request, and returns
    NULL for all of them — a failure mode that looks like poor model accuracy
    rather than like misconfiguration.
    """
    if not settings.runtime_require_populated_execution_database:
        return
    inspector = _build_readiness_inspector(settings)
    if inspector is None:
        return
    report = inspector.inspect_readiness(settings.runtime_readiness_relation_sample_size)
    if report.is_ready:
        return
    raise ConfigurationError(
        f"Configured execution database is not queryable ({report.status.value}): "
        f"{report.detail} Point the runtime at a populated database, or set "
        "RUNTIME_REQUIRE_POPULATED_EXECUTION_DATABASE=false to accept it."
    )


def _build_readiness_inspector(settings: Settings) -> DatabaseReadinessInspectorPort | None:
    """Return the inspector for the configured dialect, or None when unsupported."""
    dialect = settings.runtime_default_dialect
    if dialect == "sqlite" and settings.runtime_sqlite_database_path is not None:
        return SqliteDatabaseReadinessInspector(settings.runtime_sqlite_database_path)
    if dialect == "postgres" and settings.runtime_database_url is not None:
        return PostgresDatabaseReadinessInspector(
            database_url=settings.runtime_database_url,
            connect_timeout_seconds=settings.runtime_database_connect_timeout_seconds,
        )
    return None


def _build_value_grounder(settings: Settings) -> ValueGrounder | None:
    """Build a value grounder for the configured dialect, or None when unavailable.

    Returning None leaves ``value_bindings`` empty rather than silently claiming
    value evidence the deployment cannot actually produce.
    """
    if not settings.value_grounding_enabled:
        return None
    value_probe = _build_value_probe(settings)
    if value_probe is None:
        return None
    return ValueGrounder(
        value_probe=value_probe,
        budget=ValueGroundingBudget(
            max_value_columns=settings.max_value_columns,
            max_value_candidates_per_column=settings.max_value_candidates_per_column,
            value_lookup_timeout_ms=settings.value_lookup_timeout_ms,
            enumerate_low_cardinality_domains=settings.enumerate_low_cardinality_domains,
            max_enumerated_domain_values=settings.max_enumerated_domain_values,
        ),
    )


def _build_value_probe(settings: Settings) -> ValueProbePort | None:
    dialect = settings.runtime_default_dialect
    if dialect == "sqlite" and settings.runtime_sqlite_database_path is not None:
        return SqliteValueProbe(settings.runtime_sqlite_database_path)
    if dialect == "postgres" and settings.runtime_database_url is not None:
        return PostgresValueProbe(
            database_url=settings.runtime_database_url,
            connect_timeout_seconds=settings.runtime_database_connect_timeout_seconds,
        )
    return None


def _is_runtime_requested(settings: Settings) -> bool:
    """A runtime is wired only once the operator points at a catalog or a database."""
    return any(
        (
            settings.runtime_catalog_tables_path is not None,
            settings.runtime_sqlite_database_path is not None,
            settings.runtime_database_url is not None,
            settings.metadata_provider is not None,
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
    """Compatibility loader routing through StaticMetadataProvider."""
    from t2s.catalog.static_metadata_provider import StaticMetadataProvider

    provider = StaticMetadataProvider(
        catalog_tables_path=catalog_tables_path,
        database_id=settings.runtime_catalog_database_id,
    )
    return provider.fetch_metadata()
