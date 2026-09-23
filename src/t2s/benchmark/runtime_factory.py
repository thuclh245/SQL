from collections.abc import Callable
from pathlib import Path
from typing import Literal

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import GroundingContext, QueryRequest
from t2s.contracts.sql_candidate import SupportedSqlDialect
from t2s.database import QueryExecutionPolicy
from t2s.database.query_executor_port import QueryExecutorPort
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.grounding import GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.grounding.value_grounding import (
    SqliteValueProbe,
    ValueGrounder,
    ValueGroundingBudget,
)
from t2s.grounding.value_grounding.value_probe_port import ValueProbePort
from t2s.runtime import TextToSqlRuntime
from t2s.runtime.runtime_assembly import assemble_semantic_runtime
from t2s.runtime.runtime_profile import PlannerMode, SemanticRuntimeProfile
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver.chat_client import StructuredChatClient


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
    value_grounding_budget: ValueGroundingBudget | None = None,
    release_candidates_with_caveats: bool = True,
    planner_mode: PlannerMode = "off",
    result_verifier_enabled: bool = True,
    runtime_profile: SemanticRuntimeProfile | None = None,
    schema_serializer: Callable[[GroundingContext], str] | None = None,
    query_executor: QueryExecutorPort | None = None,
    value_probe: ValueProbePort | None = None,
    default_dialect: SupportedSqlDialect = "sqlite",
) -> TextToSqlRuntime:
    # db_path chỉ bắt buộc khi chạy trên SQLite; engine khác tự mang executor
    # và probe của mình, lúc đó không có file nào để kiểm tra.
    if query_executor is None and not db_path.exists():
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
    profile = runtime_profile or SemanticRuntimeProfile(
        model_name=model_name,
        prompt_version=prompt_version,
        value_linking_enabled=value_grounding_budget is not None,
        release_candidates_with_caveats=release_candidates_with_caveats,
        planner_mode=planner_mode,
        result_verifier_enabled=result_verifier_enabled,
    )
    if profile.value_linking_enabled != (value_grounding_budget is not None):
        raise ValueError("runtime_profile.value_linking_enabled must match value_grounding_budget.")
    grounding_context_builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=schema_retriever,
        authorization_service=authorization_service,
        grounding_budget=profile.grounding_budget,
        # Probes run against the same database the generated SQL executes on, so
        # observed literals are guaranteed to match at execution time.
        value_grounder=(
            ValueGrounder(
                value_probe=value_probe or SqliteValueProbe(db_path),
                budget=value_grounding_budget,
            )
            if value_grounding_budget is not None
            else None
        ),
    )

    executor = query_executor or SqliteReadOnlyQueryExecutor(db_path)
    return assemble_semantic_runtime(
        grounding_context_builder=grounding_context_builder,
        authorization_service=authorization_service,
        query_executor=executor,
        chat_client=chat_client,
        prompt_directory=prompt_directory,
        execution_policy=query_execution_policy
        or QueryExecutionPolicy(maximum_result_rows=1000, statement_timeout_seconds=30),
        default_dialect=default_dialect,
        profile=profile,
        schema_serializer=schema_serializer,
    )


BenchmarkEvidenceMode = Literal["none", "inline", "structured"]


def build_query_request_from_benchmark_case(
    question: str,
    evidence: str | None,
    evidence_mode: BenchmarkEvidenceMode = "none",
) -> QueryRequest:
    """Build a request from a benchmark case, keeping evidence in the harness.

    Benchmark evidence is dataset-supplied context and reaches the solver only
    through this evaluation-layer function. Production requests construct
    ``QueryRequest`` themselves and leave ``evidence`` empty unless a governed
    source fills it, so no benchmark text can reach a production prompt.

    ``evidence_mode`` is explicit rather than implied because it changes what the
    model sees: ``inline`` reproduces the historical runs that appended evidence
    to the question text, while ``structured`` carries it as its own field for
    prompt versions that render an evidence block. Comparing the two is only
    meaningful if the choice is recorded per run.
    """
    if not evidence:
        return QueryRequest(question=question, database_dialect="sqlite")
    if evidence_mode == "none":
        return QueryRequest(question=question, database_dialect="sqlite")
    if evidence_mode == "structured":
        return QueryRequest(
            question=question,
            evidence=[evidence],
            database_dialect="sqlite",
        )
    return QueryRequest(
        question=f"{question}\n\nEvidence: {evidence}",
        database_dialect="sqlite",
    )
