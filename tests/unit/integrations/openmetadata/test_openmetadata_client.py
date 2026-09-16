import httpx
import pytest

from t2s.errors import (
    MetadataAuthenticationError,
    MetadataCardinalityLimitExceededError,
    MetadataEntityNotFoundError,
    MetadataPermissionError,
    MetadataSyncError,
)
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
        max_assets=10,
    )

    catalog_tables = client.list_tables(limit=1)

    assert requested_after_tokens == [None, "page-2"]
    assert [catalog_table.table_name for catalog_table in catalog_tables] == [
        "orders",
        "customers",
    ]


def test_openmetadata_client_bearer_auth_and_masking() -> None:
    captured_auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"data": []})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        auth_token="test-token",
        transport=httpx.MockTransport(handler),
    )

    client.list_tables()
    assert captured_auth == ["Bearer test-token"]
    assert "test-token" not in repr(client)
    assert "***" in repr(client)


def test_openmetadata_client_401_authentication_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Not authenticated"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        auth_token="bad-token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MetadataAuthenticationError, match="HTTP 401 Unauthorized"):
        client.list_tables()


def test_openmetadata_client_403_permission_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MetadataPermissionError, match="HTTP 403 Forbidden"):
        client.list_tables()


def test_openmetadata_client_404_not_found_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Table not found"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MetadataEntityNotFoundError, match="HTTP 404"):
        client.get_table_by_fqn("warehouse.db.sch.missing_table")


def test_openmetadata_client_retry_on_429_then_succeed() -> None:
    calls = 0
    slept_durations: list[float] = []

    def mock_sleeper(duration: float) -> None:
        slept_durations.append(duration)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"message": "Too Many Requests"})
        return httpx.Response(200, json={"data": [raw_table("svc.db.sch.tbl", "tbl")]})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        max_retries=2,
        sleeper=mock_sleeper,
        transport=httpx.MockTransport(handler),
    )

    tables = client.list_tables()
    assert len(tables) == 1
    assert calls == 2
    assert len(slept_durations) == 1


def test_openmetadata_client_cardinality_limit_exceeded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    raw_table("svc.db.sch.t1", "t1"),
                    raw_table("svc.db.sch.t2", "t2"),
                    raw_table("svc.db.sch.t3", "t3"),
                ]
            },
        )

    # Set max_assets to 2
    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        max_assets=2,
        transport=httpx.MockTransport(handler),
    )

    # Must fail closed, never silently truncate!
    with pytest.raises(
        MetadataCardinalityLimitExceededError, match="exceeding configured safety limit"
    ):
        client.list_tables()


def test_openmetadata_client_page_limit_exceeded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [raw_table("svc.db.sch.t", "t")],
                "paging": {"after": "cursor-infinite"},
            },
        )

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        max_pages=3,
        max_assets=100,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MetadataCardinalityLimitExceededError, match="exceeded page limit"):
        client.list_tables()


def test_openmetadata_client_normalizes_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "provider failed"})

    client = OpenMetadataClient(
        base_url="http://openmetadata.test",
        max_retries=0,
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
        "id": "11111111-2222-3333-4444-555555555555",
        "fullyQualifiedName": table_fqn,
        "name": table_name,
        "service": {"name": "warehouse"},
        "database": {"name": "analytics"},
        "databaseSchema": {"name": "sales"},
        "extension": {"sqlIdentifier": f"analytics.sales.{table_name}"},
        "columns": [{"name": "id", "dataType": "BIGINT", "dataTypeDisplay": "int8"}],
        "version": 0.1,
    }
