from collections.abc import Awaitable, Callable

import httpx
import pytest

from t2s.errors import MalformedSolverOutputError, SolverDependencyError
from t2s.integrations.vllm import VllmChatClient
from t2s.solver.solver_response import build_sql_candidate_json_schema


@pytest.mark.anyio
async def test_vllm_client_parses_structured_message_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b"json_schema" in payload
        return httpx.Response(
            200,
            json={
                "model": "gpt-oss-120b",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"sql":"SELECT 1","dialect":"postgres",'
                                '"referenced_tables":[],"referenced_columns":[],'
                                '"expected_columns":["one"],"assumptions":[],"unresolved":[]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8},
            },
        )

    client = build_mocked_vllm_client(handler)

    response = await client.generate_structured_response(
        messages=[{"role": "user", "content": "question"}],
        response_schema=build_sql_candidate_json_schema(),
        model_name="gpt-oss-120b",
        reasoning_effort="medium",
        max_output_tokens=128,
    )

    assert response.content["sql"] == "SELECT 1"
    assert response.model_name == "gpt-oss-120b"
    assert response.prompt_tokens == 10
    assert response.output_tokens == 8


@pytest.mark.anyio
async def test_vllm_client_rejects_malformed_json_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json"}}]},
        )

    client = build_mocked_vllm_client(handler)

    with pytest.raises(MalformedSolverOutputError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="gpt-oss-120b",
            reasoning_effort=None,
            max_output_tokens=128,
        )


@pytest.mark.anyio
async def test_vllm_timeout_is_dependency_failure() -> None:
    async def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    client = build_mocked_vllm_client(raise_timeout)

    with pytest.raises(SolverDependencyError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="gpt-oss-120b",
            reasoning_effort=None,
            max_output_tokens=128,
        )


@pytest.mark.anyio
async def test_vllm_http_200_non_json_is_dependency_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy error</html>")

    client = build_mocked_vllm_client(handler)

    with pytest.raises(SolverDependencyError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="gpt-oss-120b",
            reasoning_effort=None,
            max_output_tokens=128,
        )


@pytest.mark.anyio
async def test_vllm_http_500_is_dependency_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "provider failure"})

    client = build_mocked_vllm_client(handler)

    with pytest.raises(SolverDependencyError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="gpt-oss-120b",
            reasoning_effort=None,
            max_output_tokens=128,
        )


@pytest.mark.anyio
async def test_vllm_connection_failure_is_dependency_failure() -> None:
    async def raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed")

    client = build_mocked_vllm_client(raise_connect_error)

    with pytest.raises(SolverDependencyError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="gpt-oss-120b",
            reasoning_effort=None,
            max_output_tokens=128,
        )


@pytest.mark.anyio
async def test_vllm_malformed_provider_structure_is_solver_output_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "gpt-oss-120b", "choices": []})

    client = build_mocked_vllm_client(handler)

    with pytest.raises(MalformedSolverOutputError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="gpt-oss-120b",
            reasoning_effort=None,
            max_output_tokens=128,
        )


def build_mocked_vllm_client(
    handler: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]],
) -> VllmChatClient:
    transport = httpx.MockTransport(handler)
    return VllmChatClient(base_url="http://vllm.test/v1", transport=transport)
