import json

import httpx
import pytest

from t2s.catalog import CatalogSearchDocument
from t2s.errors import MetadataSyncError
from t2s.integrations.opensearch.opensearch_metadata_index import OpenSearchMetadataIndex


def test_opensearch_bulk_request_uses_ndjson_pairs() -> None:
    bulk_payloads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/_bulk"
        assert request.headers["content-type"] == "application/x-ndjson"
        bulk_payloads.append(request.content.decode())
        return httpx.Response(200, json={"errors": False, "items": []})

    index = OpenSearchMetadataIndex(
        base_url="http://opensearch.test",
        index_name="metadata",
        transport=httpx.MockTransport(handler),
    )

    index.upsert_search_documents([search_document("table-1")])

    bulk_lines = bulk_payloads[0].splitlines()
    assert len(bulk_lines) == 2
    assert json.loads(bulk_lines[0]) == {"index": {"_index": "metadata", "_id": "table:table-1"}}
    assert json.loads(bulk_lines[1])["document_id"] == "table:table-1"


def test_opensearch_bulk_indexing_is_chunked() -> None:
    bulk_payloads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bulk_payloads.append(request.content.decode())
        return httpx.Response(200, json={"errors": False, "items": []})

    index = OpenSearchMetadataIndex(
        base_url="http://opensearch.test",
        index_name="metadata",
        bulk_batch_size=2,
        transport=httpx.MockTransport(handler),
    )

    index.upsert_search_documents(
        [search_document("table-1"), search_document("table-2"), search_document("table-3")]
    )

    assert len(bulk_payloads) == 2
    assert [len(payload.splitlines()) for payload in bulk_payloads] == [4, 2]


def test_opensearch_partial_bulk_failure_is_reported_per_batch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "errors": True,
                "items": [{"index": {"error": {"type": "mapper_parsing_exception"}}}],
            },
        )

    index = OpenSearchMetadataIndex(
        base_url="http://opensearch.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MetadataSyncError):
        index.upsert_search_documents([search_document("table-1")])


def test_opensearch_delete_documents_for_table_uses_delete_by_query() -> None:
    captured_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/metadata/_delete_by_query"
        captured_payloads.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"deleted": 2})

    index = OpenSearchMetadataIndex(
        base_url="http://opensearch.test",
        index_name="metadata",
        transport=httpx.MockTransport(handler),
    )

    index.delete_search_documents_for_tables(["warehouse.sales.public.orders"])

    assert captured_payloads == [
        {"query": {"terms": {"table_fqn": ["warehouse.sales.public.orders"]}}}
    ]


def search_document(table_fqn: str) -> CatalogSearchDocument:
    return CatalogSearchDocument(
        document_id=f"table:{table_fqn}",
        document_type="table",
        table_fqn=table_fqn,
        title=table_fqn,
        searchable_text=table_fqn,
        service_name="warehouse",
        database_name="sales",
        schema_name="public",
        table_name=table_fqn,
    )
