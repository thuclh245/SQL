import httpx
import pytest

from t2s.errors import MalformedSolverOutputError, SolverDependencyError
from t2s.integrations.vllm import VllmChatClient
from t2s.integrations.vllm.structured_output_schema import build_sql_candidate_json_schema


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


def build_mocked_vllm_client(
    handler: httpx.MockTransport | httpx.SyncHandler | httpx.AsyncHandler,
) -> VllmChatClient:
    transport = httpx.MockTransport(handler)
    return VllmChatClient(base_url="http://vllm.test/v1", transport=transport)
