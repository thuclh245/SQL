import hashlib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from t2s.errors import MalformedSolverOutputError, SolverDependencyError
from t2s.solver.chat_client import StructuredChatClient
from t2s.verification.contracts import (
    SEMANTIC_CHECK_DIMENSIONS,
    CheckStatus,
    SemanticCheckResult,
    VerificationDecision,
    VerificationInput,
    VerificationResult,
)


def _enforce_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    schema = dict(schema)
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
            schema["properties"] = {
                k: _enforce_strict_json_schema(v) for k, v in schema["properties"].items()
            }
    if "items" in schema:
        schema["items"] = _enforce_strict_json_schema(schema["items"])
    if "$defs" in schema:
        schema["$defs"] = {k: _enforce_strict_json_schema(v) for k, v in schema["$defs"].items()}
    return schema


def build_verification_result_json_schema() -> dict[str, Any]:
    raw_schema = VerificationResult.model_json_schema()
    strict_schema = _enforce_strict_json_schema(raw_schema)
    return {
        "name": "verification_result",
        "schema": strict_schema,
        "strict": True,
    }


class LlmSemanticVerifier:
    """Offline semantic SQL verifier using structured LLM reasoning.

    Evaluates candidate SQL across 7 semantic dimensions against the question and grounded schema.
    Strictly isolated: does not accept or process gold SQL, gold rows, or generator uncertainty.
    """

    def __init__(
        self,
        chat_client: StructuredChatClient,
        model_name: str = "gpt-5-mini",
        prompt_directory: Path | None = None,
        prompt_version: str = "v001",
        max_output_tokens: int = 1500,
        reasoning_effort: str | None = None,
    ) -> None:
        self.chat_client = chat_client
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.prompt_directory = prompt_directory or self._resolve_default_prompt_directory()
        self.prompt_sha256 = self._compute_prompt_hash()

    def _resolve_default_prompt_directory(self) -> Path:
        repository_root = Path(__file__).resolve().parents[3]
        return repository_root / "prompts" / "sql_verifier"

    def _compute_prompt_hash(self) -> str:
        sys_path = self.prompt_directory / f"{self.prompt_version}_system.md"
        usr_path = self.prompt_directory / f"{self.prompt_version}_user_template.md"
        content = ""
        if sys_path.exists():
            content += sys_path.read_text(encoding="utf-8")
        if usr_path.exists():
            content += usr_path.read_text(encoding="utf-8")
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _read_prompt_file(self, file_name: str) -> str:
        prompt_path = self.prompt_directory / file_name
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    def build_verifier_messages(
        self, verification_input: VerificationInput
    ) -> list[dict[str, str]]:
        system_prompt = self._read_prompt_file(f"{self.prompt_version}_system.md")
        user_template = self._read_prompt_file(f"{self.prompt_version}_user_template.md")

        user_content = user_template.format(
            question=verification_input.question,
            evidence=verification_input.evidence,
            target_dialect=verification_input.dialect,
            authorized_schema=verification_input.authorized_schema,
            candidate_sql=verification_input.candidate_sql,
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    async def verify(self, verification_input: VerificationInput) -> VerificationResult:
        messages = self.build_verifier_messages(verification_input)

        try:
            chat_response = await self.chat_client.generate_structured_response(
                messages=messages,
                response_schema=build_verification_result_json_schema(),
                model_name=self.model_name,
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.max_output_tokens,
            )
        except (SolverDependencyError, Exception) as exc:
            return self._fail_closed_result(
                f"Provider dependency failure during verification: {exc}"
            )

        try:
            result = VerificationResult.model_validate(chat_response.content)
        except (ValidationError, MalformedSolverOutputError, Exception) as exc:
            return self._fail_closed_result(f"Malformed verifier structured output: {exc}")

        # Post-process and enforce conservative decision policy
        failed_checks = [
            dim
            for dim in SEMANTIC_CHECK_DIMENSIONS
            if getattr(result, dim).status == CheckStatus.FAIL
        ]
        unknown_checks = [
            dim
            for dim in SEMANTIC_CHECK_DIMENSIONS
            if getattr(result, dim).status == CheckStatus.UNKNOWN
        ]

        # Decision alignment: any FAIL -> REJECT; any UNKNOWN -> ABSTAIN; all PASS -> ACCEPT
        if failed_checks:
            enforced_decision = VerificationDecision.REJECT
        elif unknown_checks:
            enforced_decision = VerificationDecision.ABSTAIN
        else:
            enforced_decision = VerificationDecision.ACCEPT

        return VerificationResult(
            projection=result.projection,
            aggregation_and_grain=result.aggregation_and_grain,
            filters_and_values=result.filters_and_values,
            join_semantics=result.join_semantics,
            ordering_and_limit=result.ordering_and_limit,
            null_semantics=result.null_semantics,
            schema_reference=result.schema_reference,
            decision=enforced_decision,
            failed_checks=failed_checks,
            unknown_checks=unknown_checks,
            confidence=result.confidence,
        )

    def _fail_closed_result(self, error_message: str) -> VerificationResult:
        unknown_check = SemanticCheckResult(
            status=CheckStatus.UNKNOWN,
            short_reason=error_message,
        )
        return VerificationResult(
            projection=unknown_check,
            aggregation_and_grain=unknown_check,
            filters_and_values=unknown_check,
            join_semantics=unknown_check,
            ordering_and_limit=unknown_check,
            null_semantics=unknown_check,
            schema_reference=unknown_check,
            decision=VerificationDecision.ABSTAIN,
            failed_checks=[],
            unknown_checks=list(SEMANTIC_CHECK_DIMENSIONS),
            confidence=0.0,
        )
