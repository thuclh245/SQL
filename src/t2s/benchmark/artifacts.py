import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as jsonl_file:
        jsonl_file.write(json.dumps(payload, sort_keys=True) + "\n")


def write_summary_markdown(path: Path, metrics: dict[str, Any], run_id: str) -> None:
    overall = metrics["overall"]
    path.write_text(
        "\n".join(
            [
                f"# T2S Benchmark Summary: {run_id}",
                "",
                f"- Cases: {overall['case_count']}",
                (
                    "- Execution Accuracy: "
                    f"{overall['correct']}/{overall['total']} "
                    f"({overall['execution_accuracy']:.2%})"
                ),
                (f"- Successful execution rate: {overall['successful_execution_rate']:.2%}"),
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_reproducibility_manifest(
    run_id: str,
    dataset_path: Path,
    database_root: Path,
    provider: str,
    model: str,
    base_url: str,
    prompt_version: str,
    case_ids: list[str],
    temperature: float,
    max_tokens: int,
    provider_request_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": _git_output(["git", "rev-parse", "HEAD"]),
        "git_dirty_status": _git_output(["git", "status", "--short"]),
        "dataset_path": str(dataset_path),
        "dataset_sha256": sha256_file(dataset_path),
        "database_root": str(database_root),
        "provider": provider,
        "model": model,
        "base_url_identifier": _redact_url(base_url),
        "prompt_version": prompt_version,
        "grounding_config": {"source": "GroundingBudget defaults"},
        "escalation_config": {"max_escalations": 1},
        "runtime_config": {
            "statement_timeout_seconds": 30,
            "max_result_rows": 1000,
            "read_only": True,
        },
        "temperature": temperature,
        "seed": None,
        "max_tokens": max_tokens,
        "case_ids": case_ids,
    }
    if provider_request_policy is not None:
        manifest["provider_request_policy"] = provider_request_policy
    return manifest


def _git_output(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _redact_url(base_url: str) -> str:
    return base_url.split("?")[0].replace("//", "//")
