"""AST-based and path-based naming policy auditor for production modules."""

from __future__ import annotations

import ast
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.security.audit.contracts import AuditFinding, AuditResult, AuditStatus


class NamingPolicyChecker:
    """Audits production modules for forbidden phase, benchmark, and experiment tokens."""

    def __init__(
        self, config_path: Path | str = "configs/security/benchmark_registry.json"
    ) -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.phase_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.get("forbidden_phase_regex", [])
        ]
        self.benchmark_tokens = [
            t.lower() for t in self.config.get("forbidden_benchmark_identifiers", [])
        ]
        self.experiment_tokens = [
            t.lower() for t in self.config.get("forbidden_experiment_tokens", [])
        ]
        self.architecture_anti_tokens = [
            t.lower() for t in self.config.get("forbidden_architecture_tokens", [])
        ]
        self.production_packages = set(self.config.get("production_packages", []))

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            return {
                "forbidden_phase_regex": [
                    r"\b[pP]\d+\b",
                    r"\b[eE]\d+\b",
                    r"\b[pP]\d+[-_]?[eE]\d+\b",
                    r"\bphase[-_]?\d+\b",
                ],
                "forbidden_benchmark_identifiers": [
                    "bird",
                    "dev100",
                    "mini_dev",
                    "spider",
                    "pilot_v1",
                    "eval_v1",
                ],
                "forbidden_experiment_tokens": ["arm_a", "arm_b", "control_arm", "treatment_arm"],
                "forbidden_architecture_tokens": [
                    "holdout",
                    "benchmark_case",
                    "eval_split",
                    "test_partition",
                ],
                "production_packages": [
                    "api",
                    "bootstrap",
                    "catalog",
                    "configuration",
                    "contracts",
                    "database",
                    "errors",
                    "grounding",
                    "integrations",
                    "observability",
                    "orchestration",
                    "prompting",
                    "runtime",
                    "security",
                    "solver",
                    "verification",
                ],
            }
        loaded: dict[str, Any] = json.loads(self.config_path.read_text(encoding="utf-8"))
        return loaded


    def get_production_files(self, root_dir: Path | str = "src/t2s") -> list[Path]:
        prod_root = Path(root_dir)
        excluded = {"src/t2s/benchmark", "src/t2s/evaluation", "src/t2s/security/audit"}
        py_files = []
        for root, _dirs, files in os.walk(prod_root):
            rel = Path(root).as_posix()
            if any(rel == exc or rel.startswith(f"{exc}/") for exc in excluded):
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(Path(root) / f)
        return sorted(py_files)

    def check_naming(self, root_dir: Path | str = "src/t2s") -> AuditResult:
        files = self.get_production_files(root_dir)
        findings: list[AuditFinding] = []
        checked_identifiers = 0

        for file_path in files:
            # 1. Path check
            rel_path = file_path.as_posix()
            for p_pat in self.phase_patterns:
                m = p_pat.search(rel_path)
                if m:
                    findings.append(
                        AuditFinding(
                            finding_id=f"PATH-PHASE-{len(findings) + 1:03d}",
                            category="PATH_VIOLATION",
                            location=rel_path,
                            description="Production file path contains phase numbering pattern",
                            evidence=f"Matched '{m.group(0)}' in path {rel_path}",
                            severity="CRITICAL",
                        )
                    )

            # 2. Package classification check
            parts = file_path.relative_to(root_dir).parts
            if parts:
                top_pkg = parts[0]
                if top_pkg not in self.production_packages and not top_pkg.endswith(".py"):
                    findings.append(
                        AuditFinding(
                            finding_id=f"PKG-UNCLASSIFIED-{len(findings) + 1:03d}",
                            category="PACKAGE_CLASSIFICATION",
                            location=rel_path,
                            description=(
                                f"Package '{top_pkg}' is not classified in "
                                "production_packages policy"
                            ),
                            evidence=f"Directory '{top_pkg}' found in {rel_path}",
                            severity="HIGH",
                        )
                    )

            # 3. AST Identifier Inspection
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
            except Exception as exc:
                findings.append(
                    AuditFinding(
                        finding_id=f"PARSE-ERROR-{len(findings) + 1:03d}",
                        category="SYNTAX_ERROR",
                        location=rel_path,
                        description=f"Failed to parse file for AST inspection: {exc}",
                        evidence=str(exc),
                        severity="CRITICAL",
                    )
                )
                continue

            for node in ast.walk(tree):
                names_to_check = []
                if isinstance(node, ast.ClassDef):
                    names_to_check.append((node.name, node.lineno, "class_name"))
                elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    names_to_check.append((node.name, node.lineno, "function_name"))
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    names_to_check.append((node.id, node.lineno, "variable_name"))
                elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                    names_to_check.append((node.attr, node.lineno, "attribute_name"))

                for name, lineno, kind in names_to_check:
                    checked_identifiers += 1
                    name_parts = re.split(r"[_]+", name)
                    # Check phase regex
                    for p_pat in self.phase_patterns:
                        m = p_pat.search(name)
                        if not m:
                            for part in name_parts:
                                m = p_pat.search(part)
                                if m:
                                    break
                        if m:
                            matched_str = m.group(0)
                            findings.append(
                                AuditFinding(
                                    finding_id=f"ID-PHASE-{len(findings) + 1:03d}",
                                    category="IDENTIFIER_VIOLATION",
                                    location=f"{rel_path}:{lineno}",
                                    description=f"Phase token '{matched_str}' in {kind} '{name}'",
                                    evidence=name,
                                    severity="CRITICAL",
                                )
                            )
                    # Check benchmark identifiers
                    name_lower = name.lower()
                    for b_tok in self.benchmark_tokens:
                        if b_tok in name_lower:
                            findings.append(
                                AuditFinding(
                                    finding_id=f"ID-BENCHMARK-{len(findings) + 1:03d}",
                                    category="IDENTIFIER_VIOLATION",
                                    location=f"{rel_path}:{lineno}",
                                    description=(
                                        f"Benchmark identifier '{b_tok}' in {kind} '{name}'"
                                    ),
                                    evidence=name,
                                    severity="CRITICAL",
                                )
                            )
                    # Check experiment tokens
                    for exp_tok in self.experiment_tokens:
                        if re.search(rf"(?:^|_){re.escape(exp_tok)}(?:_|$)", name_lower):
                            findings.append(
                                AuditFinding(
                                    finding_id=f"ID-EXPERIMENT-{len(findings) + 1:03d}",
                                    category="IDENTIFIER_VIOLATION",
                                    location=f"{rel_path}:{lineno}",
                                    description=f"Experiment token '{exp_tok}' in {kind} '{name}'",
                                    evidence=name,
                                    severity="HIGH",
                                )
                            )

        status = AuditStatus.PASS if len(findings) == 0 else AuditStatus.FAIL
        return AuditResult(
            check_name="naming_policy_audit",
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
            tool_or_function="NamingPolicyChecker.check_naming",
            scope=str(root_dir),
            checked_count=len(files),
            violation_count=len(findings),
            violations=findings,
            evidence_paths=[str(self.config_path)],
            limitations=[
                "AST inspection covers defined symbols; string literals checked by "
                "secondary raw scan."
            ],
            details={
                "scanned_files_count": len(files),
                "checked_identifiers_count": checked_identifiers,
                "phase_patterns_count": len(self.phase_patterns),
                "benchmark_tokens_count": len(self.benchmark_tokens),
            },
        )


def audit_naming(
    target_dir: Path | str = "src/t2s",
    config_path: Path | str = "configs/security/benchmark_registry.json",
) -> AuditResult:
    """Convenience top-level wrapper to audit naming policies."""
    return NamingPolicyChecker(config_path=config_path).check_naming(root_dir=target_dir)
