from pydantic import ValidationError

from t2s.contracts import GenerationTrace, SqlCandidate
from t2s.errors import MalformedSolverOutputError, UnsupportedSqlDialectError
from t2s.solver.chat_client import StructuredChatClient
from t2s.solver.prompt_builder import DirectSqlPromptBuilder
from t2s.solver.solver_request import SolverRequest
from t2s.solver.solver_response import SolverStructuredOutput, build_sql_candidate_json_schema

SUPPORTED_DIALECTS = {"postgres", "clickhouse", "starrocks", "sqlite", "trino"}


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
            structured_output = SolverStructuredOutput.model_validate(chat_response.content)
        except ValidationError as exc:
            raise MalformedSolverOutputError(
                "Model response did not match SqlCandidate schema."
            ) from exc

        if structured_output.dialect != solver_request.target_dialect:
            raise MalformedSolverOutputError(
                "Model response dialect did not match requested target dialect."
            )

        try:
            return SqlCandidate(
                sql=structured_output.sql,
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
