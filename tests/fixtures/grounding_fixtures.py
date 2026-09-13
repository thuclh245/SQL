from t2s.contracts import (
    ColumnContext,
    EvidenceRef,
    GlossaryHit,
    GroundingContext,
    RelationshipEvidence,
    TableContext,
    ValidatedQueryExample,
    ValueBinding,
)


def build_single_table_sales_grounding_context() -> GroundingContext:
    return GroundingContext(
        scope_id="finance-scope",
        tables=[
            TableContext(
                fqn="warehouse.finance.sales_orders",
                description="Authorized sales order facts.",
                columns=[
                    ColumnContext(name="order_id", data_type="text", description="Order key"),
                    ColumnContext(name="region", data_type="text", description="Sales region"),
                    ColumnContext(
                        name="net_revenue",
                        data_type="numeric",
                        description="Net revenue",
                    ),
                    ColumnContext(name="order_date", data_type="date", description="Order date"),
                ],
            )
        ],
        glossary_hits=[
            GlossaryHit(term="doanh thu thuần", definition="Use net_revenue from sales orders.")
        ],
        value_bindings=[
            ValueBinding(
                phrase="Q3/2026",
                column_fqn="warehouse.finance.sales_orders.order_date",
                value="[2026-07-01, 2026-10-01)",
            )
        ],
        examples=[
            ValidatedQueryExample(
                question="Revenue by region",
                sql=(
                    "SELECT region, SUM(net_revenue) AS net_revenue "
                    "FROM warehouse.finance.sales_orders GROUP BY region"
                ),
                dialect="postgres",
            )
        ],
        evidence=[
            EvidenceRef(
                kind="metadata",
                source_id="fixture:finance.sales_orders",
                summary="Sales order metadata fixture.",
            )
        ],
    )


def build_two_table_customer_grounding_context() -> GroundingContext:
    orders_table = TableContext(
        fqn="warehouse.finance.sales_orders",
        description="Authorized sales order facts.",
        columns=[
            ColumnContext(name="order_id", data_type="text"),
            ColumnContext(name="customer_id", data_type="text"),
            ColumnContext(name="net_revenue", data_type="numeric"),
        ],
        relationships=[
            RelationshipEvidence(
                from_table_fqn="warehouse.finance.sales_orders",
                from_column="customer_id",
                to_table_fqn="warehouse.crm.customers",
                to_column="customer_id",
            )
        ],
    )
    customers_table = TableContext(
        fqn="warehouse.crm.customers",
        description="Authorized customer dimension.",
        columns=[
            ColumnContext(name="customer_id", data_type="text"),
            ColumnContext(name="segment", data_type="text"),
        ],
    )
    return GroundingContext(
        scope_id="finance-crm-scope",
        tables=[orders_table, customers_table],
    )
