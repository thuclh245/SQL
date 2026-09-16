from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

from t2s.errors import (
    MetadataAuthenticationError,
    MetadataCardinalityLimitExceededError,
    MetadataEntityNotFoundError,
    MetadataPermissionError,
    MetadataSyncError,
)
from t2s.integrations.openmetadata.table_mapper import OpenMetadataTableMapper
from t2s.security.error_sanitizer import sanitize_error_message

if TYPE_CHECKING:
    from t2s.catalog.canonical_metadata import CatalogTable

DEFAULT_TABLE_FIELDS = (
    "columns,tags,owner,domain,tableConstraints,database,databaseSchema,service,extension"
)


class OpenMetadataClient:
    """Production REST client for OpenMetadata entity catalog APIs."""

    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        table_mapper: OpenMetadataTableMapper | None = None,
        request_timeout_seconds: float = 30.0,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 25.0,
        max_retries: int = 3,
        max_assets: int = 25,
        max_pages: int = 10,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.table_mapper = table_mapper or OpenMetadataTableMapper()
        self.request_timeout_seconds = request_timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self.max_retries = max(0, max_retries)
        self.max_assets = max_assets
        self.max_pages = max_pages
        self.transport = transport
        self._sleeper = sleeper or time.sleep

    def __repr__(self) -> str:
        token_indicator = "***" if self.auth_token else "none"
        return (
            f"OpenMetadataClient(base_url='{self.base_url}', "
            f"auth_token={token_indicator}, max_assets={self.max_assets})"
        )

    def get_table_by_fqn(
        self,
        table_fqn: str,
        fields: str = DEFAULT_TABLE_FIELDS,
    ) -> CatalogTable:
        """Fetch an individual table entity by exact OpenMetadata FQN."""
        raw_table = self.get_raw_table_by_fqn(table_fqn, fields=fields)
        return self.table_mapper.map_table(raw_table)

    def get_raw_table_by_fqn(
        self,
        table_fqn: str,
        fields: str = DEFAULT_TABLE_FIELDS,
    ) -> dict[str, Any]:
        """Fetch raw OpenMetadata JSON entity by exact FQN."""
        clean_fqn = table_fqn.strip()
        if not clean_fqn:
            raise MetadataSyncError("Cannot fetch OpenMetadata table with empty FQN.")

        encoded_fqn = quote(clean_fqn, safe="")
        path = f"/api/v1/tables/name/{encoded_fqn}"
        params: dict[str, str | int] = {"fields": fields, "include": "non-deleted"}
        return self._request_json(path=path, params=params)

    def list_tables(
        self,
        database: str | None = None,
        database_schema: str | None = None,
        limit: int = 25,
        fields: str = DEFAULT_TABLE_FIELDS,
    ) -> list[CatalogTable]:
        """Acquire tables matching scope filters with safe pagination and cardinality caps."""
        raw_tables = self.list_raw_tables(
            database=database,
            database_schema=database_schema,
            limit=limit,
            fields=fields,
        )
        return [self.table_mapper.map_table(raw_table) for raw_table in raw_tables]

    def list_raw_tables(
        self,
        database: str | None = None,
        database_schema: str | None = None,
        limit: int = 25,
        fields: str = DEFAULT_TABLE_FIELDS,
    ) -> list[dict[str, Any]]:
        """Paginate OpenMetadata table entities enforcing completeness and cardinality caps."""
        raw_tables: list[dict[str, Any]] = []
        after: str | None = None
        pages_fetched = 0

        while True:
            pages_fetched += 1
            if pages_fetched > self.max_pages:
                raise MetadataCardinalityLimitExceededError(
                    f"OpenMetadata pagination exceeded page limit of {self.max_pages} pages."
                )

            params: dict[str, str | int] = {
                "limit": limit,
                "fields": fields,
                "include": "non-deleted",
            }
            if database:
                params["database"] = database.strip()
            if database_schema:
                params["databaseSchema"] = database_schema.strip()
            if after:
                params["after"] = after

            response_payload = self._request_json(path="/api/v1/tables", params=params)
            page_data = response_payload.get("data") or []
            if not isinstance(page_data, list):
                raise MetadataSyncError("OpenMetadata response 'data' field is not a list.")

            for item in page_data:
                if isinstance(item, dict):
                    raw_tables.append(item)

            # Cardinality guard: fail closed if result set exceeds max_assets
            if len(raw_tables) > self.max_assets:
                raise MetadataCardinalityLimitExceededError(
                    f"OpenMetadata returned {len(raw_tables)} assets, exceeding configured "
                    f"safety limit of {self.max_assets} assets. Aborting to prevent accidental "
                    "full-catalog ingestion."
                )

            paging = response_payload.get("paging") or {}
            after = paging.get("after") if isinstance(paging, dict) else None
            if not after:
                break

        return raw_tables

    def _request_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute HTTP GET with bounded retries and sanitized exceptions."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "t2s-catalog/0.1.0",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        url = f"{self.base_url}{path}"
        timeout = httpx.Timeout(
            self.request_timeout_seconds,
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                with httpx.Client(timeout=timeout, transport=self.transport) as client:
                    response = client.get(url, headers=headers, params=params)

                # Explicit status handling
                if response.status_code == 401:
                    raise MetadataAuthenticationError(
                        "OpenMetadata authentication failed (HTTP 401 Unauthorized). "
                        "Verify that OPENMETADATA_AUTH_TOKEN is valid."
                    )
                if response.status_code == 403:
                    raise MetadataPermissionError(
                        "OpenMetadata permission denied (HTTP 403 Forbidden). "
                        "Ensure the token has read permissions on catalog tables."
                    )
                if response.status_code == 404:
                    raise MetadataEntityNotFoundError(
                        f"OpenMetadata entity not found (HTTP 404): {sanitize_error_message(path)}"
                    )

                # Retryable HTTP status codes
                if response.status_code in {429, 502, 503, 504}:
                    err_msg = f"Transient OpenMetadata HTTP {response.status_code} error on {path}"
                    last_error = MetadataSyncError(err_msg)
                    if attempts <= self.max_retries:
                        backoff = 0.05 * (2 ** (attempts - 1))
                        self._sleeper(backoff)
                        continue
                    raise last_error

                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise MetadataSyncError(
                        f"OpenMetadata returned invalid JSON object from {path}"
                    )
                return payload

            except (
                MetadataAuthenticationError,
                MetadataPermissionError,
                MetadataEntityNotFoundError,
            ):
                raise
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ) as exc:
                sanitized_exc = sanitize_error_message(str(exc))
                last_error = MetadataSyncError(
                    f"OpenMetadata network transport error: {sanitized_exc}"
                )
                if attempts <= self.max_retries:
                    backoff = 0.05 * (2 ** (attempts - 1))
                    self._sleeper(backoff)
                    continue
                raise last_error from exc
            except httpx.HTTPStatusError as exc:
                sanitized_exc = sanitize_error_message(str(exc))
                raise MetadataSyncError(
                    f"OpenMetadata HTTP error {exc.response.status_code}: {sanitized_exc}"
                ) from exc
            except ValueError as exc:
                raise MetadataSyncError(
                    f"OpenMetadata response from {path} is not valid JSON."
                ) from exc
            except Exception as exc:
                sanitized_exc = sanitize_error_message(str(exc))
                raise MetadataSyncError(
                    f"OpenMetadata unexpected request failure: {sanitized_exc}"
                ) from exc

        if last_error:
            raise last_error
        raise MetadataSyncError(f"OpenMetadata request failed after {attempts} attempts.")
