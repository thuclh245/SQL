import json

import httpx

from t2s.catalog.catalog_models import MetadataSnapshot
from t2s.catalog.metadata_document import CatalogSearchDocument, build_catalog_index_mapping
from t2s.errors import MetadataSyncError


class OpenSearchMetadataIndex:
    def __init__(
        self,
        base_url: str,
        index_name: str = "t2s-metadata",
        request_timeout_seconds: float = 30.0,
        bulk_batch_size: int = 1000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if bulk_batch_size <= 0:
            raise ValueError("OpenSearch bulk batch size must be greater than zero.")
        self.base_url = base_url.rstrip("/")
        self.index_name = index_name
        self.request_timeout_seconds = request_timeout_seconds
        self.bulk_batch_size = bulk_batch_size
        self.transport = transport

    def ensure_index(self) -> None:
        try:
            with self._build_client() as client:
                response = client.put(
                    f"{self.base_url}/{self.index_name}",
                    json=build_catalog_index_mapping(),
                )
                if response.status_code not in {200, 201, 400}:
                    response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetadataSyncError("OpenSearch metadata index creation failed.") from exc

    def upsert_search_documents(self, search_documents: list[CatalogSearchDocument]) -> None:
        if not search_documents:
            return
        for batch_start in range(0, len(search_documents), self.bulk_batch_size):
            search_document_batch = search_documents[
                batch_start : batch_start + self.bulk_batch_size
            ]
            self._post_bulk(self._build_bulk_payload(search_document_batch))

    def _build_bulk_payload(self, search_documents: list[CatalogSearchDocument]) -> str:
        bulk_lines: list[str] = []
        for search_document in search_documents:
            bulk_lines.append(
                json.dumps(
                    {"index": {"_index": self.index_name, "_id": search_document.document_id}}
                )
            )
            bulk_lines.append(search_document.model_dump_json())
        return "\n".join(bulk_lines) + "\n"

    def delete_search_documents_for_tables(self, table_fqns: list[str]) -> None:
        if not table_fqns:
            return
        query = {"query": {"terms": {"table_fqn": table_fqns}}}
        try:
            with self._build_client() as client:
                response = client.post(
                    f"{self.base_url}/{self.index_name}/_delete_by_query",
                    json=query,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetadataSyncError("OpenSearch metadata delete failed.") from exc

    def record_metadata_snapshot(self, metadata_snapshot: MetadataSnapshot) -> None:
        try:
            with self._build_client() as client:
                response = client.put(
                    f"{self.base_url}/{self.index_name}-snapshots/_doc/{metadata_snapshot.snapshot_id}",
                    json=metadata_snapshot.model_dump(mode="json"),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetadataSyncError("OpenSearch metadata snapshot write failed.") from exc

    def _post_bulk(self, bulk_payload: str) -> None:
        try:
            with self._build_client() as client:
                response = client.post(
                    f"{self.base_url}/_bulk",
                    content=bulk_payload,
                    headers={"Content-Type": "application/x-ndjson"},
                )
                response.raise_for_status()
                response_payload = response.json()
        except httpx.HTTPError as exc:
            raise MetadataSyncError("OpenSearch metadata bulk upsert failed.") from exc
        if isinstance(response_payload, dict) and response_payload.get("errors"):
            raise MetadataSyncError("OpenSearch metadata bulk upsert reported item errors.")

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.request_timeout_seconds,
            transport=self.transport,
        )
