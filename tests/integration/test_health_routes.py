import pytest
from httpx import ASGITransport, AsyncClient

from t2s.bootstrap import create_application
from t2s.configuration import Settings


@pytest.mark.anyio
async def test_health_liveness_returns_200() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


@pytest.mark.anyio
async def test_health_readiness_returns_200() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "environment": "test"}
