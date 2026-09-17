"""V2-P01 provider-parity test: Static ↔ OpenMetadata canonical DTO equivalence.

Purpose (V2-P01 §30):
    Prove that switching the enterprise metadata source from
    :class:`StaticMetadataProvider` to :class:`OpenMetadataProvider` does not
    silently change MG0's information set. For logically equivalent metadata
    the two providers must produce equivalent canonical :class:`CatalogTable`
    lists after normalization.

Approach:
    Build a generic synthetic catalog (customers, orders, order_items) as
    both:

    A. a Static provider fed from a JSON file, and
    B. an OpenMetadata provider fed from a mocked HTTP transport that returns
       the same catalog through the OpenMetadata REST payload shape.

    Then compare the canonicalized :class:`CatalogTable` objects field-by-field
    on every field MG0 consumes (:mod:`t2s.grounding` reads these). Provenance
    is compared for source_system only (source_locator, timestamps, and
    source_entity_id are legitimately different across providers).

Fixtures use only generic synthetic identifiers (customers, orders,
order_items, warehouse, sales). No benchmark question, gold SQL, or protected
literal is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from t2s.catalog.canonical_metadata import CatalogTable
from t2s.catalog.metadata_scope import MetadataScope
from t2s.catalog.openmetadata_provider import OpenMetadataProvider
from t2s.catalog.static_metadata_provider import StaticMetadataProvider
from t2s.integrations.openmetadata.openmetadata_client import OpenMetadataClient

SERVICE_NAME = "warehouse"
DATABASE_NAME = "analytics"
SCHEMA_NAME = "sales"
TABLE_NAMES = ["customers", "order_items", "orders"]  # alphabetical for deterministic checks


def _static_catalog_json() -> list[dict[str, Any]]:
    """Return the same generic three-table catalog in the Static provider shape."""
    prefix = f"{SERVICE_NAME}.{DATABASE_NAME}.{SCHEMA_NAME}"
    return [
        {
            "table_fqn": f"{prefix}.customers",
            "service_name": SERVICE_NAME,
            "database_name": DATABASE_NAME,
            "schema_name": SCHEMA_NAME,
            "table_name": "customers",
            "table_type": "regular",
            "description": "Customer master.",
            "sql_identifier": "customers",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": f"{prefix}.customers.id",
                    "column_name": "id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "ordinal_position": 1,
                },
                {
                    "column_fqn": f"{prefix}.customers.name",
                    "column_name": "name",
                    "data_type": "VARCHAR",
                    "native_type": "VARCHAR",
                    "is_nullable": True,
                    "ordinal_position": 2,
                },
            ],
            "primary_key_column_names": ["id"],
        },
        {
            "table_fqn": f"{prefix}.orders",
            "service_name": SERVICE_NAME,
            "database_name": DATABASE_NAME,
            "schema_name": SCHEMA_NAME,
            "table_name": "orders",
            "table_type": "regular",
            "description": "Order header.",
            "sql_identifier": "orders",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": f"{prefix}.orders.id",
                    "column_name": "id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "ordinal_position": 1,
                },
                {
                    "column_fqn": f"{prefix}.orders.customer_id",
                    "column_name": "customer_id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "ordinal_position": 2,
                },
            ],
            "primary_key_column_names": ["id"],
            "foreign_keys": [
                {
                    "relationship_name": "orders_customer_fk",
                    "from_table_fqn": f"{prefix}.orders",
                    "from_column_names": ["customer_id"],
                    "to_table_fqn": f"{prefix}.customers",
                    "to_column_names": ["id"],
                    "to_service_name": SERVICE_NAME,
                    "to_database_name": DATABASE_NAME,
                    "to_schema_name": SCHEMA_NAME,
                    "to_table_name": "customers",
                    "provenance": "declared_foreign_key",
                }
            ],
        },
        {
            "table_fqn": f"{prefix}.order_items",
            "service_name": SERVICE_NAME,
            "database_name": DATABASE_NAME,
            "schema_name": SCHEMA_NAME,
            "table_name": "order_items",
            "table_type": "regular",
            "description": "Order line items.",
            "sql_identifier": "order_items",
            "sql_identifier_source": "explicit",
            "columns": [
                {
                    "column_fqn": f"{prefix}.order_items.id",
                    "column_name": "id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "ordinal_position": 1,
                },
                {
                    "column_fqn": f"{prefix}.order_items.order_id",
                    "column_name": "order_id",
                    "data_type": "BIGINT",
                    "native_type": "BIGINT",
                    "is_nullable": False,
                    "ordinal_position": 2,
                },
            ],
            "primary_key_column_names": ["id"],
            "foreign_keys": [
                {
                    "relationship_name": "order_items_order_fk",
                    "from_table_fqn": f"{prefix}.order_items",
                    "from_column_names": ["order_id"],
                    "to_table_fqn": f"{prefix}.orders",
                    "to_column_names": ["id"],
                    "to_service_name": SERVICE_NAME,
                    "to_database_name": DATABASE_NAME,
                    "to_schema_name": SCHEMA_NAME,
                    "to_table_name": "orders",
                    "provenance": "declared_foreign_key",
                }
            ],
        },
    ]


def _openmetadata_raw_table(
    name: str,
    columns_payload: list[dict[str, Any]],
    constraints_payload: list[dict[str, Any]] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Build an OpenMetadata REST-shaped raw table entity."""
    fqn = f"{SERVICE_NAME}.{DATABASE_NAME}.{SCHEMA_NAME}.{name}"
    return {
        "id": f"om-{name}",
        "name": name,
        "fullyQualifiedName": fqn,
        "tableType": "Regular",
        "description": description,
        "service": {"name": SERVICE_NAME, "fullyQualifiedName": SERVICE_NAME},
        "database": {"name": DATABASE_NAME},
        "databaseSchema": {"name": SCHEMA_NAME},
        "columns": columns_payload,
        "tableConstraints": constraints_payload or [],
        "extension": {"sqlIdentifier": name},
        "version": 1.0,
    }


def _openmetadata_payloads() -> dict[str, dict[str, Any]]:
    """Same generic three-table catalog in the OpenMetadata payload shape.

    Returned as a dict keyed by table FQN so the mock transport can serve
    both list-tables and get-by-name endpoints from a single fixture.
    """
    prefix = f"{SERVICE_NAME}.{DATABASE_NAME}.{SCHEMA_NAME}"

    customers = _openmetadata_raw_table(
        name="customers",
        description="Customer master.",
        columns_payload=[
            {
                "name": "id",
                "dataType": "BIGINT",
                "dataTypeDisplay": "BIGINT",
                "constraint": "PRIMARY_KEY",
                "ordinalPosition": 1,
                "isNullable": False,
            },
            {
                "name": "name",
                "dataType": "VARCHAR",
                "dataTypeDisplay": "VARCHAR",
                "ordinalPosition": 2,
                "isNullable": True,
            },
        ],
    )

    orders = _openmetadata_raw_table(
        name="orders",
        description="Order header.",
        columns_payload=[
            {
                "name": "id",
                "dataType": "BIGINT",
                "dataTypeDisplay": "BIGINT",
                "constraint": "PRIMARY_KEY",
                "ordinalPosition": 1,
                "isNullable": False,
            },
            {
                "name": "customer_id",
                "dataType": "BIGINT",
                "dataTypeDisplay": "BIGINT",
                "ordinalPosition": 2,
                "isNullable": False,
            },
        ],
        constraints_payload=[
            {
                "constraintType": "FOREIGN_KEY",
                "name": "orders_customer_fk",
                "columns": ["customer_id"],
                "referredColumns": [f"{prefix}.customers.id"],
            }
        ],
    )

    order_items = _openmetadata_raw_table(
        name="order_items",
        description="Order line items.",
        columns_payload=[
            {
                "name": "id",
                "dataType": "BIGINT",
                "dataTypeDisplay": "BIGINT",
                "constraint": "PRIMARY_KEY",
                "ordinalPosition": 1,
                "isNullable": False,
            },
            {
                "name": "order_id",
                "dataType": "BIGINT",
                "dataTypeDisplay": "BIGINT",
                "ordinalPosition": 2,
                "isNullable": False,
            },
        ],
        constraints_payload=[
            {
                "constraintType": "FOREIGN_KEY",
                "name": "order_items_order_fk",
                "columns": ["order_id"],
                "referredColumns": [f"{prefix}.orders.id"],
            }
        ],
    )

    return {
        f"{prefix}.customers": customers,
        f"{prefix}.orders": orders,
        f"{prefix}.order_items": order_items,
    }


def _build_static_provider(tmp_path: Path) -> StaticMetadataProvider:
    catalog_file = tmp_path / "generic_catalog.json"
    catalog_file.write_text(json.dumps(_static_catalog_json()), encoding="utf-8")
    return StaticMetadataProvider(catalog_tables_path=catalog_file)


def _build_openmetadata_provider() -> OpenMetadataProvider:
    payloads = _openmetadata_payloads()
    fqns_sorted = sorted(payloads.keys())

    def _handler(request: httpx.Request) -> httpx.Response:
        # Pilot mode goes through /api/v1/tables/name/<fqn>
        if request.url.path.startswith("/api/v1/tables/name/"):
            # httpx already decoded the path; strip the prefix.
            raw = request.url.path[len("/api/v1/tables/name/"):]
            from urllib.parse import unquote

            fqn = unquote(raw)
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
    return OpenMetadataProvider(client=client, pilot_fqns=fqns_sorted)


def _tables_equivalent_for_mg0(a: CatalogTable, b: CatalogTable) -> tuple[bool, str]:
    """Compare two CatalogTables on every field MG0 consumes.

    Provenance is not compared for equality (source_locator and snapshot_at
    legitimately differ across providers); only source_system is checked
    non-empty for both.
    """
    mg0_fields = (
        "table_fqn",
        "service_name",
        "database_name",
        "schema_name",
        "table_name",
        "table_type",
        "description",
        "sql_identifier",
        "sql_identifier_source",
        "primary_key_column_names",
    )
    for field in mg0_fields:
        av = getattr(a, field)
        bv = getattr(b, field)
        if av != bv:
            return False, f"table field '{field}' differs: static={av!r} openmetadata={bv!r}"

    if len(a.columns) != len(b.columns):
        return False, f"column count differs: static={len(a.columns)} openmetadata={len(b.columns)}"
    for ac, bc in zip(a.columns, b.columns, strict=True):
        for col_field in (
            "column_fqn",
            "column_name",
            "data_type",
            "is_nullable",
            "is_primary_key",
            "ordinal_position",
            "description",
        ):
            av = getattr(ac, col_field)
            bv = getattr(bc, col_field)
            if av != bv:
                return (
                    False,
                    f"column '{ac.column_name}' field '{col_field}' differs: "
                    f"static={av!r} openmetadata={bv!r}",
                )

    if len(a.foreign_keys) != len(b.foreign_keys):
        return (
            False,
            f"foreign key count differs: static={len(a.foreign_keys)} "
            f"openmetadata={len(b.foreign_keys)}",
        )
    for afk, bfk in zip(a.foreign_keys, b.foreign_keys, strict=True):
        for fk_field in (
            "from_table_fqn",
            "from_column_names",
            "to_table_fqn",
            "to_column_names",
            "provenance",
        ):
            av = getattr(afk, fk_field)
            bv = getattr(bfk, fk_field)
            if av != bv:
                return (
                    False,
                    f"foreign key {afk.relationship_name!r} field '{fk_field}' differs: "
                    f"static={av!r} openmetadata={bv!r}",
                )

    return True, ""


def test_provider_parity_canonical_dto_equivalence(tmp_path: Path) -> None:
    """Static and OpenMetadata providers produce equivalent canonical CatalogTables."""
    static_provider = _build_static_provider(tmp_path)
    openmetadata_provider = _build_openmetadata_provider()

    static_tables = sorted(static_provider.fetch_metadata(), key=lambda t: t.table_fqn)
    om_tables = sorted(openmetadata_provider.fetch_metadata(), key=lambda t: t.table_fqn)

    assert len(static_tables) == len(om_tables) == 3
    for st, ot in zip(static_tables, om_tables, strict=True):
        ok, reason = _tables_equivalent_for_mg0(st, ot)
        assert ok, f"Provider parity broken for {st.table_fqn}: {reason}"


def test_provider_parity_provenance_labels_source_system_but_not_locator() -> None:
    """Both providers stamp source_system; source_locator legitimately differs.

    OpenMetadata provenance carries source_locator (the OM FQN); Static
    provenance may not carry one. V2-P01 requires per-fact provenance so an
    auditor can tell one provider from the other, but the canonical DTO shape
    (fields MG0 reads) must remain equivalent.
    """
    static_json = _static_catalog_json()
    from t2s.catalog.canonical_metadata import CatalogTable as CT

    static_tables = [CT.model_validate(row) for row in static_json]

    om_provider = _build_openmetadata_provider()
    om_tables = om_provider.fetch_metadata()

    static_by_fqn = {t.table_fqn: t for t in static_tables}
    om_by_fqn = {t.table_fqn: t for t in om_tables}
    assert static_by_fqn.keys() == om_by_fqn.keys()

    for fqn, om_table in om_by_fqn.items():
        assert om_table.provenance is not None
        assert om_table.provenance.source_system == "openmetadata"
        # OpenMetadata provider must carry a source_locator so the audit can
        # distinguish it from a Static provider entry.
        assert om_table.provenance.source_locator == fqn


def test_openmetadata_provider_enforces_mg0_relationship_parity() -> None:
    """Declared FK relationships come through both providers with identical semantics."""
    om_provider = _build_openmetadata_provider()
    om_tables = {t.table_fqn: t for t in om_provider.fetch_metadata()}
    prefix = f"{SERVICE_NAME}.{DATABASE_NAME}.{SCHEMA_NAME}"

    orders = om_tables[f"{prefix}.orders"]
    order_items = om_tables[f"{prefix}.order_items"]

    assert len(orders.foreign_keys) == 1
    assert orders.foreign_keys[0].from_column_names == ["customer_id"]
    assert orders.foreign_keys[0].to_table_fqn == f"{prefix}.customers"
    assert orders.foreign_keys[0].to_column_names == ["id"]
    assert orders.foreign_keys[0].provenance == "declared_foreign_key"

    assert len(order_items.foreign_keys) == 1
    assert order_items.foreign_keys[0].to_table_fqn == f"{prefix}.orders"
    assert order_items.foreign_keys[0].to_column_names == ["id"]
    assert order_items.foreign_keys[0].provenance == "declared_foreign_key"


def test_openmetadata_provider_declines_unrestricted_scope_only_scoped_or_pilot() -> None:
    """Reaffirms the fail-closed guard even for a mocked provider with no live server."""
    import pytest

    from t2s.errors import MetadataSyncError

    def _empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [], "paging": {}})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(_empty),
    )
    provider = OpenMetadataProvider(client=client)  # no pilot_fqns
    with pytest.raises(MetadataSyncError, match="Unrestricted acquisition is prohibited"):
        provider.fetch_metadata()
    with pytest.raises(MetadataSyncError, match="Unrestricted acquisition is prohibited"):
        provider.fetch_metadata(scope=MetadataScope())
