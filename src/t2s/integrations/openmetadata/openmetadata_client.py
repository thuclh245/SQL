from typing import Any

import httpx

from t2s.catalog.catalog_models import CatalogTable
from t2s.errors import MetadataSyncError
from t2s.integrations.openmetadata.table_mapper import OpenMetadataTableMapper


class OpenMetadataClient:
    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        table_mapper: OpenMetadataTableMapper | None = None,
        request_timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.table_mapper = table_mapper or OpenMetadataTableMapper()
        self.request_timeout_seconds = request_timeout_seconds
        self.transport = transport

    def list_tables(self, limit: int = 100) -> list[CatalogTable]:
        raw_tables: list[dict[str, Any]] = []
        after: str | None = None
        while True:
            response_payload = self._get_tables_page(limit=limit, after=after)
            page_tables = response_payload.get("data") or []
            raw_tables.extend(raw_table for raw_table in page_tables if isinstance(raw_table, dict))
            paging = response_payload.get("paging") or {}
            after = paging.get("after") if isinstance(paging, dict) else None
            if not after:
                break
        return [self.table_mapper.map_table(raw_table) for raw_table in raw_tables]

    def _get_tables_page(self, limit: int, after: str | None) -> dict[str, Any]:
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        params: dict[str, str | int] = {
            "limit": limit,
            "fields": "columns,tags,owner,tableConstraints,database,databaseSchema,service",
        }
        if after:
            params["after"] = after
        try:
            with self._build_client() as client:
                response = client.get(
                    f"{self.base_url}/api/v1/tables",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                response_payload = response.json()
        except httpx.HTTPError as exc:
            raise MetadataSyncError("OpenMetadata table fetch failed.") from exc
        except ValueError as exc:
            raise MetadataSyncError("OpenMetadata table fetch returned non-JSON data.") from exc
        if not isinstance(response_payload, dict):
            raise MetadataSyncError("OpenMetadata table fetch returned an invalid payload.")
        return response_payload

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.request_timeout_seconds,
            transport=self.transport,
        )
