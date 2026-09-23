"""Minimal Trino client speaking the HTTP client protocol directly.

Trino has no wire-level parameter binding: its own JDBC and Python drivers render
parameters into statement text before sending. This client therefore exposes only
whole statements, and every caller that needs literals must format them through
:func:`format_trino_string_literal`.

``httpx`` is already a dependency of this project, so the protocol is implemented
here rather than pulling in the ``trino`` package for one lab connector. The
implementation covers exactly what this system needs: submit one statement, follow
``nextUri`` until the result is complete, stop early at a row cap, and always
cancel a query the caller abandoned.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

STATEMENT_PATH = "/v1/statement"

# Trino answers 429/502/503/504 while it is starting up or shedding load; those are
# retried. Any other non-2xx is a protocol or authorization failure and is raised.
_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


class TrinoClientError(Exception):
    """Transport, protocol, or authorization failure talking to Trino."""


class TrinoStatementError(TrinoClientError):
    """Trino accepted the request and then failed the statement.

    ``error_name`` carries Trino's stable error name (for example
    ``EXCEEDED_TIME_LIMIT`` or ``PERMISSION_DENIED``), which callers map onto
    their own error types without parsing messages.
    """

    def __init__(
        self,
        message: str,
        error_name: str | None = None,
        error_code: int | None = None,
        error_type: str | None = None,
        query_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_name = error_name
        self.error_code = error_code
        self.error_type = error_type
        self.query_id = query_id


class TrinoTimeoutError(TrinoClientError):
    """The client-side deadline elapsed; the query was cancelled."""


def format_trino_string_literal(value: str) -> str:
    """Render a Python string as a Trino VARCHAR literal.

    Mirrors what the official drivers do client-side. A NUL byte cannot survive the
    round trip and is rejected rather than silently dropped.
    """
    if "\x00" in value:
        raise ValueError("Trino string literals cannot contain NUL.")
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def format_trino_identifier(identifier: str) -> str:
    """Quote a dotted catalog identifier part by part.

    Identifiers always originate from the catalog, never from user input, but they
    are quoted anyway so reserved words and mixed case survive.
    """
    parts = [part for part in identifier.split(".") if part]
    if not parts:
        raise ValueError("Trino identifier must not be empty.")
    quoted_parts = []
    for part in parts:
        if '"' in part:
            raise ValueError("Trino identifier parts cannot contain a double quote.")
        quoted_parts.append(f'"{part}"')
    return ".".join(quoted_parts)


@dataclass(frozen=True)
class TrinoQueryOutcome:
    """Rows returned for one statement, plus whether the row cap cut them short."""

    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    query_id: str | None = None
    elapsed_ms: int = 0


class TrinoRestClient:
    """Submits one statement at a time over the Trino HTTP client protocol."""

    def __init__(
        self,
        base_url: str,
        user: str,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        password: str | None = None,
        source: str = "t2s",
        time_zone: str | None = None,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.05,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.catalog = catalog
        self.schema = schema
        self.password = password
        self.source = source
        self.time_zone = time_zone
        self.connect_timeout_seconds = connect_timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.max_retries = max(0, max_retries)
        self.transport = transport
        self._sleeper = sleeper or time.sleep

    def __repr__(self) -> str:
        password_indicator = "***" if self.password else "none"
        return (
            f"TrinoRestClient(base_url='{self.base_url}', user='{self.user}', "
            f"catalog={self.catalog!r}, password={password_indicator})"
        )

    def run(
        self,
        sql: str,
        *,
        session_properties: Mapping[str, str] | None = None,
        max_rows: int | None = None,
        deadline_seconds: float | None = None,
    ) -> TrinoQueryOutcome:
        """Execute one statement and collect its rows.

        ``max_rows`` stops collection early and cancels the query, so a statement
        that would return millions of rows never has to finish. ``deadline_seconds``
        bounds total wall time client-side; Trino's own
        ``query_max_execution_time`` session property bounds it server-side.
        """
        started_at = time.monotonic()
        deadline = None if deadline_seconds is None else started_at + deadline_seconds

        with self._open_client() as client:
            payload = self._request(
                client,
                "POST",
                f"{self.base_url}{STATEMENT_PATH}",
                content=sql.encode("utf-8"),
                session_properties=session_properties,
                deadline=deadline,
            )

            query_id = payload.get("id")
            columns: list[str] = []
            rows: list[list[Any]] = []
            truncated = False

            while True:
                self._raise_for_statement_error(payload, query_id)

                if not columns:
                    columns = [
                        str(column.get("name", "")) for column in payload.get("columns") or []
                    ]
                for row in payload.get("data") or []:
                    if max_rows is not None and len(rows) >= max_rows + 1:
                        break
                    rows.append(list(row))

                next_uri = payload.get("nextUri")
                if max_rows is not None and len(rows) > max_rows:
                    truncated = True
                    rows = rows[:max_rows]
                    self._cancel(client, next_uri)
                    break
                if not next_uri:
                    break

                self._sleep_before_poll(payload)
                try:
                    payload = self._request(
                        client,
                        "GET",
                        str(next_uri),
                        session_properties=None,
                        deadline=deadline,
                    )
                except TrinoTimeoutError:
                    self._cancel(client, next_uri)
                    raise

        return TrinoQueryOutcome(
            columns=columns,
            rows=rows,
            truncated=truncated,
            query_id=query_id if isinstance(query_id, str) else None,
            elapsed_ms=int((time.monotonic() - started_at) * 1000),
        )

    def run_scalar(
        self,
        sql: str,
        *,
        session_properties: Mapping[str, str] | None = None,
        deadline_seconds: float | None = None,
    ) -> Any | None:
        """Return the first column of the first row, or ``None`` when there is none."""
        outcome = self.run(
            sql,
            session_properties=session_properties,
            max_rows=1,
            deadline_seconds=deadline_seconds,
        )
        if not outcome.rows or not outcome.rows[0]:
            return None
        return outcome.rows[0][0]

    def _open_client(self) -> httpx.Client:
        auth: tuple[str, str] | None = None
        if self.password is not None:
            auth = (self.user, self.password)
        return httpx.Client(
            timeout=httpx.Timeout(
                self.read_timeout_seconds,
                connect=self.connect_timeout_seconds,
            ),
            transport=self.transport,
            auth=auth,
            follow_redirects=False,
        )

    def _headers(self, session_properties: Mapping[str, str] | None) -> dict[str, str]:
        headers = {
            "X-Trino-User": self.user,
            "X-Trino-Source": self.source,
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "application/json",
        }
        if self.catalog:
            headers["X-Trino-Catalog"] = self.catalog
        if self.schema:
            headers["X-Trino-Schema"] = self.schema
        if self.time_zone:
            headers["X-Trino-Time-Zone"] = self.time_zone
        if session_properties:
            headers["X-Trino-Session"] = ",".join(
                f"{quote(name, safe='')}={quote(str(value), safe='')}"
                for name, value in session_properties.items()
            )
        return headers

    def _request(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        session_properties: Mapping[str, str] | None,
        deadline: float | None,
    ) -> dict[str, Any]:
        headers = self._headers(session_properties)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            self._check_deadline(deadline)
            try:
                response = client.request(method, url, content=content, headers=headers)
            except httpx.TimeoutException as exc:
                last_error = exc
                raise TrinoTimeoutError("Trino request timed out.") from exc
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = TrinoClientError(
                        f"Trino returned HTTP {response.status_code}."
                    )
                elif response.status_code in (401, 403):
                    raise TrinoClientError(
                        f"Trino rejected the request with HTTP {response.status_code}."
                    )
                elif response.status_code >= 400:
                    raise TrinoClientError(
                        f"Trino returned HTTP {response.status_code}."
                    )
                else:
                    return self._decode(response)

            if attempt < self.max_retries:
                self._sleeper(min(0.1 * (2**attempt), 1.0))

        raise TrinoClientError("Trino request failed after retries.") from last_error

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise TrinoClientError("Trino returned a non-JSON response.") from exc
        if not isinstance(payload, dict):
            raise TrinoClientError("Trino returned an unexpected response shape.")
        return payload

    def _raise_for_statement_error(self, payload: Mapping[str, Any], query_id: Any) -> None:
        error = payload.get("error")
        if not isinstance(error, Mapping):
            return
        raise TrinoStatementError(
            str(error.get("message") or "Trino statement failed."),
            error_name=_optional_str(error.get("errorName")),
            error_code=_optional_int(error.get("errorCode")),
            error_type=_optional_str(error.get("errorType")),
            query_id=query_id if isinstance(query_id, str) else None,
        )

    def _sleep_before_poll(self, payload: Mapping[str, Any]) -> None:
        """Back off only while Trino is still planning or has produced nothing yet."""
        if payload.get("data"):
            return
        self._sleeper(self.poll_interval_seconds)

    def _cancel(self, client: httpx.Client, next_uri: Any) -> None:
        """Best-effort cancel; a failure here must not mask the caller's outcome."""
        if not isinstance(next_uri, str) or not next_uri:
            return
        try:
            client.delete(next_uri, headers=self._headers(None))
        except httpx.HTTPError:
            return

    def _check_deadline(self, deadline: float | None) -> None:
        if deadline is not None and time.monotonic() >= deadline:
            raise TrinoTimeoutError("Trino query exceeded the client deadline.")


def _optional_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def build_session_properties(
    statement_timeout_seconds: int,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Session properties that bound one statement server-side."""
    properties: dict[str, str] = {
        "query_max_execution_time": f"{statement_timeout_seconds}s",
        "query_max_run_time": f"{statement_timeout_seconds}s",
    }
    if extra:
        properties.update(extra)
    return properties

