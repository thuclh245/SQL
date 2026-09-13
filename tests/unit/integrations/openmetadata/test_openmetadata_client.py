import httpx
import pytest

from t2s.errors import MetadataSyncError
from t2s.integrations.openmetadata.openmetadata_client import OpenMetadataClient


def test_openmetadata_client_reads_all_after_pages() -> None:
    requested_after_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_after_tokens.append(request.url.params.get("after"))
        if request.url.params.get("after") is None:
            return httpx.Response(
                200,
                json={
                    "data": [raw_table("warehouse.analytics.sales.orders", "orders")],
                    "paging": {"after": "page-2"},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [raw_table("warehouse.analytics.sales.customers", "customers")],
                "paging": {},
            },
        )

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
    )

    catalog_tables = client.list_tables(limit=1)

    assert requested_after_tokens == [None, "page-2"]
    assert [catalog_table.table_name for catalog_table in catalog_tables] == [
        "orders",
        "customers",
    ]


def test_openmetadata_client_normalizes_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "provider failed"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MetadataSyncError):
        client.list_tables()


def test_openmetadata_client_normalizes_non_json_provider_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy error</html>")

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MetadataSyncError):
        client.list_tables()


def raw_table(table_fqn: str, table_name: str) -> dict[str, object]:
    return {
        "fullyQualifiedName": table_fqn,
        "name": table_name,
        "service": {"name": "warehouse"},
        "database": {"name": "analytics"},
        "databaseSchema": {"name": "sales"},
        "extension": {"sqlIdentifier": f"analytics.sales.{table_name}"},
        "columns": [{"name": "id", "dataType": "BIGINT"}],
    }
