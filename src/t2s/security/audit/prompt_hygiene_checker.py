"""Prompt hygiene auditor.

Inspects all prompt templates and runtime-reachable prompts for:
1. Forbidden benchmark tokens and datasets (e.g. bird, dev100, spider).
2. Forbidden phase and experiment tokens (e.g. P8, arm_a).
3. Few-shot example contamination and hardcoded benchmark fixtures.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.security.audit.contracts import AuditFinding, AuditResult, AuditStatus

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = PROJECT_ROOT / "configs" / "security" / "benchmark_registry.json"
PROMPTS_DIR = PROJECT_ROOT / "prompts"


def _load_registry() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Benchmark registry missing at {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


def audit_prompts(prompts_dir: Path | None = None) -> AuditResult:
    """Audit all prompt templates for contamination, leaks, and hardcoded fixtures."""
    target_dir = prompts_dir or PROMPTS_DIR
    registry = _load_registry()
    now_iso = datetime.now(UTC).isoformat()

    forbidden_benchmarks = [b.lower() for b in registry.get("forbidden_benchmark_identifiers", [])]
    forbidden_tokens = [t.lower() for t in registry.get("forbidden_architecture_tokens", [])]
    forbidden_experiments = [e.lower() for e in registry.get("forbidden_experiment_tokens", [])]
    phase_patterns = [re.compile(p) for p in registry.get("forbidden_phase_regex", [])]

    if not target_dir.is_dir():
        return AuditResult(
            check_name="prompt_hygiene",
            status=AuditStatus.FAIL,
            timestamp=now_iso,
            tool_or_function="audit_prompts",
            scope=str(target_dir),
            checked_count=0,
            violation_count=1,
            violations=[
                AuditFinding(
                    finding_id="PROMPT_DIR_MISSING",
                    category="PROMPT_HYGIENE",
                    location=str(target_dir),
                    description="Prompt directory does not exist",
                    evidence="Directory not found on filesystem",
                    severity="CRITICAL",
                )
            ],
            evidence_paths=[str(target_dir)],
            limitations=[],
            details={},
        )

    prompt_files = sorted(
        [
            p
            for p in target_dir.glob("**/*")
            if p.is_file() and p.suffix in {".txt", ".md", ".json", ".yaml", ".yml"}
        ]
    )

    violations: list[AuditFinding] = []
    scanned_count = len(prompt_files)
    reachable_count = 0
    few_shot_count = 0
    benchmark_fixture_count = 0

    # Runtime reachable prompt prefixes/directories
    runtime_reachable_prefixes = ("direct_sql", "sql_verifier")

    for pfile in prompt_files:
        try:
            rel_path = pfile.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            rel_path = pfile.as_posix()
        is_reachable = any(part in rel_path for part in runtime_reachable_prefixes)
        if is_reachable:
            reachable_count += 1

        content = pfile.read_text(encoding="utf-8")
        content_lower = content.lower()

        # Check forbidden benchmarks
        for b in forbidden_benchmarks:
            if re.search(rf"\b{re.escape(b)}\b", content_lower):
                violations.append(
                    AuditFinding(
                        finding_id=f"FORBIDDEN_BENCHMARK_IN_PROMPT_{b.upper()}",
                        category="PROMPT_HYGIENE",
                        location=rel_path,
                        description=(
                            f"Prompt template contains forbidden benchmark identifier '{b}'"
                        ),
                        evidence=f"Matched '{b}' in {rel_path}",
                        severity="CRITICAL",
                    )
                )
                benchmark_fixture_count += 1

        # Check forbidden architecture tokens
        for t in forbidden_tokens:
            if re.search(rf"\b{re.escape(t)}\b", content_lower):
                violations.append(
                    AuditFinding(
                        finding_id=f"FORBIDDEN_ARCH_TOKEN_{t.upper()}",
                        category="PROMPT_HYGIENE",
                        location=rel_path,
                        description=f"Prompt template contains forbidden architecture token '{t}'",
                        evidence=f"Matched '{t}' in {rel_path}",
                        severity="HIGH",
                    )
                )

        # Check forbidden phase patterns
        for pattern in phase_patterns:
            m = pattern.search(content)
            if m:
                violations.append(
                    AuditFinding(
                        finding_id="FORBIDDEN_PHASE_IN_PROMPT",
                        category="PROMPT_HYGIENE",
                        location=rel_path,
                        description=(
                            f"Prompt template contains historical phase identifier '{m.group(0)}'"
                        ),
                        evidence=(
                            f"Matched '{m.group(0)}' against regex '{pattern.pattern}' in "
                            f"{rel_path}"
                        ),
                        severity="HIGH",
                    )
                )

        # Check forbidden experiment tokens
        for exp in forbidden_experiments:
            if re.search(rf"\b{re.escape(exp)}\b", content_lower):
                violations.append(
                    AuditFinding(
                        finding_id=f"FORBIDDEN_EXPERIMENT_IN_PROMPT_{exp.upper()}",
                        category="PROMPT_HYGIENE",
                        location=rel_path,
                        description=f"Prompt template contains forbidden experiment token '{exp}'",
                        evidence=f"Matched '{exp}' in {rel_path}",
                        severity="HIGH",
                    )
                )

        # Check for hardcoded few-shot SQL examples (e.g. Example: Question: ... SQL: SELECT ...)
        if re.search(
            r"(?:example|few[-_]?shot)\s*\d*:\s*(?:question:.*?sql:|query:.*?select)",
            content_lower,
            re.DOTALL,
        ):
            violations.append(
                AuditFinding(
                    finding_id="FEW_SHOT_SQL_FIXTURE_FOUND",
                    category="PROMPT_HYGIENE",
                    location=rel_path,
                    description="Prompt contains hardcoded few-shot SQL example fixture",
                    evidence="Matched few-shot Q/A regex pattern in prompt text",
                    severity="CRITICAL",
                )
            )
            few_shot_count += 1

    status = AuditStatus.PASS if not violations else AuditStatus.FAIL

    return AuditResult(
        check_name="prompt_hygiene",
        status=status,
        timestamp=now_iso,
        tool_or_function="audit_prompts",
        scope=f"prompts_dir={target_dir.as_posix()}",
        checked_count=scanned_count,
        violation_count=len(violations),
        violations=violations,
        evidence_paths=[str(p) for p in prompt_files],
        limitations=["Only static text files (.md, .txt, .json, .yaml, .yml) in prompts/ scanned"],
        details={
            "scanned_prompt_count": scanned_count,
            "reachable_prompt_count": reachable_count,
            "few_shot_examples_count": few_shot_count,
            "benchmark_fixture_count": benchmark_fixture_count,
        },
    )
