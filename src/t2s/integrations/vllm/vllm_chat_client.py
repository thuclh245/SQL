import json
import time
from typing import Any

import httpx

from t2s.errors import MalformedSolverOutputError, SolverDependencyError
from t2s.solver.solver_response import StructuredChatResponse


class VllmChatClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        request_timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.request_timeout_seconds = request_timeout_seconds
        self.transport = transport

    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": response_schema,
            },
            "max_tokens": max_output_tokens,
        }
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
            raise SolverDependencyError("vLLM structured generation timed out.") from exc
        except httpx.HTTPError as exc:
            raise SolverDependencyError("vLLM structured generation failed.") from exc

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        response_payload = response.json()
        content = self._extract_message_content(response_payload)
        usage = response_payload.get("usage", {})
        return StructuredChatResponse(
            content=content,
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
                "vLLM response did not contain message content."
            ) from exc

        if isinstance(raw_content, dict):
            return raw_content
        if not isinstance(raw_content, str):
            raise MalformedSolverOutputError("vLLM message content was not JSON text.")

        try:
            parsed_content = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise MalformedSolverOutputError("vLLM message content was not valid JSON.") from exc
        if not isinstance(parsed_content, dict):
            raise MalformedSolverOutputError("vLLM message content JSON was not an object.")
        return parsed_content
