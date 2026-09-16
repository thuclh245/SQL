from t2s.catalog import (
    CatalogColumn,
    CatalogForeignKey,
    CatalogSearchDocumentBuilder,
    CatalogTable,
)
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.contracts import QueryRequest
from t2s.evaluation import GroundingBenchmarkCase, GroundingEvaluator
from t2s.grounding import (
    GroundingBudget,
    GroundingContextBuilder,
    InMemorySchemaSearch,
    RetrievalRanker,
    SchemaRetriever,
)
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity


class StaticAccessPolicy:
    def __init__(self, catalog_tables: list[CatalogTable]) -> None:
        self.catalog_tables = catalog_tables

    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return [
            AuthorizedSqlResource(
                catalog_fqn=catalog_table.table_fqn,
                sql_identifier=catalog_table.sql_identifier or "unresolved.placeholder",
            )
            for catalog_table in self.catalog_tables
        ]


def test_search_candidate_retrieval_records_matched_fields() -> None:
    customers_table = build_customers_table()
    schema_retriever = build_schema_retriever([customers_table])

    schema_candidates = schema_retriever.retrieve_schema_candidates(
        question="List active customers",
        allowed_table_fqns={customers_table.table_fqn},
        limit=10,
    )

    assert [candidate.table_fqn for candidate in schema_candidates]
    assert any(candidate.resource_type == "table" for candidate in schema_candidates)
    assert any("column_name" in candidate.matched_fields for candidate in schema_candidates)


def test_ranking_preserves_duplicate_short_table_fqns() -> None:
    active_orders_table = build_orders_table()
    archived_orders_table = CatalogTable(
        table_fqn="postgres_prod.warehouse.archive.orders",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="archive",
        table_name="orders",
        sql_identifier="archive.orders",
        description="Archived historical orders",
    )
    schema_candidates = build_schema_retriever(
        [active_orders_table, archived_orders_table],
    ).retrieve_schema_candidates(
        question="orders revenue",
        allowed_table_fqns={active_orders_table.table_fqn, archived_orders_table.table_fqn},
        limit=10,
    )

    ranked_tables = RetrievalRanker().rank_table_candidates(schema_candidates, max_tables=10)

    assert {ranked_table.table_fqn for ranked_table in ranked_tables} == {
        active_orders_table.table_fqn,
        archived_orders_table.table_fqn,
    }


def test_grounding_context_filters_unauthorized_tables_before_output() -> None:
    customers_table = build_customers_table()
    secret_payroll_table = CatalogTable(
        table_fqn="postgres_prod.warehouse.secret.payroll",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="secret",
        table_name="payroll",
        sql_identifier="secret.payroll",
        description="Sensitive employee salaries",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.secret.payroll.salary",
                column_name="salary",
                data_type="numeric",
            )
        ],
    )
    grounding_builder = build_grounding_builder(
        catalog_tables=[customers_table, secret_payroll_table],
        authorized_tables=[customers_table],
    )

    grounding_context = grounding_builder.build_grounding_context(
        QueryRequest(question="customers and payroll salary"),
        UserIdentity(user_id="analyst"),
    )

    assert [table_context.fqn for table_context in grounding_context.tables] == [
        customers_table.table_fqn
    ]
    assert "secret.payroll" not in str(grounding_context.model_dump())


def test_grounding_hydrates_canonical_catalog_and_selects_bounded_columns() -> None:
    customers_table = build_customers_table()
    grounding_builder = build_grounding_builder(
        catalog_tables=[customers_table],
        authorized_tables=[customers_table],
        grounding_budget=GroundingBudget(max_columns_per_table=2, max_total_columns=2),
    )

    grounding_context = grounding_builder.build_grounding_context(
        QueryRequest(question="List active customers"),
        UserIdentity(user_id="analyst"),
    )

    assert grounding_context.tables[0].sql_identifier == "crm.customers"
    assert [column.name for column in grounding_context.tables[0].columns] == [
        "customer_id",
        "is_active",
    ]
    assert grounding_context.retrieval_signals["selected_column_count"] == 2.0


def test_relationship_expansion_discovers_outgoing_fk_and_keeps_join_columns() -> None:
    orders_table = build_orders_table()
    customers_table = build_customers_table()
    grounding_builder = build_grounding_builder(
        catalog_tables=[orders_table, customers_table],
        authorized_tables=[orders_table, customers_table],
    )

    grounding_context = grounding_builder.build_grounding_context(
        QueryRequest(question="Revenue by customer"),
        UserIdentity(user_id="analyst"),
    )

    selected_tables = {
        table_context.fqn: table_context for table_context in grounding_context.tables
    }
    assert orders_table.table_fqn in selected_tables
    assert customers_table.table_fqn in selected_tables
    order_column_names = {column.name for column in selected_tables[orders_table.table_fqn].columns}
    assert "customer_id" in order_column_names
    assert selected_tables[orders_table.table_fqn].relationships[0].from_columns == ["customer_id"]


def test_relationship_expansion_discovers_incoming_fk() -> None:
    orders_table = build_orders_table()
    customers_table = build_customers_table()
    grounding_builder = build_grounding_builder(
        catalog_tables=[orders_table, customers_table],
        authorized_tables=[orders_table, customers_table],
    )

    grounding_context = grounding_builder.build_grounding_context(
        QueryRequest(question="Customer revenue"),
        UserIdentity(user_id="analyst"),
    )

    selected_tables = {table_context.fqn for table_context in grounding_context.tables}
    assert orders_table.table_fqn in selected_tables
    assert customers_table.table_fqn in selected_tables


def test_composite_fk_relationship_evidence_is_lossless() -> None:
    order_lines_table = build_order_lines_table()
    orders_table = build_orders_table()
    grounding_builder = build_grounding_builder(
        catalog_tables=[order_lines_table, orders_table],
        authorized_tables=[order_lines_table, orders_table],
    )

    grounding_context = grounding_builder.build_grounding_context(
        QueryRequest(question="Order line revenue by order"),
        UserIdentity(user_id="analyst"),
    )

    relationships = [
        relationship
        for table_context in grounding_context.tables
        for relationship in table_context.relationships
        if relationship.from_table_fqn == order_lines_table.table_fqn
    ]
    assert relationships[0].from_columns == ["order_id", "line_number"]
    assert relationships[0].to_columns == ["order_id", "line_number"]


def test_relevant_unresolved_sql_identifier_is_reported_not_executed() -> None:
    leads_table = CatalogTable(
        table_fqn="postgres_prod.warehouse.marketing.leads",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="marketing",
        table_name="leads",
        sql_identifier=None,
        description="Marketing leads",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.marketing.leads.lead_id",
                column_name="lead_id",
                data_type="text",
            )
        ],
    )
    grounding_builder = build_grounding_builder(
        catalog_tables=[leads_table],
        authorized_tables=[leads_table],
    )

    grounding_context = grounding_builder.build_grounding_context(
        QueryRequest(question="List marketing leads"),
        UserIdentity(user_id="analyst"),
    )

    assert grounding_context.tables == []
    assert grounding_context.unresolved[0].code == "unresolved_sql_identifier"


def test_vietnamese_and_english_evaluation_fixture_measures_recall() -> None:
    orders_table = build_orders_table()
    customers_table = build_customers_table()
    grounding_builder = build_grounding_builder(
        catalog_tables=[orders_table, customers_table],
        authorized_tables=[orders_table, customers_table],
    )
    evaluation_result = GroundingEvaluator().evaluate_grounding_cases(
        benchmark_cases=[
            GroundingBenchmarkCase(
                case_id="english-single-table",
                question="List active customers",
                expected_table_fqns=frozenset({customers_table.table_fqn}),
                expected_column_fqns=frozenset(
                    {
                        f"{customers_table.table_fqn}.customer_id",
                        f"{customers_table.table_fqn}.is_active",
                    }
                ),
                locale="en",
            ),
            GroundingBenchmarkCase(
                case_id="vietnamese-join",
                question="Doanh thu theo khách hàng",
                expected_table_fqns=frozenset({orders_table.table_fqn, customers_table.table_fqn}),
                expected_column_fqns=frozenset(
                    {
                        f"{orders_table.table_fqn}.net_revenue",
                        f"{orders_table.table_fqn}.customer_id",
                        f"{customers_table.table_fqn}.customer_id",
                    }
                ),
                locale="vi",
            ),
        ],
        user_identity=UserIdentity(user_id="analyst"),
        build_grounding_context=lambda request, identity: grounding_builder.build_grounding_context(
            request,
            identity,
        ),
    )

    assert evaluation_result.case_count == 2
    assert evaluation_result.table_recall_at_k == 1.0
    assert evaluation_result.column_recall_at_k == 1.0
    assert evaluation_result.average_selected_tables >= 1.0


def build_grounding_builder(
    catalog_tables: list[CatalogTable],
    authorized_tables: list[CatalogTable],
    grounding_budget: GroundingBudget | None = None,
) -> GroundingContextBuilder:
    catalog = InMemoryCatalog()
    catalog.upsert_tables(catalog_tables)
    return GroundingContextBuilder(
        catalog=catalog,
        schema_retriever=build_schema_retriever(catalog_tables),
        authorization_service=AuthorizationService(StaticAccessPolicy(authorized_tables)),
        grounding_budget=grounding_budget,
    )


def build_schema_retriever(catalog_tables: list[CatalogTable]) -> SchemaRetriever:
    search_document_builder = CatalogSearchDocumentBuilder()
    search_documents = [
        search_document
        for catalog_table in catalog_tables
        for search_document in search_document_builder.build_search_documents(catalog_table)
    ]
    return SchemaRetriever(InMemorySchemaSearch(search_documents))


def build_customers_table() -> CatalogTable:
    return CatalogTable(
        table_fqn="postgres_prod.warehouse.crm.customers",
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="crm",
        table_name="customers",
        sql_identifier="crm.customers",
        description="Customer dimension. Khách hàng and customer accounts.",
        columns=[
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.crm.customers.customer_id",
                column_name="customer_id",
                data_type="text",
                description="Customer key",
                is_primary_key=True,
                ordinal_position=1,
            ),
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.crm.customers.is_active",
                column_name="is_active",
                data_type="boolean",
                description="Active customer flag",
                ordinal_position=2,
            ),
            CatalogColumn(
                column_fqn="postgres_prod.warehouse.crm.customers.segment",
                column_name="segment",
                data_type="text",
                description="Customer segment",
                ordinal_position=3,
            ),
        ],
        primary_key_column_names=["customer_id"],
    )


def build_orders_table() -> CatalogTable:
    orders_table_fqn = "postgres_prod.warehouse.finance.orders"
    customers_table_fqn = "postgres_prod.warehouse.crm.customers"
    return CatalogTable(
        table_fqn=orders_table_fqn,
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="finance",
        table_name="orders",
        sql_identifier="finance.orders",
        description="Orders fact table. Revenue doanh thu by customer khách hàng.",
        columns=[
            CatalogColumn(
                column_fqn=f"{orders_table_fqn}.order_id",
                column_name="order_id",
                data_type="text",
                is_primary_key=True,
                ordinal_position=1,
            ),
            CatalogColumn(
                column_fqn=f"{orders_table_fqn}.line_number",
                column_name="line_number",
                data_type="integer",
                ordinal_position=2,
            ),
            CatalogColumn(
                column_fqn=f"{orders_table_fqn}.customer_id",
                column_name="customer_id",
                data_type="text",
                description="Customer foreign key",
                ordinal_position=3,
            ),
            CatalogColumn(
                column_fqn=f"{orders_table_fqn}.net_revenue",
                column_name="net_revenue",
                data_type="numeric",
                description="Revenue amount. Doanh thu.",
                glossary_terms=["doanh thu"],
                ordinal_position=4,
            ),
        ],
        primary_key_column_names=["order_id"],
        foreign_keys=[
            CatalogForeignKey(
                relationship_name="orders_customer_fk",
                from_table_fqn=orders_table_fqn,
                from_column_names=["customer_id"],
                to_table_fqn=customers_table_fqn,
                to_column_names=["customer_id"],
            )
        ],
    )


def build_order_lines_table() -> CatalogTable:
    order_lines_table_fqn = "postgres_prod.warehouse.finance.order_lines"
    orders_table_fqn = "postgres_prod.warehouse.finance.orders"
    return CatalogTable(
        table_fqn=order_lines_table_fqn,
        service_name="postgres_prod",
        database_name="warehouse",
        schema_name="finance",
        table_name="order_lines",
        sql_identifier="finance.order_lines",
        description="Order line revenue detail",
        columns=[
            CatalogColumn(
                column_fqn=f"{order_lines_table_fqn}.order_id",
                column_name="order_id",
                data_type="text",
                ordinal_position=1,
            ),
            CatalogColumn(
                column_fqn=f"{order_lines_table_fqn}.line_number",
                column_name="line_number",
                data_type="integer",
                ordinal_position=2,
            ),
            CatalogColumn(
                column_fqn=f"{order_lines_table_fqn}.line_revenue",
                column_name="line_revenue",
                data_type="numeric",
                description="Line revenue",
                ordinal_position=3,
            ),
        ],
        foreign_keys=[
            CatalogForeignKey(
                relationship_name="order_lines_orders_composite_fk",
                from_table_fqn=order_lines_table_fqn,
                from_column_names=["order_id", "line_number"],
                to_table_fqn=orders_table_fqn,
                to_column_names=["order_id", "line_number"],
            )
        ],
    )
