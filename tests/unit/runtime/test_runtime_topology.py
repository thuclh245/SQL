"""Object-graph parity tests for the shared semantic runtime assembly."""

from pathlib import Path

from t2s.benchmark.runtime_factory import build_bird_runtime_for_database
from t2s.bootstrap.runtime_factory import build_runtime_from_settings
from t2s.configuration import Settings
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.runtime import (
    SemanticRuntimeProfile,
    build_effective_runtime_manifest,
    compare_runtime_topologies,
    inspect_effective_runtime,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATABASE_ID = "card_games"
DATABASE_PATH = (
    PROJECT_ROOT
    / "benchmarks"
    / "t2s"
    / "databases"
    / "official"
    / DATABASE_ID
    / "card_games.sqlite"
)
TABLES_PATH = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_tables.json"
PROMPTS_PATH = PROJECT_ROOT / "prompts" / "direct_sql"


def _profile() -> SemanticRuntimeProfile:
    return SemanticRuntimeProfile(
        provider_identifier="openai_compatible",
        model_name="parity-test-model",
        prompt_version="v001",
        evidence_mode="none",
    )


def _api_runtime(profile: SemanticRuntimeProfile):  # type: ignore[no-untyped-def]
    runtime = build_runtime_from_settings(
        Settings(
            environment="test",
            runtime_sqlite_database_path=DATABASE_PATH,
            runtime_catalog_tables_path=TABLES_PATH,
            runtime_catalog_database_id=DATABASE_ID,
            vllm_base_url="https://parity.invalid/v1",
            llm_provider=profile.provider_identifier,
            llm_model_name=profile.model_name,
            llm_temperature=profile.temperature,
            runtime_prompt_version=profile.prompt_version,
            runtime_evidence_mode=profile.evidence_mode,
            runtime_require_populated_execution_database=False,
        )
    )
    assert runtime is not None
    return runtime


def _benchmark_runtime(profile: SemanticRuntimeProfile):  # type: ignore[no-untyped-def]
    return build_bird_runtime_for_database(
        db_id=DATABASE_ID,
        db_path=DATABASE_PATH,
        tables_json_path=TABLES_PATH,
        chat_client=OpenAICompatibleChatClient(
            base_url="https://parity.invalid/v1", api_key=None, temperature=profile.temperature
        ),
        model_name=profile.model_name,
        prompt_directory=PROMPTS_PATH,
        runtime_profile=profile,
    )


def test_default_profile_disables_planner_and_wires_decoupled_result_verifier() -> None:
    profile = _profile()
    api = inspect_effective_runtime(_api_runtime(profile), entrypoint="api", profile=profile)
    benchmark = inspect_effective_runtime(
        _benchmark_runtime(profile), entrypoint="benchmark", profile=profile
    )

    for snapshot in (api, benchmark):
        assert snapshot.components["semantic_planner"].wired is False
        assert snapshot.components["semantic_planner"].mode == "off"
        assert snapshot.components["result_verifier"].wired is True
        assert snapshot.components["result_verifier"].reachable is True
        assert snapshot.components["result_verifier"].mode == "advisory"


def test_api_and_benchmark_share_effective_semantic_profile() -> None:
    profile = _profile()
    api = inspect_effective_runtime(_api_runtime(profile), entrypoint="api", profile=profile)
    benchmark = inspect_effective_runtime(
        _benchmark_runtime(profile), entrypoint="benchmark", profile=profile
    )

    result = compare_runtime_topologies(api, benchmark)
    assert result.status == "PASS"
    assert result.semantic_differences == []
    assert api.solver["prompt_version"] == benchmark.solver["prompt_version"]
    assert api.solver["system_prompt_hash"] == benchmark.solver["system_prompt_hash"]
    assert api.grounding == benchmark.grounding


def test_parity_checker_reports_a_synthetic_semantic_mismatch() -> None:
    profile = _profile()
    api = inspect_effective_runtime(_api_runtime(profile), entrypoint="api", profile=profile)
    mismatched = api.model_copy(
        update={"grounding": {**api.grounding, "max_columns_per_table": 13}}
    )

    result = compare_runtime_topologies(api, mismatched)
    assert result.status == "FAIL"
    assert result.semantic_differences[0].field == "grounding.max_columns_per_table"


def test_effective_manifest_is_secret_free_and_hashable() -> None:
    profile = _profile()
    api = inspect_effective_runtime(_api_runtime(profile), entrypoint="api", profile=profile)
    benchmark = inspect_effective_runtime(
        _benchmark_runtime(profile), entrypoint="benchmark", profile=profile
    )
    manifest = build_effective_runtime_manifest(
        api, benchmark, compare_runtime_topologies(api, benchmark)
    )

    encoded = str(manifest)
    assert "api_key" not in encoded
    assert "parity.invalid" not in encoded
    assert len(manifest["manifest_sha256"]) == 64


def test_profile_allows_a_decoupled_result_verifier() -> None:
    profile = SemanticRuntimeProfile(planner_mode="off", result_verifier_enabled=True)
    assert profile.result_verifier_enabled is True
