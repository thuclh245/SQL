import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
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
    lines = [
        f"# T2S Benchmark Summary: {run_id}",
        "",
        f"- Total Cases: {overall['case_count']}",
        (
            "- Strict Execution Accuracy (EX): "
            f"{overall['correct']}/{overall['total']} "
            f"({overall['execution_accuracy']:.2%})"
        ),
        (f"- Successful Execution Rate: {overall['successful_execution_rate']:.2%}"),
    ]

    if "practical_accuracy" in overall and "grade_counts" in overall:
        counts = overall["grade_counts"]
        pcts = overall["grade_percentages"]
        lines.extend(
            [
                (
                    f"- Practical Business Accuracy (A + B): "
                    f"{overall['practical_correct']}/{overall['total']} "
                    f"({overall['practical_accuracy']:.2%})"
                ),
                "",
                "## Evaluation Breakdown (A–F Grading)",
                "",
                "| Grade | Evaluation Meaning | Count | Percentage |",
                "| :---: | :--- | :---: | :---: |",
                f"| **A** | **Exact Match** (Matches gold result shape & rows) | {counts.get('A', 0)} | {pcts.get('A', 0.0):.2%} |",
                f"| **B** | **Practical Match** (Extra projected columns or DISTINCT variance, core business data intact) | {counts.get('B', 0)} | {pcts.get('B', 0.0):.2%} |",
                f"| **C** | **Near Miss** (High overlap >=50%, missing LIMIT or NULL ordering difference) | {counts.get('C', 0)} | {pcts.get('C', 0.0):.2%} |",
                f"| **D** | **Semantic Divergence** (Executed cleanly but wrong logic / incorrect rows) | {counts.get('D', 0)} | {pcts.get('D', 0.0):.2%} |",
                f"| **F** | **Failure** (Execution error, generation failure, or rejected) | {counts.get('F', 0)} | {pcts.get('F', 0.0):.2%} |",
                "",
            ]
        )
    else:
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


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
    prompts_dir = Path("prompts/direct_sql")
    prompt_hashes: dict[str, str] = {}
    if prompts_dir.exists():
        for prompt_file in sorted(prompts_dir.glob(f"{prompt_version}*.md")):
            prompt_hashes[prompt_file.name] = sha256_file(prompt_file)

    planner_prompt_hash = hashlib.sha256(
        b"You are a Grounded Semantic Planner for an enterprise Text-to-SQL system.\n"
        b"Interpret the semantic meaning of the user question given ONLY the "
        b"authorized grounding context and metadata.\n"
        b"CRITICAL OPERATIONAL RULES:\n"
        b"1. Do NOT generate SQL statements.\n"
        b"2. Use only supplied grounding evidence; do not invent missing business definitions.\n"
        b"3. If metric grain, unit, or business meaning is unstated in metadata, mark it unknown.\n"
        b"4. Return structured output conforming strictly to SemanticPlan schema.\n"
    ).hexdigest()

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": _git_output(["git", "rev-parse", "HEAD"]),
        "git_dirty_status": _git_output(["git", "status", "--short"]),
        "dataset_path": str(dataset_path),
        "dataset_sha256": sha256_file(dataset_path),
        "database_root": str(database_root),
        "database_identity": str(database_root),
        "dialect": "sqlite",
        "provider": provider,
        "model": model,
        "base_url_identifier": _redact_url(base_url),
        "prompt_version": prompt_version,
        "prompt_hashes": prompt_hashes,
        "solver_prompt_hashes": prompt_hashes,
        "planner_prompt_hash": planner_prompt_hash,
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

    # Canonical experiment config hash
    config_repr = json.dumps(
        {
            "model": model,
            "provider": provider,
            "prompt_version": prompt_version,
            "dataset_sha256": manifest["dataset_sha256"],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "solver_prompt_hashes": prompt_hashes,
            "planner_prompt_hash": planner_prompt_hash,
        },
        sort_keys=True,
    )
    manifest["experiment_config_hash"] = hashlib.sha256(config_repr.encode("utf-8")).hexdigest()
    return manifest


def _git_output(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _redact_url(base_url: str) -> str:
    return base_url.split("?")[0].replace("//", "//")
