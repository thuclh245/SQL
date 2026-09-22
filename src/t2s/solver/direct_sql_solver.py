from pydantic import ValidationError

from t2s.contracts import GenerationTrace, SqlCandidate
from t2s.errors import MalformedSolverOutputError, UnsupportedSqlDialectError
from t2s.solver.chat_client import StructuredChatClient
from t2s.solver.prompt_builder import DirectSqlPromptBuilder
from t2s.solver.solver_request import SolverRequest
from t2s.solver.solver_response import SolverStructuredOutput, build_sql_candidate_json_schema

SUPPORTED_DIALECTS = {"postgres", "clickhouse", "starrocks", "sqlite"}


class DirectSqlSolver:
    def __init__(
        self,
        chat_client: StructuredChatClient,
        prompt_builder: DirectSqlPromptBuilder,
        model_name: str = "gpt-oss-120b",
    ) -> None:
        self.chat_client = chat_client
        self.prompt_builder = prompt_builder
        self.model_name = model_name

    async def generate_sql_candidate(self, solver_request: SolverRequest) -> SqlCandidate:
        if solver_request.target_dialect not in SUPPORTED_DIALECTS:
            raise UnsupportedSqlDialectError(
                f"Unsupported target dialect: {solver_request.target_dialect}"
            )

        messages = self.prompt_builder.build_solver_messages(
            query_request=solver_request.query_request,
            grounding_context=solver_request.grounding_context,
            target_dialect=solver_request.target_dialect,
            semantic_plan=solver_request.semantic_plan,
        )
        chat_response = await self.chat_client.generate_structured_response(
            messages=messages,
            response_schema=build_sql_candidate_json_schema(),
            model_name=self.model_name,
            reasoning_effort=solver_request.generation_settings.reasoning_effort,
            max_output_tokens=solver_request.generation_settings.max_output_tokens,
        )

        try:
            return self._parse_structured_chat_response(chat_response, solver_request)
        except (MalformedSolverOutputError, ValidationError):
            # One retry if model outputs empty SQL or malformed payload
            retry_messages = list(messages)
            retry_messages.append({
                "role": "user",
                "content": "IMPORTANT: You returned empty SQL in your previous response. You MUST write a non-empty, valid SQL statement.",
            })
            retry_response = await self.chat_client.generate_structured_response(
                messages=retry_messages,
                response_schema=build_sql_candidate_json_schema(),
                model_name=self.model_name,
                reasoning_effort=solver_request.generation_settings.reasoning_effort,
                max_output_tokens=solver_request.generation_settings.max_output_tokens,
            )
            return self._parse_structured_chat_response(retry_response, solver_request)

    async def refine_sql_candidate(
        self,
        solver_request: SolverRequest,
        failed_sql: str,
        error_message: str,
    ) -> SqlCandidate:
        """Attempt single-turn self-correction given runtime database execution error."""
        messages = self.prompt_builder.build_solver_messages(
            query_request=solver_request.query_request,
            grounding_context=solver_request.grounding_context,
            target_dialect=solver_request.target_dialect,
            semantic_plan=solver_request.semantic_plan,
        )
        correction_user_content = (
            f"The previous SQL query you produced failed during execution on the database:\n"
            f"```sql\n{failed_sql}\n```\n\n"
            f"Database execution error:\n{error_message}\n\n"
            f"Please fix the SQL query to resolve this error. Use only valid table identifiers "
            f"and column names from the authorized schema above. Output only the updated SQL candidate."
        )
        messages.extend([
            {"role": "assistant", "content": f'{{"sql": {failed_sql!r}}}'},
            {"role": "user", "content": correction_user_content},
        ])

        chat_response = await self.chat_client.generate_structured_response(
            messages=messages,
            response_schema=build_sql_candidate_json_schema(),
            model_name=self.model_name,
            reasoning_effort=solver_request.generation_settings.reasoning_effort,
            max_output_tokens=solver_request.generation_settings.max_output_tokens,
        )

        return self._parse_structured_chat_response(chat_response, solver_request)

    def _parse_structured_chat_response(
        self,
        chat_response: Any,
        solver_request: SolverRequest,
    ) -> SqlCandidate:
        try:
            structured_output = SolverStructuredOutput.model_validate(chat_response.content)
        except ValidationError as exc:
            raise MalformedSolverOutputError(
                "Model response did not match SqlCandidate schema."
            ) from exc

        if structured_output.dialect != solver_request.target_dialect:
            raise MalformedSolverOutputError(
                "Model response dialect did not match requested target dialect."
            )

        sql_cleaned = structured_output.sql.strip()
        if sql_cleaned.startswith("```"):
            lines = sql_cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            sql_cleaned = "\n".join(lines).strip()

        try:
            return SqlCandidate(
                sql=sql_cleaned,
                dialect=structured_output.dialect,
                referenced_tables=structured_output.referenced_tables,
                referenced_columns=structured_output.referenced_columns,
                expected_columns=structured_output.expected_columns,
                assumptions=structured_output.assumptions,
                unresolved=structured_output.unresolved,
                generation_trace=GenerationTrace(
                    run_id=solver_request.run_id,
                    model_name=chat_response.model_name,
                    prompt_version=self.prompt_builder.prompt_version,
                    reasoning_effort=solver_request.generation_settings.reasoning_effort,
                    max_output_tokens=solver_request.generation_settings.max_output_tokens,
                    elapsed_ms=chat_response.elapsed_ms,
                    prompt_tokens=chat_response.prompt_tokens,
                    output_tokens=chat_response.output_tokens,
                ),
            )
        except ValidationError as exc:
            raise MalformedSolverOutputError(
                "Model response produced an invalid SqlCandidate."
            ) from exc

