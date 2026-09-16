"""Integration tests for the AdaptiveOrchestrator covering all 8 required scenarios.

Cases A-H test the bounded orchestration loop end-to-end using in-memory
catalog, search index, and a fake structured chat client.
"""

from pathlib import Path
from typing import Any

import pytest

from t2s.catalog import (
    CatalogColumn,
    CatalogForeignKey,
    CatalogSearchDocumentBuilder,
    CatalogTable,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import (
    GroundingContext,
    QueryRequest,
)
from t2s.grounding import (
    GroundingBudget,
    GroundingContextBuilder,
    InMemorySchemaSearch,
    SchemaRetriever,
)
from t2s.orchestration import (
    AdaptiveOrchestrator,
    EscalationBudget,
    EscalationPolicy,
    OrchestrationOutcome,
)
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver, SolverRequest
from t2s.solver.solver_response import StructuredChatResponse

# --- Shared test infrastructure ---


class StaticAccessPolicy:
    def __init__(self, authorized_tables: list[CatalogTable]) -> None:
        self.authorized_tables = authorized_tables

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return [
            AuthorizedSqlResource(
                catalog_fqn=table.table_fqn,
                sql_identifier=table.sql_identifier or "unresolved.placeholder",
            )
            for table in self.authorized_tables
        ]


class FakeStructuredChatClient:
    """Fake chat client that returns pre-configured solver responses."""

    def __init__(self, content: dict[str, Any]) -> None:
        self.content = content
        self.call_count = 0

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        self.call_count += 1
        return StructuredChatResponse(
            content=self.content,
            model_name=model_name,
            elapsed_ms=10,
            prompt_tokens=100,
            output_tokens=50,
        )


def _build_customers_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="postgres_prod.warehouse.crm.customers",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="crm",
        table_name="customers",
        sql_identifier="crm.customers",
        description="Customer records",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.crm.customers.customer_id",
                column_name="customer_id",
                data_type="text",
                is_primary_key=True,
            ),
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.crm.customers.is_active",
                column_name="is_active",
                data_type="boolean",
            ),
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.crm.customers.segment",
                column_name="segment",
                data_type="text",
            ),
        ],
        primary_key_column_names=["customer_id"],
    )


def _build_orders_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="postgres_prod.warehouse.finance.orders",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="finance",
        table_name="orders",
        sql_identifier="finance.orders",
        description="Order records with customer revenue",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.finance.orders.order_id",
                column_name="order_id",
                data_type="text",
                is_primary_key=True,
            ),
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.finance.orders.customer_id",
                column_name="customer_id",
                data_type="text",
            ),
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.finance.orders.net_revenue",
                column_name="net_revenue",
                data_type="numeric",
            ),
        ],
        primary_key_column_names=["order_id"],
        foreign_keys=[
            CatalogForeignKey(
                from_table_fqn="postgres_prod.warehouse.finance.orders",
                from_column_names=["customer_id"],
                to_table_fqn="postgres_prod.warehouse.crm.customers",
                to_column_names=["customer_id"],
            )
        ],
    )


def _build_secret_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="postgres_prod.warehouse.secret.payroll",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="secret",
        table_name="payroll",
        sql_identifier="secret.payroll",
        description="Secret employee payroll with salary data",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.secret.payroll.salary",
                column_name="salary",
                data_type="numeric",
            ),
        ],
    )


def _build_unresolved_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="postgres_prod.warehouse.marketing.leads",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="marketing",
        table_name="leads",
        sql_identifier=None,
        description="Marketing leads without SQL identifier",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.marketing.leads.lead_id",
                column_name="lead_id",
                data_type="text",
            ),
        ],
    )


def _build_clean_solver_response(sql_identifier: str = "crm.customers") -> dict[str, Any]:
    return {
        "sql": f"SELECT * FROM {sql_identifier}",
        "dialect": "postgres",
        "referenced_tables": [sql_identifier],
        "referenced_columns": [],
        "expected_columns": [],
        "assumptions": [],
        "unresolved": [],
    }


def _build_unresolved_solver_response() -> dict[str, Any]:
    return {
        "sql": "SELECT * FROM crm.customers",
        "dialect": "postgres",
        "referenced_tables": ["crm.customers"],
        "referenced_columns": [],
        "expected_columns": [],
        "assumptions": [],
        "unresolved": ["Cannot determine join condition for missing table"],
    }


def _build_schema_reference_mismatch_response() -> dict[str, Any]:
    return {
        "sql": "SELECT * FROM crm.customers JOIN finance.orders ON 1=1",
        "dialect": "postgres",
        "referenced_tables": ["crm.customers", "finance.orders"],
        "referenced_columns": [],
        "expected_columns": [],
        "assumptions": [],
        "unresolved": [],
    }


def _build_orchestrator(
    catalog_tables: list[CatalogTable],
    authorized_tables: list[CatalogTable],
    solver_response: dict[str, Any],
    grounding_budget: GroundingBudget | None = None,
    escalation_budget: EscalationBudget | None = None,
) -> tuple[AdaptiveOrchestrator, FakeStructuredChatClient]:
    catalog = InMemoryCatalog()
    catalog.upsert_tables(catalog_tables)

    search_document_builder = CatalogSearchDocumentBuilder()
    search_documents = [
        doc
        for table in catalog_tables
        for doc in search_document_builder.build_search_documents(table)
    ]
    schema_retriever = SchemaRetriever(InMemorySchemaSearch(search_documents))
    authorization_service = AuthorizationService(StaticAccessPolicy(authorized_tables))

    grounding_builder = GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=schema_retriever,
        authorization_service=authorization_service,
        grounding_budget=grounding_budget,
    )

    fake_client = FakeStructuredChatClient(solver_response)
    solver = DirectSqlSolver(
        chat_client=fake_client,
        prompt_builder=DirectSqlPromptBuilder(prompt_directory=Path("prompts/direct_sql")),
        model_name="test-model",
    )

    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=grounding_builder,
        solver=solver,
        escalation_policy=EscalationPolicy(),
        escalation_budget=escalation_budget,
    )

    return orchestrator, fake_client


def _build_solver_request_factory() -> type[
    object
]:  # Returns a callable, typed as object for simplicity
    def factory(grounding_context: GroundingContext, run_id: str) -> SolverRequest:
        return SolverRequest(
            run_id=run_id,
            query_request=QueryRequest(question="test"),
            target_dialect="postgres",
            grounding_context=grounding_context,
        )

    return factory  # type: ignore[return-value]


# =============================================================================
# Case A: No escalation — good grounding + solver completes normally
# =============================================================================


@pytest.mark.anyio
async def test_case_a_no_escalation_good_grounding_and_solver() -> None:
    customers = _build_customers_table()
    orchestrator, fake_client = _build_orchestrator(
        catalog_tables=[customers],
        authorized_tables=[customers],
        solver_response=_build_clean_solver_response(),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List active customers"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-a",
    )

    assert result.outcome == OrchestrationOutcome.BASELINE_SUCCESS
    assert result.sql_candidate is not None
    assert result.trace.total_grounding_calls == 1
    assert result.trace.total_solver_calls == 1
    assert len(result.trace.escalation_records) == 0
    assert fake_client.call_count == 1


# =============================================================================
# Case B: Grounding incomplete — recoverable grounding issues trigger escalation
# =============================================================================


@pytest.mark.anyio
async def test_case_b_grounding_incomplete_triggers_escalated_regrounding() -> None:
    """When solver reports unresolved items, escalation rgrounds with expanded budget."""
    customers = _build_customers_table()
    orchestrator, fake_client = _build_orchestrator(
        catalog_tables=[customers],
        authorized_tables=[customers],
        solver_response=_build_unresolved_solver_response(),
        grounding_budget=GroundingBudget(max_hydrated_tables=1, max_total_columns=3),
        escalation_budget=EscalationBudget(
            max_escalations=1, grounding_table_delta=2, grounding_column_delta=6
        ),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List active customers"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-b",
    )

    # Escalation should have been attempted (solver had unresolved items).
    assert result.trace.total_grounding_calls == 2
    assert len(result.trace.escalation_records) == 1
    assert result.trace.escalation_records[0].reason.value == "solver_unresolved"


# =============================================================================
# Case C: Solver unresolved — escalate only if new context can be obtained
# =============================================================================


@pytest.mark.anyio
async def test_case_c_solver_unresolved_with_schema_mismatch() -> None:
    """Solver references tables not in grounding — triggers reground."""
    customers = _build_customers_table()
    orders = _build_orders_table()
    orchestrator, fake_client = _build_orchestrator(
        catalog_tables=[customers, orders],
        authorized_tables=[customers, orders],
        solver_response=_build_schema_reference_mismatch_response(),
        grounding_budget=GroundingBudget(max_hydrated_tables=1, max_total_columns=5),
        escalation_budget=EscalationBudget(max_escalations=1, grounding_table_delta=4),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="Customer revenue"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="Customer revenue"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-c",
    )

    # Should attempt escalation due to schema reference mismatch.
    assert result.trace.total_grounding_calls == 2
    assert len(result.trace.escalation_records) == 1


# =============================================================================
# Case D: Same context cannot improve — no retry when context unchanged
# =============================================================================


@pytest.mark.anyio
async def test_case_d_same_context_prevents_meaningless_retry() -> None:
    """When expanded grounding produces identical context, do not regenerate."""
    customers = _build_customers_table()
    orchestrator, fake_client = _build_orchestrator(
        catalog_tables=[customers],
        authorized_tables=[customers],
        solver_response=_build_unresolved_solver_response(),
        # Budget already large enough — expanding won't find new tables.
        grounding_budget=GroundingBudget(
            max_hydrated_tables=50, max_total_columns=200, max_relationships=50
        ),
        escalation_budget=EscalationBudget(max_escalations=1),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List active customers"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-d",
    )

    # Regrounding attempted but context unchanged → UNRESOLVED, no second solver call.
    assert result.outcome == OrchestrationOutcome.UNRESOLVED
    assert result.trace.total_grounding_calls == 2
    assert result.trace.total_solver_calls == 1  # Only baseline, no escalated generation
    assert len(result.trace.escalation_records) == 1
    assert result.trace.escalation_records[0].outcome == "context_unchanged"


# =============================================================================
# Case E: Escalation budget exhausted — stop deterministically
# =============================================================================


@pytest.mark.anyio
async def test_case_e_budget_exhausted_stops_deterministically() -> None:
    customers = _build_customers_table()
    orchestrator, fake_client = _build_orchestrator(
        catalog_tables=[customers],
        authorized_tables=[customers],
        solver_response=_build_unresolved_solver_response(),
        escalation_budget=EscalationBudget(max_escalations=0),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List active customers"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-e",
    )

    # Budget = 0, so no escalation despite solver having unresolved items.
    assert result.outcome == OrchestrationOutcome.BASELINE_SUCCESS
    assert result.trace.total_grounding_calls == 1
    assert result.trace.total_solver_calls == 1
    assert len(result.trace.escalation_records) == 0


# =============================================================================
# Case F: Unauthorized related table — never included during escalation
# =============================================================================


@pytest.mark.anyio
async def test_case_f_unauthorized_table_never_included_in_escalation() -> None:
    customers = _build_customers_table()
    secret = _build_secret_table()
    orchestrator, fake_client = _build_orchestrator(
        catalog_tables=[customers, secret],
        authorized_tables=[customers],  # secret NOT authorized
        solver_response=_build_clean_solver_response(),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="customers and payroll salary"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="customers and payroll salary"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-f",
    )

    # Secret table must never appear in grounding context regardless of escalation.
    all_table_fqns = {table.fqn for table in result.grounding_context.tables}
    assert "postgres_prod.warehouse.secret.payroll" not in all_table_fqns
    assert "secret.payroll" not in str(result.grounding_context.model_dump())


# =============================================================================
# Case G: Missing sql_identifier — never fabricated
# =============================================================================


@pytest.mark.anyio
async def test_case_g_missing_sql_identifier_is_never_fabricated() -> None:
    leads = _build_unresolved_table()
    orchestrator, fake_client = _build_orchestrator(
        catalog_tables=[leads],
        authorized_tables=[leads],
        solver_response=_build_clean_solver_response(),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="List marketing leads"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List marketing leads"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-g",
    )

    # No tables in context (sql_identifier is None), should be UNRESOLVED.
    assert result.outcome == OrchestrationOutcome.UNRESOLVED
    assert len(result.grounding_context.tables) == 0
    assert any(
        issue.code == "unresolved_sql_identifier" for issue in result.grounding_context.unresolved
    )
    # Must not attempt escalation for unresolvable identifier issues.
    assert len(result.trace.escalation_records) == 0


# =============================================================================
# Case H: Relationship ambiguity — recorded instead of generic retry
# =============================================================================


@pytest.mark.anyio
async def test_case_h_relationship_ambiguity_is_recorded() -> None:
    """Multiple tables with no FK relationships triggers ambiguity detection."""
    # Create two isolated tables (no FKs between them).
    customers = CatalogTable(
        table_fqn="postgres_prod.warehouse.crm.customers",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="crm",
        table_name="customers",
        sql_identifier="crm.customers",
        description="Customer records",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.crm.customers.customer_id",
                column_name="customer_id",
                data_type="text",
                is_primary_key=True,
            ),
        ],
        primary_key_column_names=["customer_id"],
    )
    products = CatalogTable(
        table_fqn="postgres_prod.warehouse.catalog.products",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="catalog",
        table_name="products",
        sql_identifier="catalog.products",
        description="Product catalog",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.catalog.products.product_id",
                column_name="product_id",
                data_type="text",
                is_primary_key=True,
            ),
        ],
        primary_key_column_names=["product_id"],
    )
    orchestrator, _ = _build_orchestrator(
        catalog_tables=[customers, products],
        authorized_tables=[customers, products],
        solver_response={
            "sql": "SELECT * FROM crm.customers, catalog.products",
            "dialect": "postgres",
            "referenced_tables": ["crm.customers", "catalog.products"],
            "referenced_columns": [],
            "expected_columns": [],
            "assumptions": [],
            "unresolved": [],
        },
        grounding_budget=GroundingBudget(max_hydrated_tables=2, max_total_columns=10),
        escalation_budget=EscalationBudget(max_escalations=1),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="customers and products"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="customers and products"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="case-h",
    )

    # Should detect relationship ambiguity and attempt escalation.
    assert result.trace.total_grounding_calls == 2
    assert len(result.trace.escalation_records) == 1
    assert result.trace.escalation_records[0].reason.value == "relationship_ambiguity"


# =============================================================================
# Orchestration trace is complete and reconstructable
# =============================================================================


@pytest.mark.anyio
async def test_orchestration_trace_records_complete_decision_evidence() -> None:
    customers = _build_customers_table()
    orchestrator, _ = _build_orchestrator(
        catalog_tables=[customers],
        authorized_tables=[customers],
        solver_response=_build_clean_solver_response(),
    )

    result = await orchestrator.run(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List active customers"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="trace-test",
    )

    trace = result.trace
    assert trace.run_id == "trace-test"
    assert trace.outcome == OrchestrationOutcome.BASELINE_SUCCESS
    assert trace.total_grounding_calls >= 1
    assert trace.total_solver_calls >= 1
    assert isinstance(trace.baseline_table_fqns, list)
    assert isinstance(trace.baseline_unresolved_codes, list)
    assert isinstance(trace.baseline_solver_unresolved, list)
    assert isinstance(trace.final_table_fqns, list)
