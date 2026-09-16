from pathlib import Path
from typing import Literal

from t2s.benchmark.catalog_loader import load_bird_catalog_tables
from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.database import QueryExecutionPolicy
from t2s.database.sqlite_read_only_query_executor import SqliteReadOnlyQueryExecutor
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.grounding.value_grounding import (
    SqliteValueProbe,
    ValueGrounder,
    ValueGroundingBudget,
)
from t2s.orchestration import AdaptiveOrchestrator, EscalationBudget, EscalationPolicy
from t2s.runtime import TextToSqlRuntime
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.semantics import GroundedSemanticPlanner, SemanticPlanConsistencyChecker
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.solver.chat_client import StructuredChatClient
from t2s.verification import (
    DiagnosticProbeRunner,
    ResultVerifier,
    SqlAccessValidator,
    SqlAstParser,
    SqlSafetyValidator,
)


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
    planner_mode: str = "off",
    result_verifier_enabled: bool = False,
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
        # Probes run against the same database the generated SQL executes on, so
        # observed literals are guaranteed to match at execution time.
        value_grounder=(
            ValueGrounder(value_probe=SqliteValueProbe(db_path), budget=value_grounding_budget)
            if value_grounding_budget is not None
            else None
        ),
    )

    solver = DirectSqlSolver(
        chat_client=chat_client,
        prompt_builder=DirectSqlPromptBuilder(
            prompt_directory=prompt_directory,
            prompt_version=prompt_version,
        ),
        model_name=model_name,
    )

    semantic_planner = None
    if planner_mode == "llm":
        semantic_planner = GroundedSemanticPlanner(
            chat_client=chat_client,
            model_name=model_name,
        )
    elif planner_mode == "deterministic":
        semantic_planner = GroundedSemanticPlanner()

    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=grounding_context_builder,
        solver=solver,
        escalation_policy=EscalationPolicy(
            release_candidates_with_caveats=release_candidates_with_caveats
        ),
        escalation_budget=EscalationBudget(max_escalations=1),
        semantic_planner=semantic_planner,
    )

    access_validator = SqlAccessValidator(authorization_service)
    ast_parser = SqlAstParser()
    safety_validator = SqlSafetyValidator()
    executor = SqliteReadOnlyQueryExecutor(db_path)

    result_verifier = ResultVerifier() if result_verifier_enabled else None
    diagnostic_probe_runner = (
        DiagnosticProbeRunner(
            query_executor=executor,
            sql_ast_parser=ast_parser,
            sql_safety_validator=safety_validator,
            sql_access_validator=access_validator,
        )
        if result_verifier_enabled
        else None
    )
    plan_consistency_checker = (
        SemanticPlanConsistencyChecker()
        if (result_verifier_enabled and semantic_planner is not None)
        else None
    )

    return TextToSqlRuntime(
        adaptive_orchestrator=orchestrator,
        sql_access_validator=access_validator,
        query_executor=executor,
        sql_ast_parser=ast_parser,
        sql_safety_validator=safety_validator,
        execution_policy=query_execution_policy
        or QueryExecutionPolicy(maximum_result_rows=1000, statement_timeout_seconds=30),
        default_dialect="sqlite",
        result_verifier=result_verifier,
        diagnostic_probe_runner=diagnostic_probe_runner,
        plan_consistency_checker=plan_consistency_checker,
    )


BenchmarkEvidenceMode = Literal["inline", "structured"]


def build_query_request_from_benchmark_case(
    question: str,
    evidence: str | None,
    evidence_mode: BenchmarkEvidenceMode = "inline",
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
