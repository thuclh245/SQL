"""Emit a secret-free effective-runtime parity manifest from constructed instances."""

import argparse
import json
from pathlib import Path
from typing import Literal

from t2s.benchmark.runtime_factory import build_bird_runtime_for_database
from t2s.bootstrap.runtime_factory import (
    build_runtime_from_settings,
    build_semantic_runtime_profile,
)
from t2s.configuration import Settings
from t2s.integrations.openai_compatible import OpenAICompatibleChatClient
from t2s.runtime import (
    SemanticRuntimeProfile,
    build_effective_runtime_manifest,
    compare_runtime_topologies,
    inspect_effective_runtime,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
OUTPUT_DIRECTORY = PROJECT_ROOT / "results" / "runtime_parity"


def main() -> None:
    """Build a fixture or deployment-equivalent no-network topology inspection."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile-source",
        choices=("fixture", "settings"),
        default="fixture",
        help="Use a synthetic fixture profile or local non-secret Settings values.",
    )
    args = parser.parse_args()
    if args.profile_source == "settings":
        _inspect_settings_profile()
        return
    _inspect_fixture_profile()


def _inspect_fixture_profile() -> None:
    profile = SemanticRuntimeProfile(
        provider_identifier="openai_compatible",
        model_name="parity-fixture-model",
        temperature=0.0,
        prompt_version="v001",
        evidence_mode="none",
    )
    api_runtime = build_runtime_from_settings(
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
            # The inspector verifies construction and topology only. It never
            # executes a query, so readiness is deliberately outside this
            # no-network fixture check.
            runtime_require_populated_execution_database=False,
        )
    )
    if api_runtime is None:
        raise RuntimeError("Fixture API settings unexpectedly did not construct a runtime.")
    benchmark_runtime = build_bird_runtime_for_database(
        db_id=DATABASE_ID,
        db_path=DATABASE_PATH,
        tables_json_path=TABLES_PATH,
        chat_client=OpenAICompatibleChatClient(
            base_url="https://parity.invalid/v1", api_key=None, temperature=0.0
        ),
        model_name=profile.model_name,
        prompt_directory=PROMPTS_PATH,
        runtime_profile=profile,
    )
    api_snapshot = inspect_effective_runtime(
        api_runtime, entrypoint="fastapi:/v1/query", profile=profile
    )
    benchmark_snapshot = inspect_effective_runtime(
        benchmark_runtime, entrypoint="benchmark:run_benchmark", profile=profile
    )
    parity = compare_runtime_topologies(api_snapshot, benchmark_snapshot)
    manifest = build_effective_runtime_manifest(
        api_snapshot,
        benchmark_snapshot,
        parity,
        inspection_source="fixture",
    )
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIRECTORY / "effective_runtime_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIRECTORY / "runtime_parity_diff.json").write_text(
        json.dumps(parity.model_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIRECTORY / "validation_summary.json").write_text(
        json.dumps(
            {
                "status": parity.status,
                "semantic_mismatch_count": len(parity.semantic_differences),
                "allowed_difference_count": len(parity.allowed_infrastructure_differences),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"runtime parity: {parity.status}")


def _inspect_settings_profile() -> None:
    """Inspect local Settings without executing SQL or writing credentials.

    Readiness is disabled only for this topology inspection. It does not change
    deployment settings or make a query; deployment startup retains its normal
    populated-database readiness check.
    """
    settings = Settings()
    profile = build_semantic_runtime_profile(settings)
    inspection_settings = settings.model_copy(
        update={"runtime_require_populated_execution_database": False}
    )
    api_runtime = build_runtime_from_settings(inspection_settings)
    if api_runtime is None:
        raise RuntimeError("Configured Settings did not construct an API runtime.")
    if settings.runtime_sqlite_database_path is None:
        raise RuntimeError("Settings inspection currently requires runtime_sqlite_database_path.")
    if settings.runtime_catalog_tables_path is None or settings.runtime_catalog_database_id is None:
        raise RuntimeError("Settings inspection requires catalog tables path and database ID.")
    if settings.vllm_base_url is None:
        raise RuntimeError("Settings inspection requires vllm_base_url.")
    benchmark_runtime = build_bird_runtime_for_database(
        db_id=settings.runtime_catalog_database_id,
        db_path=settings.runtime_sqlite_database_path,
        tables_json_path=settings.runtime_catalog_tables_path,
        chat_client=OpenAICompatibleChatClient(
            base_url=settings.vllm_base_url,
            api_key=settings.llm_api_key,
            request_timeout_seconds=settings.llm_request_timeout_seconds,
            temperature=profile.temperature,
        ),
        model_name=profile.model_name,
        prompt_directory=settings.runtime_prompt_directory,
        runtime_profile=profile,
    )
    api_snapshot = inspect_effective_runtime(
        api_runtime,
        entrypoint="fastapi:/v1/query (settings inspection)",
        profile=profile,
    )
    benchmark_snapshot = inspect_effective_runtime(
        benchmark_runtime,
        entrypoint="benchmark:run_benchmark (settings inspection)",
        profile=profile,
    )
    _write_artifacts(api_snapshot, benchmark_snapshot, inspection_source="settings")


def _write_artifacts(
    api_snapshot: object,
    benchmark_snapshot: object,
    *,
    inspection_source: Literal["fixture", "settings"],
) -> None:
    """Persist only snapshots, which omit endpoint and credential fields."""
    parity = compare_runtime_topologies(api_snapshot, benchmark_snapshot)
    manifest = build_effective_runtime_manifest(
        api_snapshot,
        benchmark_snapshot,
        parity,
        inspection_source=inspection_source,
    )
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIRECTORY / "effective_runtime_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIRECTORY / "runtime_parity_diff.json").write_text(
        json.dumps(parity.model_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIRECTORY / "validation_summary.json").write_text(
        json.dumps(
            {
                "status": parity.status,
                "semantic_mismatch_count": len(parity.semantic_differences),
                "allowed_difference_count": len(parity.allowed_infrastructure_differences),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"runtime parity: {parity.status}")


if __name__ == "__main__":
    main()
