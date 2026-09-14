import json
from argparse import Namespace
from pathlib import Path

import pytest

from t2s.benchmark.artifacts import build_reproducibility_manifest, write_json
from t2s.benchmark.invariants import (
    resolve_official_database_path,
    verify_benchmark_database_integrity,
)
from t2s.benchmark.metrics import aggregate_benchmark_metrics
from t2s.benchmark.runner import run_benchmark
from t2s.errors import BenchmarkDatabaseIntegrityError


def test_manifest_does_not_serialize_api_key(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text("{}\n", encoding="utf-8")
    manifest = build_reproducibility_manifest(
        run_id="run-1",
        dataset_path=dataset_path,
        database_root=tmp_path / "db",
        provider="openai_compatible",
        model="chat-5-mini",
        base_url="https://provider.example/v1?api_key=fake-secret",
        prompt_version="v001",
        case_ids=["case-1"],
        temperature=0.0,
        max_tokens=2048,
        provider_request_policy={
            "token_limit_parameter": "max_completion_tokens",
            "requested_temperature": 0.0,
            "effective_temperature": None,
            "temperature_sent": False,
        },
    )

    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)
    serialized_manifest = manifest_path.read_text(encoding="utf-8")

    assert "fake-secret" not in serialized_manifest
    assert "chat-5-mini" in serialized_manifest
    assert manifest["provider_request_policy"]["requested_temperature"] == 0.0
    assert manifest["provider_request_policy"]["temperature_sent"] is False


def test_metric_aggregation_reports_required_slices() -> None:
    metrics = aggregate_benchmark_metrics(
        [
            {
                "runtime_status": "SUCCESS",
                "execution_correct": True,
                "latency_ms": 10,
                "t2s_stratum": "S1",
                "bird_difficulty": "simple",
                "db_id": "db_a",
                "escalated": False,
                "grounding_calls": 1,
                "solver_calls": 1,
                "tokens_input": None,
                "tokens_output": None,
            },
            {
                "runtime_status": "EXECUTION_FAILED",
                "execution_correct": False,
                "latency_ms": 30,
                "t2s_stratum": "S2",
                "bird_difficulty": "moderate",
                "db_id": "db_b",
                "escalated": True,
                "same_context_stop": True,
                "grounding_calls": 2,
                "solver_calls": 1,
                "tokens_input": None,
                "tokens_output": None,
            },
        ]
    )

    assert metrics["overall"]["case_count"] == 2
    assert metrics["overall"]["execution_accuracy"] == 0.5
    assert metrics["by_t2s_stratum"]["S1"]["correct"] == 1
    assert metrics["runtime"]["execution_failures"] == 1
    assert json.dumps(metrics)


def test_unknown_db_id_resolution_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_official_database_path(tmp_path, "missing_db")


def test_schema_only_database_root_is_rejected_before_scoring() -> None:
    with pytest.raises(BenchmarkDatabaseIntegrityError, match="contains no data rows"):
        verify_benchmark_database_integrity(
            Path("benchmarks/t2s/databases/schema_only_placeholders"),
            {"california_schools"},
        )


def test_official_populated_database_root_is_accepted() -> None:
    verify_benchmark_database_integrity(
        Path("benchmarks/t2s/databases/official"),
        {"california_schools"},
    )


@pytest.mark.anyio
async def test_provider_config_without_api_key_fails_before_run_output(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        '{"case_id":"case-1","inference":{"question":"Q","db_id":"db"}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing API key"):
        await run_benchmark(
            Namespace(
                provider="openai_compatible",
                model="chat-5-mini",
                base_url="https://provider.example/v1",
                api_key=None,
                dataset=str(dataset_path),
                database_root=str(tmp_path / "db"),
                tables_json=str(tmp_path / "tables.json"),
                prompt_directory="prompts/direct_sql",
                pilot_dataset=str(dataset_path),
                verify_invariants=False,
                limit=None,
                case_id=[],
                db_id=[],
                output=str(tmp_path / "results"),
                run_id="run-1",
                timeout_seconds=1.0,
                temperature=0.0,
                max_output_tokens=128,
            )
        )
