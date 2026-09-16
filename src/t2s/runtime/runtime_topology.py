"""Secret-free inspection and comparison of constructed semantic runtimes."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from t2s.runtime.runtime_profile import SemanticRuntimeProfile
from t2s.runtime.text_to_sql_runtime import TextToSqlRuntime

ParityStatus = Literal["MATCH", "FAIL", "ALLOWED_INFRASTRUCTURE_DIFFERENCE"]


class RuntimeComponentDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wired: bool
    reachable: bool
    class_name: str | None = None
    module: str | None = None
    mode: str
    stage: str | None = None


class RuntimeTopologySnapshot(BaseModel):
    """Actual, secret-free runtime object graph plus effective semantic settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1"
    entrypoint: str
    components: dict[str, RuntimeComponentDescriptor]
    solver: dict[str, Any]
    grounding: dict[str, Any]
    policies: dict[str, Any]
    execution: dict[str, Any]


class RuntimeParityDifference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    api: Any
    benchmark: Any
    status: ParityStatus
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    reason: str


class RuntimeParityResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["PASS", "FAIL"]
    semantic_differences: list[RuntimeParityDifference] = Field(default_factory=list)
    allowed_infrastructure_differences: list[RuntimeParityDifference] = Field(default_factory=list)


def inspect_effective_runtime(
    runtime: TextToSqlRuntime,
    *,
    entrypoint: str,
    profile: SemanticRuntimeProfile,
) -> RuntimeTopologySnapshot:
    """Describe what is wired from runtime instances, not Settings alone."""
    orchestrator = runtime.adaptive_orchestrator
    planner = orchestrator.semantic_planner
    result_verifier = runtime.result_verifier
    budget = orchestrator.grounding_context_builder.grounding_budget
    prompt_builder = orchestrator.solver.prompt_builder
    result_wired = result_verifier is not None
    result_reachable = result_wired

    return RuntimeTopologySnapshot(
        entrypoint=entrypoint,
        components={
            "semantic_planner": _component(
                planner,
                mode=_planner_mode(planner),
                stage="pre_generation",
            ),
            "result_verifier": _component(
                result_verifier,
                mode="advisory" if result_reachable else "off",
                stage="post_execution" if result_reachable else None,
                reachable=result_reachable,
            ),
            "diagnostic_probe_runner": _component(
                runtime.diagnostic_probe_runner,
                mode="advisory" if result_reachable else "off",
                stage="post_execution" if result_reachable else None,
                reachable=result_reachable and runtime.diagnostic_probe_runner is not None,
            ),
        },
        solver={
            "strategy": _qualified_name(orchestrator.solver),
            "provider": profile.provider_identifier,
            "model": orchestrator.solver.model_name,
            "temperature": profile.temperature,
            "request_timeout_seconds": getattr(
                orchestrator.solver.chat_client,
                "request_timeout_seconds",
                None,
            ),
            "retry_policy": profile.retry_policy,
            "seed_policy": profile.seed_policy,
            "prompt_version": prompt_builder.prompt_version,
            "system_prompt_hash": _prompt_hash(prompt_builder, "system"),
            "user_template_hash": _prompt_hash(prompt_builder, "user_template"),
            "evidence_mode": profile.evidence_mode,
        },
        grounding={
            "builder": _qualified_name(orchestrator.grounding_context_builder),
            **budget.model_dump(),
            "value_linking_mode": "enabled"
            if orchestrator.grounding_context_builder.value_grounder is not None
            else "off",
        },
        policies={
            "validator_mode": runtime.validator_mode.value,
            "release_candidates_with_caveats": (
                orchestrator.escalation_policy.release_candidates_with_caveats
            ),
            "max_escalations": orchestrator.escalation_budget.max_escalations,
            "planner_mode": _planner_mode(planner),
            "result_verifier_mode": "advisory" if result_reachable else "off",
        },
        execution={
            "default_dialect": runtime.default_dialect,
            "read_only_required": runtime.execution_policy.read_only_required,
            "maximum_result_rows": runtime.execution_policy.maximum_result_rows,
            "statement_timeout_seconds": runtime.execution_policy.statement_timeout_seconds,
        },
    )


def compare_runtime_topologies(
    api: RuntimeTopologySnapshot,
    benchmark: RuntimeTopologySnapshot,
) -> RuntimeParityResult:
    """Compare semantic fields without normalizing differences away."""
    required_fields = (
        "components.semantic_planner.mode",
        "components.semantic_planner.wired",
        "components.result_verifier.mode",
        "components.result_verifier.wired",
        "components.result_verifier.reachable",
        "solver.strategy",
        "solver.provider",
        "solver.model",
        "solver.temperature",
        "solver.request_timeout_seconds",
        "solver.retry_policy",
        "solver.seed_policy",
        "solver.prompt_version",
        "solver.system_prompt_hash",
        "solver.user_template_hash",
        "solver.evidence_mode",
        "grounding.max_candidate_tables",
        "grounding.max_hydrated_tables",
        "grounding.max_columns_per_table",
        "grounding.max_total_columns",
        "grounding.max_relationships",
        "grounding.relationship_expansion_mode",
        "grounding.fill_column_budget",
        "grounding.small_db_threshold",
        "grounding.value_linking_mode",
        "policies.validator_mode",
        "policies.release_candidates_with_caveats",
        "policies.max_escalations",
        "policies.planner_mode",
        "policies.result_verifier_mode",
    )
    semantic_differences = [
        RuntimeParityDifference(
            field=field,
            api=_read_field(api.model_dump(), field),
            benchmark=_read_field(benchmark.model_dump(), field),
            status="FAIL",
            severity="HIGH",
            reason="Semantic runtime invariant differs between entrypoints.",
        )
        for field in required_fields
        if _read_field(api.model_dump(), field) != _read_field(benchmark.model_dump(), field)
    ]
    allowed = [
        RuntimeParityDifference(
            field="entrypoint",
            api=api.entrypoint,
            benchmark=benchmark.entrypoint,
            status="ALLOWED_INFRASTRUCTURE_DIFFERENCE",
            severity="LOW",
            reason="HTTP API and benchmark CLI are intentionally different transports.",
        ),
        RuntimeParityDifference(
            field="execution.default_dialect",
            api=api.execution["default_dialect"],
            benchmark=benchmark.execution["default_dialect"],
            status="ALLOWED_INFRASTRUCTURE_DIFFERENCE",
            severity="LOW",
            reason="Parity profiles may use different read-only database adapters/dialects.",
        ),
    ]
    return RuntimeParityResult(
        status="FAIL" if semantic_differences else "PASS",
        semantic_differences=semantic_differences,
        allowed_infrastructure_differences=allowed,
    )


def build_effective_runtime_manifest(
    api: RuntimeTopologySnapshot,
    benchmark: RuntimeTopologySnapshot,
    parity: RuntimeParityResult,
    *,
    inspection_source: Literal["fixture", "settings"] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "1",
        "git": {"commit": _git_output(["rev-parse", "HEAD"]), "dirty": _is_dirty()},
        "profiles": {"api": api.model_dump(), "benchmark": benchmark.model_dump()},
        "parity": parity.model_dump(),
    }
    if inspection_source is not None:
        payload["inspection_source"] = inspection_source
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _component(
    component: object | None,
    *,
    mode: str,
    stage: str | None,
    reachable: bool | None = None,
) -> RuntimeComponentDescriptor:
    wired = component is not None
    return RuntimeComponentDescriptor(
        wired=wired,
        reachable=wired if reachable is None else reachable,
        class_name=component.__class__.__name__ if component is not None else None,
        module=component.__class__.__module__ if component is not None else None,
        mode=mode,
        stage=stage,
    )


def _planner_mode(planner: object | None) -> str:
    if planner is None:
        return "off"
    return "llm" if getattr(planner, "chat_client", None) is not None else "deterministic"


def _prompt_hash(prompt_builder: Any, suffix: str) -> str:
    path = Path(prompt_builder.prompt_directory) / f"{prompt_builder.prompt_version}_{suffix}.md"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _qualified_name(instance: object) -> str:
    return f"{instance.__class__.__module__}.{instance.__class__.__name__}"


def _read_field(payload: dict[str, Any], field: str) -> Any:
    value: Any = payload
    for part in field.split("."):
        value = value[part]
    return value


def _git_output(args: list[str]) -> str:
    result = subprocess.run(["git", *args], capture_output=True, check=False, text=True)
    return result.stdout.strip() or "unknown"


def _is_dirty() -> bool:
    return bool(_git_output(["status", "--porcelain"]))
