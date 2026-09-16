import pytest
from httpx import ASGITransport, AsyncClient

from t2s.bootstrap import create_application
from t2s.configuration import Settings
from t2s.contracts import QueryRequest
from t2s.runtime import RuntimeExecutionResult, RuntimeState, RuntimeStatus, RuntimeTrace
from t2s.security import UserIdentity


class RecordingRuntime:
    """Runtime double capturing the arguments the API route forwards to the pipeline."""

    def __init__(self) -> None:
        self.query_request: QueryRequest | None = None
        self.user_identity: UserIdentity | None = None
        self.run_id: str | None = None

    async def execute_query_pipeline(
        self,
        query_request: QueryRequest,
        user_identity: UserIdentity,
        run_id: str | None = None,
    ) -> RuntimeExecutionResult:
        self.query_request = query_request
        self.user_identity = user_identity
        self.run_id = run_id
        return RuntimeExecutionResult(
            run_id=run_id or "run-id",
            status=RuntimeStatus.COMPLETED,
            sql="SELECT 1 AS revenue",
            dialect="sqlite",
            columns=["revenue"],
            rows=[{"revenue": 1}],
            row_count=1,
            trace=RuntimeTrace(
                run_id=run_id or "run-id",
                final_state=RuntimeState.COMPLETED,
                ast_referenced_tables=["orders"],
                safety_check_passed=True,
                access_check_passed=True,
                execution_passed=True,
            ),
        )


@pytest.mark.anyio
async def test_query_request_abstains_when_no_runtime_is_configured() -> None:
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
    assert payload["decision"]["policy"] == "runtime-not-configured-v1"
    assert payload["sql"] is None


@pytest.mark.anyio
async def test_query_request_is_delegated_to_configured_runtime() -> None:
    runtime = RecordingRuntime()
    app = create_application(Settings(environment="test"), runtime=runtime)  # type: ignore[arg-type]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/query",
            json={"question": "Doanh thu theo khu vực?", "locale": "vi"},
            headers={
                "x-user-id": "analyst-1",
                "x-tenant-id": "tenant-a",
                "x-user-roles": "analyst, viewer",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "answer"
    assert payload["sql"] == "SELECT 1 AS revenue"
    assert payload["answer"]["rows"] == [{"revenue": 1}]
    assert payload["decision"]["policy"] == "safe-runtime-v1"
    assert payload["run_id"] == runtime.run_id

    assert runtime.query_request is not None
    assert runtime.query_request.question == "Doanh thu theo khu vực?"
    assert runtime.user_identity is not None
    assert runtime.user_identity.user_id == "analyst-1"
    assert runtime.user_identity.tenant_id == "tenant-a"
    assert runtime.user_identity.roles == frozenset({"analyst", "viewer"})


@pytest.mark.anyio
async def test_query_request_falls_back_to_configured_api_user_identity() -> None:
    runtime = RecordingRuntime()
    app = create_application(
        Settings(environment="test", runtime_api_user_id="service-account"),
        runtime=runtime,  # type: ignore[arg-type]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/query", json={"question": "Revenue by region"})

    assert response.status_code == 200
    assert runtime.user_identity is not None
    assert runtime.user_identity.user_id == "service-account"
    assert runtime.user_identity.tenant_id is None
    assert runtime.user_identity.roles == frozenset()


@pytest.mark.anyio
async def test_invalid_query_request_returns_422() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/query", json={"question": ""})

    assert response.status_code == 422


@pytest.mark.anyio
async def test_whitespace_only_query_request_returns_422() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for question in ["", " ", "\t\n"]:
            response = await client.post("/v1/query", json={"question": question})
            assert response.status_code == 422


@pytest.mark.anyio
async def test_valid_query_request_trims_surrounding_spaces() -> None:
    app = create_application(Settings(environment="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/query", json={"question": "  Revenue by region  "})

    assert response.status_code == 200
