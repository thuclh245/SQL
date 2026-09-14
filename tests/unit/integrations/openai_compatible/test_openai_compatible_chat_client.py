import json

import httpx
import pytest

from t2s.errors import MalformedSolverOutputError, SolverDependencyError
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.solver.solver_response import build_sql_candidate_json_schema


@pytest.mark.anyio
async def test_openai_compatible_client_sends_structured_request_without_secret_body() -> None:
    captured_request_body: dict[str, object] = {}
    captured_authorization = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_authorization
        captured_request_body.update(json.loads(request.content))
        captured_authorization = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "model": "chat-5-mini",
                "choices": [
                    {
                        "message": {
                            "content": {
                                "sql": "SELECT 1",
                                "dialect": "sqlite",
                                "referenced_tables": [],
                                "referenced_columns": [],
                                "expected_columns": ["one"],
                                "assumptions": [],
                                "unresolved": [],
                            }
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    client = OpenAICompatibleChatClient(
        base_url="https://provider.example/v1",
        api_key="fake-secret-key",
        transport=httpx.MockTransport(handler),
    )

    response = await client.generate_structured_response(
        messages=[{"role": "user", "content": "Return one"}],
        response_schema=build_sql_candidate_json_schema(),
        model_name="chat-5-mini",
        reasoning_effort=None,
        max_output_tokens=128,
    )

    assert response.content["sql"] == "SELECT 1"
    assert response.model_name == "chat-5-mini"
    assert response.prompt_tokens == 11
    assert response.output_tokens == 7
    assert captured_authorization == "Bearer fake-secret-key"
    assert "fake-secret-key" not in json.dumps(captured_request_body)
    assert captured_request_body["temperature"] == 0.0
    assert captured_request_body["max_tokens"] == 128


@pytest.mark.anyio
async def test_gpt5_mini_uses_max_completion_tokens_without_max_tokens() -> None:
    captured_request_body: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-5-mini",
                "choices": [
                    {
                        "message": {
                            "content": {
                                "sql": "SELECT 1",
                                "dialect": "sqlite",
                                "referenced_tables": [],
                                "referenced_columns": [],
                                "expected_columns": ["one"],
                                "assumptions": [],
                                "unresolved": [],
                            }
                        }
                    }
                ],
            },
        )

    client = OpenAICompatibleChatClient(
        base_url="https://provider.example/v1",
        api_key="fake-secret-key",
        transport=httpx.MockTransport(handler),
    )

    await client.generate_structured_response(
        messages=[{"role": "user", "content": "Return one"}],
        response_schema=build_sql_candidate_json_schema(),
        model_name="gpt-5-mini",
        reasoning_effort=None,
        max_output_tokens=321,
    )

    assert captured_request_body["max_completion_tokens"] == 321
    assert "max_tokens" not in captured_request_body


@pytest.mark.anyio
async def test_gpt5_mini_omits_unsupported_sampling_fields() -> None:
    captured_request_body: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-5-mini",
                "choices": [
                    {
                        "message": {
                            "content": {
                                "sql": "SELECT 1",
                                "dialect": "sqlite",
                                "referenced_tables": [],
                                "referenced_columns": [],
                                "expected_columns": ["one"],
                                "assumptions": [],
                                "unresolved": [],
                            }
                        }
                    }
                ],
            },
        )

    client = OpenAICompatibleChatClient(
        base_url="https://provider.example/v1",
        api_key="fake-secret-key",
        transport=httpx.MockTransport(handler),
    )

    await client.generate_structured_response(
        messages=[{"role": "user", "content": "Return one"}],
        response_schema=build_sql_candidate_json_schema(),
        model_name="gpt-5-mini",
        reasoning_effort=None,
        max_output_tokens=128,
    )

    assert "temperature" not in captured_request_body
    assert "top_p" not in captured_request_body
    assert "logprobs" not in captured_request_body


@pytest.mark.anyio
async def test_generic_openai_compatible_model_still_uses_max_tokens() -> None:
    captured_request_body: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "generic-chat-mini",
                "choices": [
                    {
                        "message": {
                            "content": {
                                "sql": "SELECT 1",
                                "dialect": "sqlite",
                                "referenced_tables": [],
                                "referenced_columns": [],
                                "expected_columns": ["one"],
                                "assumptions": [],
                                "unresolved": [],
                            }
                        }
                    }
                ],
            },
        )

    client = OpenAICompatibleChatClient(
        base_url="https://provider.example/v1",
        api_key="fake-secret-key",
        transport=httpx.MockTransport(handler),
    )

    await client.generate_structured_response(
        messages=[{"role": "user", "content": "Return one"}],
        response_schema=build_sql_candidate_json_schema(),
        model_name="generic-chat-mini",
        reasoning_effort=None,
        max_output_tokens=456,
    )

    assert captured_request_body["max_tokens"] == 456
    assert captured_request_body["temperature"] == 0.0
    assert "max_completion_tokens" not in captured_request_body


@pytest.mark.anyio
async def test_openai_compatible_client_wraps_provider_failures() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client = OpenAICompatibleChatClient(
        base_url="https://provider.example/v1",
        api_key="fake-secret-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SolverDependencyError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="chat-5-mini",
            reasoning_effort=None,
            max_output_tokens=128,
        )


@pytest.mark.anyio
async def test_openai_compatible_client_rejects_malformed_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    client = OpenAICompatibleChatClient(
        base_url="https://provider.example/v1",
        api_key=None,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MalformedSolverOutputError):
        await client.generate_structured_response(
            messages=[],
            response_schema=build_sql_candidate_json_schema(),
            model_name="chat-5-mini",
            reasoning_effort=None,
            max_output_tokens=128,
        )
