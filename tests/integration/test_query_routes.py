import pytest
from httpx import ASGITransport, AsyncClient

from t2s.bootstrap import create_application
from t2s.configuration import Settings


@pytest.mark.anyio
async def test_valid_query_request_returns_typed_stub_response() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/query",
            json={"question": "Doanh thu theo khu vực?", "locale": "vi"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "abstain"
    assert payload["request_id"]
    assert payload["run_id"]
    assert payload["trace_id"]
    assert payload["decision"]["policy"] == "foundation-stub-v0"
    assert payload["sql"] is None


@pytest.mark.anyio
async def test_invalid_query_request_returns_422() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/query", json={"question": ""})

    assert response.status_code == 422
