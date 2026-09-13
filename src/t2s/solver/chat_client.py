from typing import Any, Protocol

from t2s.solver.solver_response import StructuredChatResponse


class StructuredChatClient(Protocol):
    async def generate_structured_response(
        self,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any],
        model_name: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
    ) -> StructuredChatResponse:
        ...
