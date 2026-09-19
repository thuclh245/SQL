"""Shared semantic runtime assembly for multiple entrypoint adapters."""

from collections.abc import Callable
from pathlib import Path

from t2s.contracts import GroundingContext
from t2s.contracts.sql_candidate import SupportedSqlDialect
from t2s.database import QueryExecutionPolicy, QueryExecutorPort
from t2s.grounding import GroundingContextBuilder
from t2s.orchestration import AdaptiveOrchestrator, EscalationPolicy
from t2s.runtime.runtime_contracts import ValidatorMode
from t2s.runtime.runtime_profile import SemanticRuntimeProfile
from t2s.runtime.text_to_sql_runtime import TextToSqlRuntime
from t2s.security import AuthorizationService
from t2s.semantics import GroundedSemanticPlanner, SemanticPlanConsistencyChecker
from t2s.solver import DirectSqlPromptBuilder, DirectSqlSolver
from t2s.solver.chat_client import StructuredChatClient
from t2s.verification import (
    DiagnosticProbeRunner,
    ResultVerifier,
    SqlAccessValidator,
    SqlAstParser,
    SqlSafetyValidator,
)


def assemble_semantic_runtime(
    *,
    grounding_context_builder: GroundingContextBuilder,
    authorization_service: AuthorizationService,
    query_executor: QueryExecutorPort,
    chat_client: StructuredChatClient,
    prompt_directory: Path,
    execution_policy: QueryExecutionPolicy,
    default_dialect: SupportedSqlDialect,
    profile: SemanticRuntimeProfile,
    schema_serializer: Callable[[GroundingContext], str] | None = None,
) -> TextToSqlRuntime:
    """Build the shared semantic pipeline after entrypoint-specific setup.

    Catalog acquisition, identity handling, executor construction, HTTP transport,
    and benchmark scoring deliberately stay outside this function.
    """
    prompt_builder = DirectSqlPromptBuilder(
        prompt_directory=prompt_directory,
        prompt_version=profile.prompt_version,
        schema_serializer=schema_serializer,
    )
    solver = DirectSqlSolver(
        chat_client=chat_client,
        prompt_builder=prompt_builder,
        model_name=profile.model_name,
    )
    semantic_planner = _build_semantic_planner(profile, chat_client)
    orchestrator = AdaptiveOrchestrator(
        grounding_context_builder=grounding_context_builder,
        solver=solver,
        escalation_policy=EscalationPolicy(
            release_candidates_with_caveats=profile.release_candidates_with_caveats
        ),
        escalation_budget=profile.escalation_budget,
        semantic_planner=semantic_planner,
    )
    access_validator = SqlAccessValidator(authorization_service)
    ast_parser = SqlAstParser()
    safety_validator = SqlSafetyValidator()
    result_verifier = ResultVerifier() if profile.result_verifier_enabled else None
    diagnostic_probe_runner = (
        DiagnosticProbeRunner(
            query_executor=query_executor,
            sql_ast_parser=ast_parser,
            sql_safety_validator=safety_validator,
            sql_access_validator=access_validator,
        )
        if result_verifier is not None
        else None
    )

    return TextToSqlRuntime(
        adaptive_orchestrator=orchestrator,
        sql_access_validator=access_validator,
        query_executor=query_executor,
        sql_ast_parser=ast_parser,
        sql_safety_validator=safety_validator,
        execution_policy=execution_policy,
        default_dialect=default_dialect,
        validator_mode=ValidatorMode(profile.validator_mode),
        plan_consistency_checker=(
            SemanticPlanConsistencyChecker() if semantic_planner is not None else None
        ),
        result_verifier=result_verifier,
        diagnostic_probe_runner=diagnostic_probe_runner,
        enable_self_correction=profile.enable_self_correction,
    )


def _build_semantic_planner(
    profile: SemanticRuntimeProfile,
    chat_client: StructuredChatClient,
) -> GroundedSemanticPlanner | None:
    if profile.planner_mode == "off":
        return None
    if profile.planner_mode == "deterministic":
        return GroundedSemanticPlanner()
    return GroundedSemanticPlanner(chat_client=chat_client, model_name=profile.model_name)
