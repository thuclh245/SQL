import json
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from t2s.errors import MalformedSolverOutputError, SolverDependencyError
from t2s.solver.solver_response import StructuredChatResponse

TokenLimitParameter = Literal["max_tokens", "max_completion_tokens"]


@dataclass(frozen=True)
class ChatCompletionModelCapabilities:
    token_limit_parameter: TokenLimitParameter
    supports_temperature: bool
    supports_top_p: bool
    supports_seed: bool
    supports_logprobs: bool


DEFAULT_CHAT_COMPLETION_CAPABILITIES = ChatCompletionModelCapabilities(
    token_limit_parameter="max_tokens",
    supports_temperature=True,
    supports_top_p=True,
    supports_seed=True,
    supports_logprobs=True,
)

GPT5_CHAT_COMPLETION_CAPABILITIES = ChatCompletionModelCapabilities(
    token_limit_parameter="max_completion_tokens",
    supports_temperature=False,
    supports_top_p=False,
    supports_seed=False,
    supports_logprobs=False,
)


def resolve_chat_completion_model_capabilities(
    model_name: str,
) -> ChatCompletionModelCapabilities:
    normalized_model = model_name.lower()
    if normalized_model.startswith("gpt-5") or "gpt-5" in normalized_model:
        return GPT5_CHAT_COMPLETION_CAPABILITIES
    return DEFAULT_CHAT_COMPLETION_CAPABILITIES


def describe_provider_request_policy(
    model_name: str,
    requested_temperature: float | None,
) -> dict[str, Any]:
    capabilities = resolve_chat_completion_model_capabilities(model_name)
    temperature_sent = requested_temperature is not None and capabilities.supports_temperature
    return {
        "token_limit_parameter": capabilities.token_limit_parameter,
        "requested_temperature": requested_temperature,
        "effective_temperature": requested_temperature if temperature_sent else None,
        "temperature_sent": temperature_sent,
        "top_p_sent": False,
        "seed_sent": False,
        "logprobs_sent": False,
    }


class OpenAICompatibleChatClient:
    """Structured chat client for OpenAI-compatible /v1/chat/completions APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        request_timeout_seconds: float = 120.0,
        temperature: float = 0.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.request_timeout_seconds = request_timeout_seconds
        self.temperature = temperature
        self.transport = transport

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        capabilities = resolve_chat_completion_model_capabilities(model_name)
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": response_schema,
            },
            capabilities.token_limit_parameter: max_output_tokens,
        }
        if capabilities.supports_temperature:
            payload["temperature"] = self.temperature
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        started_at = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.request_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SolverDependencyError(
                "OpenAI-compatible structured generation timed out."
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise SolverDependencyError(
                f"OpenAI-compatible structured generation failed with HTTP {status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise SolverDependencyError("OpenAI-compatible structured generation failed.") from exc

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        try:
            response_payload = response.json()
        except json.JSONDecodeError as exc:
            raise SolverDependencyError(
                "OpenAI-compatible provider returned a non-JSON response."
            ) from exc
        if not isinstance(response_payload, dict):
            raise SolverDependencyError(
                "OpenAI-compatible provider response was not a JSON object."
            )

        usage = response_payload.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        return StructuredChatResponse(
            content=self._extract_message_content(response_payload),
            model_name=response_payload.get("model", model_name),
            elapsed_ms=elapsed_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

    def _extract_message_content(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            raw_content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MalformedSolverOutputError(
                "OpenAI-compatible response did not contain message content."
            ) from exc

        if isinstance(raw_content, dict):
            return raw_content
        if not isinstance(raw_content, str):
            raise MalformedSolverOutputError("OpenAI-compatible message content was not JSON text.")

        try:
            parsed_content = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise MalformedSolverOutputError(
                "OpenAI-compatible message content was not valid JSON."
            ) from exc
        if not isinstance(parsed_content, dict):
            raise MalformedSolverOutputError(
                "OpenAI-compatible message content JSON was not an object."
            )
        return parsed_content
