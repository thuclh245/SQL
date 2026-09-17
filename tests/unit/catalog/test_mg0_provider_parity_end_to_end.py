"""V2-P01R end-to-end MG0 provider-parity test.

V2-P01R §5 requires proof that Static and OpenMetadata providers produce
identical MG0 output — not merely identical canonical CatalogTables. The
V2-P01 parity test compared canonical DTOs; this file runs the DTOs through
the actual MG0 deterministic path (CatalogSearchDocumentBuilder →
SchemaRetriever → GroundingContextBuilder → S0 Serializer via
``_format_authorized_schema``) and asserts equivalence on every observable
MG0 output.

Every fixture uses only generic synthetic identifiers (customers, orders,
order_items in warehouse.analytics.sales). Synthetic tags and glossary
terms are used in both providers so the retrieval-scoring feature comparison
is meaningful. No benchmark question, gold SQL, or protected literal is
present.

No LLM call is made. The test is fully deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from t2s.catalog import CatalogSearchDocumentBuilder
from t2s.catalog.in_memory_catalog import InMemoryCatalog
from t2s.catalog.openmetadata_provider import OpenMetadataProvider
from t2s.catalog.static_metadata_provider import StaticMetadataProvider
from t2s.contracts import QueryRequest
from t2s.grounding import GroundingBudget, GroundingContextBuilder, SchemaRetriever
from t2s.grounding.schema_retriever import InMemorySchemaSearch
from t2s.integrations.openmetadata.openmetadata_client import OpenMetadataClient
from t2s.security import (
    AuthorizationService,
    AuthorizedSqlResource,
    UserIdentity,
)
from t2s.solver import DirectSqlPromptBuilder

SERVICE = "warehouse"
DATABASE = "analytics"
SCHEMA = "sales"
FQN_PREFIX = f"{SERVICE}.{DATABASE}.{SCHEMA}"
TABLE_NAMES = ["customers", "orders", "order_items"]
COMMON_QUESTION = "How many orders did each customer place last month?"


def _synthetic_static_catalog() -> list[dict[str, Any]]:
    """Generic three-table catalog with synthetic tags/glossary in Static shape."""
    return [
        {
            "table_fqn": f"{FQN_PREFIX}.customers",
            "service_name": SERVICE,
            "database_name": DATABASE,
            "schema_name": SCHEMA,
            "table_name": "customers",
            "table_type": "regular",
            "description": "Customer master table.",
            "sql_identifier": "customers",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": f"{FQN_PREFIX}.customers.id",
                    "column_name": "id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "ordinal_position": 1,
                    "description": "Primary identifier.",
                    "tags": ["identity"],
                    "glossary_terms": [],
                },
                {
                    "column_fqn": f"{FQN_PREFIX}.customers.name",
                    "column_name": "name",
                    "data_type": "VARCHAR",
                    "native_type": "VARCHAR",
                    "is_nullable": True,
                    "ordinal_position": 2,
                    "description": "Customer display name.",
                    "tags": [],
                    "glossary_terms": [],
                },
            ],
            "primary_key_column_names": ["id"],
            "tags": ["core"],
            "glossary_terms": ["customer"],
        },
        {
            "table_fqn": f"{FQN_PREFIX}.orders",
            "service_name": SERVICE,
            "database_name": DATABASE,
            "schema_name": SCHEMA,
            "table_name": "orders",
            "table_type": "regular",
            "description": "Order header table.",
            "sql_identifier": "orders",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": f"{FQN_PREFIX}.orders.id",
                    "column_name": "id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "ordinal_position": 1,
                    "description": "Order id.",
                    "tags": ["identity"],
                    "glossary_terms": [],
                },
                {
                    "column_fqn": f"{FQN_PREFIX}.orders.customer_id",
                    "column_name": "customer_id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "ordinal_position": 2,
                    "description": "Foreign key to customers.",
                    "tags": [],
                    "glossary_terms": [],
                },
                {
                    "column_fqn": f"{FQN_PREFIX}.orders.placed_at",
                    "column_name": "placed_at",
                    "data_type": "TIMESTAMP",
                    "native_type": "TIMESTAMP",
                    "is_nullable": False,
                    "ordinal_position": 3,
                    "description": "Order placement timestamp.",
                    "tags": [],
                    "glossary_terms": [],
                },
            ],
            "primary_key_column_names": ["id"],
            "foreign_keys": [
                {
                    "relationship_name": "orders_customer_fk",
                    "from_table_fqn": f"{FQN_PREFIX}.orders",
                    "from_column_names": ["customer_id"],
                    "to_table_fqn": f"{FQN_PREFIX}.customers",
                    "to_column_names": ["id"],
                    "to_service_name": SERVICE,
                    "to_database_name": DATABASE,
                    "to_schema_name": SCHEMA,
                    "to_table_name": "customers",
                    "provenance": "declared_foreign_key",
                }
            ],
            "tags": ["core"],
            "glossary_terms": ["order"],
        },
        {
            "table_fqn": f"{FQN_PREFIX}.order_items",
            "service_name": SERVICE,
            "database_name": DATABASE,
            "schema_name": SCHEMA,
            "table_name": "order_items",
            "table_type": "regular",
            "description": "Order line items.",
            "sql_identifier": "order_items",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": f"{FQN_PREFIX}.order_items.id",
                    "column_name": "id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "ordinal_position": 1,
                    "description": "Line item id.",
                    "tags": ["identity"],
                    "glossary_terms": [],
                },
                {
                    "column_fqn": f"{FQN_PREFIX}.order_items.order_id",
                    "column_name": "order_id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "ordinal_position": 2,
                    "description": "Foreign key to orders.",
                    "tags": [],
                    "glossary_terms": [],
                },
            ],
            "primary_key_column_names": ["id"],
            "foreign_keys": [
                {
                    "relationship_name": "order_items_order_fk",
                    "from_table_fqn": f"{FQN_PREFIX}.order_items",
                    "from_column_names": ["order_id"],
                    "to_table_fqn": f"{FQN_PREFIX}.orders",
                    "to_column_names": ["id"],
                    "to_service_name": SERVICE,
                    "to_database_name": DATABASE,
                    "to_schema_name": SCHEMA,
                    "to_table_name": "orders",
                    "provenance": "declared_foreign_key",
                }
            ],
            "tags": ["core"],
            "glossary_terms": ["order"],
        },
    ]


def _openmetadata_payload_for(name: str) -> dict[str, Any]:
    """Build the OpenMetadata REST-shaped payload equivalent to the Static row for `name`."""
    static = {row["table_name"]: row for row in _synthetic_static_catalog()}[name]
    fqn = static["table_fqn"]

    columns_payload = []
    for column in static["columns"]:
        payload = {
            "name": column["column_name"],
            "fullyQualifiedName": column["column_fqn"],
            "dataType": column["data_type"],
            "dataTypeDisplay": column["native_type"],
            "ordinalPosition": column["ordinal_position"],
            "description": column.get("description"),
            "isNullable": column["is_nullable"],
        }
        if column.get("is_primary_key"):
            payload["constraint"] = "PRIMARY_KEY"
        column_tags = [
            {"source": "Tag", "tagFQN": tag_value} for tag_value in column.get("tags", [])
        ] + [
            {"source": "Glossary", "tagFQN": term} for term in column.get("glossary_terms", [])
        ]
        if column_tags:
            payload["tags"] = column_tags
        columns_payload.append(payload)

    constraints: list[dict[str, Any]] = []
    for foreign_key in static.get("foreign_keys", []):
        constraints.append(
            {
                "constraintType": "FOREIGN_KEY",
                "name": foreign_key["relationship_name"],
                "columns": foreign_key["from_column_names"],
                "referredColumns": [
                    f"{foreign_key['to_table_fqn']}.{column_name}"
                    for column_name in foreign_key["to_column_names"]
                ],
            }
        )

    table_tags = [
        {"source": "Tag", "tagFQN": tag_value} for tag_value in static.get("tags", [])
    ] + [
        {"source": "Glossary", "tagFQN": term} for term in static.get("glossary_terms", [])
    ]

    return {
        "id": f"om-{name}",
        "name": name,
        "fullyQualifiedName": fqn,
        "tableType": "Regular",
        "description": static.get("description"),
        "service": {"name": SERVICE, "fullyQualifiedName": SERVICE},
        "database": {"name": DATABASE},
        "databaseSchema": {"name": SCHEMA},
        "columns": columns_payload,
        "tableConstraints": constraints,
        "extension": {"sqlIdentifier": name},
        "tags": table_tags,
        "version": 1.0,
    }


def _build_static_provider(tmp_path: Path) -> StaticMetadataProvider:
    catalog_path = tmp_path / "generic_mg0_catalog.json"
    catalog_path.write_text(json.dumps(_synthetic_static_catalog()), encoding="utf-8")
    return StaticMetadataProvider(catalog_tables_path=catalog_path)


def _build_openmetadata_provider() -> OpenMetadataProvider:
    payloads = {f"{FQN_PREFIX}.{name}": _openmetadata_payload_for(name) for name in TABLE_NAMES}

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/v1/tables/name/"):
            from urllib.parse import unquote

            fqn = unquote(request.url.path[len("/api/v1/tables/name/"):])
            payload = payloads.get(fqn)
            if payload is None:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "unhandled"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        auth_token=None,
        transport=httpx.MockTransport(_handler),
        max_assets=10,
    )
    return OpenMetadataProvider(client=client, pilot_fqns=sorted(payloads.keys()))


def _assemble_mg0_stack(
    catalog_tables: list[Any],
) -> tuple[GroundingContextBuilder, AuthorizationService]:
    """Build the deterministic MG0 stack around a fixed list of CatalogTables."""
    in_memory_catalog = InMemoryCatalog()
    in_memory_catalog.upsert_tables(catalog_tables)

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

    class _AllowAllPolicy:
        def get_authorized_resources(
            self, _user_identity: UserIdentity
        ) -> list[AuthorizedSqlResource]:
            return list(authorized_resources)

    authorization_service = AuthorizationService(_AllowAllPolicy())
    grounding_budget = GroundingBudget(
        max_candidate_tables=50,
        max_hydrated_tables=8,
        max_columns_per_table=12,
        max_total_columns=60,
        max_relationships=16,
        relationship_expansion_mode="conditional",
        fill_column_budget=False,
        small_db_threshold=0,
    )
    context_builder = GroundingContextBuilder(
        catalog=in_memory_catalog,
        schema_retriever=schema_retriever,
        authorization_service=authorization_service,
        grounding_budget=grounding_budget,
    )
    return context_builder, authorization_service


def _mg0_output_for_provider(catalog_tables: list[Any]) -> dict[str, Any]:
    """Run one provider's CatalogTables all the way through MG0 (deterministic, no LLM)."""
    context_builder, _ = _assemble_mg0_stack(catalog_tables)
    grounding_context = context_builder.build_grounding_context(
        query_request=QueryRequest(question=COMMON_QUESTION),
        user_identity=UserIdentity(user_id="parity-runner", tenant_id="t2s"),
    )
    prompt_builder = DirectSqlPromptBuilder()
    s0_context_text = prompt_builder._format_authorized_schema(grounding_context)

    selected_tables = [table.fqn for table in grounding_context.tables]
    selected_columns = {
        table.fqn: [column.name for column in table.columns] for table in grounding_context.tables
    }
    relationships_summary = sorted(
        {
            (
                relationship.from_table_fqn,
                tuple(relationship.from_columns),
                relationship.to_table_fqn,
                tuple(relationship.to_columns),
            )
            for table in grounding_context.tables
            for relationship in table.relationships
        }
    )
    return {
        "selected_tables": selected_tables,
        "selected_columns": selected_columns,
        "relationships": relationships_summary,
        "s0_context_text": s0_context_text,
        "candidate_count": grounding_context.retrieval_signals.get("candidate_count"),
        "ranked_table_count": grounding_context.retrieval_signals.get("ranked_table_count"),
    }


def test_mg0_provider_parity_selected_tables(tmp_path: Path) -> None:
    static_tables = list(_build_static_provider(tmp_path).fetch_metadata())
    om_tables = list(_build_openmetadata_provider().fetch_metadata())
    static_output = _mg0_output_for_provider(static_tables)
    om_output = _mg0_output_for_provider(om_tables)
    assert static_output["selected_tables"] == om_output["selected_tables"], (
        "MG0 selected different tables for logically equivalent metadata: "
        f"static={static_output['selected_tables']!r} vs om={om_output['selected_tables']!r}"
    )


def test_mg0_provider_parity_selected_columns(tmp_path: Path) -> None:
    static_tables = list(_build_static_provider(tmp_path).fetch_metadata())
    om_tables = list(_build_openmetadata_provider().fetch_metadata())
    static_output = _mg0_output_for_provider(static_tables)
    om_output = _mg0_output_for_provider(om_tables)
    assert static_output["selected_columns"] == om_output["selected_columns"], (
        f"MG0 selected different columns for equivalent metadata: "
        f"static={static_output['selected_columns']!r} vs om={om_output['selected_columns']!r}"
    )


def test_mg0_provider_parity_relationships(tmp_path: Path) -> None:
    static_tables = list(_build_static_provider(tmp_path).fetch_metadata())
    om_tables = list(_build_openmetadata_provider().fetch_metadata())
    static_output = _mg0_output_for_provider(static_tables)
    om_output = _mg0_output_for_provider(om_tables)
    assert static_output["relationships"] == om_output["relationships"], (
        f"MG0 built different relationship sets: "
        f"static={static_output['relationships']!r} vs om={om_output['relationships']!r}"
    )


def test_mg0_provider_parity_retrieval_signals(tmp_path: Path) -> None:
    """SchemaRetriever ranking depth (candidate_count, ranked_table_count) must match.

    This is the invariant that catches tag/glossary drift between providers,
    because the SchemaRetriever score weights tags at 1.5 and glossary at
    1.75. Different tags/glossary produce different scores and different
    ranked_table_count.
    """
    static_tables = list(_build_static_provider(tmp_path).fetch_metadata())
    om_tables = list(_build_openmetadata_provider().fetch_metadata())
    static_output = _mg0_output_for_provider(static_tables)
    om_output = _mg0_output_for_provider(om_tables)
    assert static_output["candidate_count"] == om_output["candidate_count"], (
        f"candidate_count differs: static={static_output['candidate_count']} "
        f"om={om_output['candidate_count']}"
    )
    assert static_output["ranked_table_count"] == om_output["ranked_table_count"], (
        f"ranked_table_count differs: static={static_output['ranked_table_count']} "
        f"om={om_output['ranked_table_count']}"
    )


def test_mg0_provider_parity_s0_context_text_bytewise(tmp_path: Path) -> None:
    """The S0 serialized context (what reaches the solver prompt) must be identical.

    This is the strongest end-to-end invariant: after
    ``DirectSqlPromptBuilder._format_authorized_schema`` runs on both
    grounding contexts, the resulting text must match byte-for-byte.
    """
    static_tables = list(_build_static_provider(tmp_path).fetch_metadata())
    om_tables = list(_build_openmetadata_provider().fetch_metadata())
    static_output = _mg0_output_for_provider(static_tables)
    om_output = _mg0_output_for_provider(om_tables)
    assert static_output["s0_context_text"] == om_output["s0_context_text"], (
        "S0 serialized context differs between providers. First 400 chars:\n"
        f"--- Static ---\n{static_output['s0_context_text'][:400]!r}\n"
        f"--- OpenMetadata ---\n{om_output['s0_context_text'][:400]!r}"
    )


def test_mg0_provider_parity_tags_and_glossary_flow_through(tmp_path: Path) -> None:
    """Synthetic tags/glossary supplied to both providers reach the SchemaRetriever equivalently.

    V2-P01R §4: MG0_TAG_POLICY = INCLUDED_IN_RETRIEVAL_SCORING and
    MG0_GLOSSARY_POLICY = INCLUDED_IN_RETRIEVAL_SCORING. Both providers must
    therefore expose tags/glossary on canonical DTOs; MG0 uses them as
    retrieval-scoring features (weights 1.5 / 1.75 in
    ``SchemaRetriever._score_document``) but does NOT inject them verbatim
    into the solver prompt.
    """
    static_tables = list(_build_static_provider(tmp_path).fetch_metadata())
    om_tables = list(_build_openmetadata_provider().fetch_metadata())

    static_by_fqn = {table.table_fqn: table for table in static_tables}
    om_by_fqn = {table.table_fqn: table for table in om_tables}
    assert static_by_fqn.keys() == om_by_fqn.keys()

    for fqn, static_table in static_by_fqn.items():
        om_table = om_by_fqn[fqn]
        assert sorted(static_table.tags) == sorted(om_table.tags), (
            f"Tag drift on {fqn}: static={sorted(static_table.tags)} "
            f"om={sorted(om_table.tags)}"
        )
        assert sorted(static_table.glossary_terms) == sorted(om_table.glossary_terms), (
            f"Glossary drift on {fqn}: static={sorted(static_table.glossary_terms)} "
            f"om={sorted(om_table.glossary_terms)}"
        )
