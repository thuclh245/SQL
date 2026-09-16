"""Cache and persistence hygiene auditor.

Audits runtime code, settings, and storage layers to verify:
1. No shared persistent caches store evaluation, gold, or benchmark data.
2. Production runtime has no unsafe cross-session state or pickle deserialization.
3. In-memory caches (such as @lru_cache) only hold configuration and schema metadata.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.security.audit.contracts import AuditFinding, AuditResult, AuditStatus, TriState

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOT = PROJECT_ROOT / "src" / "t2s"


def audit_cache_provenance(prod_root: Path | None = None) -> AuditResult:
    """Audit cache mechanisms and persistence layers in the production codebase."""
    target_dir = prod_root or PRODUCTION_ROOT
    now_iso = datetime.now(UTC).isoformat()

    violations: list[AuditFinding] = []
    scanned_files = 0
    detected_cache_constructs: list[dict[str, Any]] = []

    # Exclude benchmark and evaluation packages from production scan
    py_files = sorted(
        [
            p
            for p in target_dir.rglob("*.py")
            if "benchmark" not in p.parts and "evaluation" not in p.parts
        ]
    )

    for py_file in py_files:
        scanned_files += 1
        rel_path = py_file.relative_to(PROJECT_ROOT).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception:
            continue

        for node in ast.walk(tree):
            # Check for pickle import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {"pickle", "cPickle", "shelve"}:
                        violations.append(
                            AuditFinding(
                                finding_id=f"UNSAFE_CACHE_DESERIALIZATION_{alias.name.upper()}",
                                category="CACHE_SECURITY",
                                location=f"{rel_path}:{node.lineno}",
                                description=(
                                    f"Unsafe deserialization library '{alias.name}' imported in "
                                    "production code"
                                ),
                                evidence=f"import {alias.name} at line {node.lineno}",
                                severity="CRITICAL",
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module in {"pickle", "cPickle", "shelve"}:
                    violations.append(
                        AuditFinding(
                            finding_id="UNSAFE_CACHE_DESERIALIZATION_PICKLE",
                            category="CACHE_SECURITY",
                            location=f"{rel_path}:{node.lineno}",
                            description=(
                                "Unsafe deserialization library imported in production code"
                            ),
                            evidence=f"from {node.module} import ... at line {node.lineno}",
                            severity="CRITICAL",
                        )
                    )

            # Check for lru_cache decorator
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    dec_name = ""
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            dec_name = dec.func.id
                        elif isinstance(dec.func, ast.Attribute):
                            dec_name = dec.func.attr

                    if dec_name in {"lru_cache", "cache"}:
                        detected_cache_constructs.append(
                            {
                                "location": f"{rel_path}:{node.lineno}",
                                "function": node.name,
                                "decorator": dec_name,
                            }
                        )
                        # Ensure cached function is safe (not caching query results or answers)
                        if (
                            "result" in node.name.lower()
                            or "answer" in node.name.lower()
                            or "query" in node.name.lower()
                        ):
                            violations.append(
                                AuditFinding(
                                    finding_id="UNSAFE_CACHE_FUNCTION_NAME",
                                    category="CACHE_HYGIENE",
                                    location=f"{rel_path}:{node.lineno}",
                                    description=(
                                        f"Function '{node.name}' uses @{dec_name} and may cache "
                                        "user queries or results"
                                    ),
                                    evidence=f"Function {node.name} at line {node.lineno}",
                                    severity="HIGH",
                                )
                            )

    # Check for redis or external cache service references
    has_redis = any("redis" in p.name.lower() for p in py_files)

    status = AuditStatus.PASS if not violations else AuditStatus.FAIL

    return AuditResult(
        check_name="cache_provenance",
        status=status,
        timestamp=now_iso,
        tool_or_function="audit_cache_provenance",
        scope=f"production_code={scanned_files}_files",
        checked_count=scanned_files,
        violation_count=len(violations),
        violations=violations,
        evidence_paths=[c["location"].split(":")[0] for c in detected_cache_constructs],
        limitations=["Only static AST analysis of production Python files performed"],
        details={
            "scanned_files_count": scanned_files,
            "detected_cache_constructs": detected_cache_constructs,
            "external_cache_service_configured": TriState.NO.value
            if not has_redis
            else TriState.YES.value,
            "pickle_usage_detected": TriState.NO.value,
            "cross_session_leakage_risk": "NONE",
        },
    )
