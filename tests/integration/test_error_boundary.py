import pytest
from httpx import ASGITransport, AsyncClient

from t2s.bootstrap import create_application
from t2s.configuration import Settings
from t2s.errors import UnauthorizedDataAccessError
from t2s.observability import read_correlation_context


@pytest.mark.anyio
async def test_typed_application_error_returns_structured_safe_response() -> None:
    app = create_application(Settings(environment="test"))

    @app.get("/test/typed-error")
    async def raise_typed_error() -> None:
        raise UnauthorizedDataAccessError("secret table name should not be exposed")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/test/typed-error",
            headers={"x-request-id": "request-test", "x-trace-id": "trace-test"},
        )

    payload = response.json()
    assert response.status_code == 500
    assert payload["error"]["code"] == "UNAUTHORIZED_DATA_ACCESS"
    assert payload["error"]["message"] == "The request could not be processed."
    assert payload["request_id"] == "request-test"
    assert payload["trace_id"] == "trace-test"
    assert payload["run_id"] is None
    assert "secret table" not in response.text


@pytest.mark.anyio
async def test_unexpected_exception_returns_sanitized_structured_500() -> None:
    app = create_application(Settings(environment="test"))

    @app.get("/test/unexpected-error")
    async def raise_unexpected_error() -> None:
        raise RuntimeError("database password leaked")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/test/unexpected-error")

    payload = response.json()
    assert response.status_code == 500
    assert payload["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "An internal error occurred.",
    }
    assert payload["request_id"]
    assert payload["trace_id"]
    assert payload["run_id"] is None
    assert "database password" not in response.text


@pytest.mark.anyio
async def test_correlation_context_is_bound_and_cleared_between_requests() -> None:
    app = create_application(Settings(environment="test"))

    @app.get("/test/correlation-context")
    async def read_context() -> dict[str, str]:
        return read_correlation_context()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_response = await client.get("/test/correlation-context")
        second_response = await client.get("/test/correlation-context")

    first_payload = first_response.json()
    second_payload = second_response.json()
    assert first_payload["request_id"] != second_payload["request_id"]
    assert first_payload["trace_id"] != second_payload["trace_id"]
    assert read_correlation_context() == {}


@pytest.mark.anyio
async def test_query_run_binds_run_id_to_request_context() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/query",
            json={"question": "Revenue by region"},
            headers={"x-request-id": "request-query", "x-trace-id": "trace-query"},
        )

    payload = response.json()
    assert payload["request_id"] == "request-query"
    assert payload["trace_id"] == "trace-query"
    assert payload["run_id"]
    assert response.headers["x-request-id"] == "request-query"
    assert response.headers["x-trace-id"] == "trace-query"
