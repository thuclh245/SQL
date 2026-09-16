"""Logging and observability privacy auditor.

Audits production code for:
1. Direct print() calls that bypass structured logging and redaction.
2. Logging calls passing sensitive arguments (e.g. passwords, tokens, gold SQL).
3. Presence of automated secret scrubbing processor in structured logging configuration.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from t2s.security.audit.contracts import AuditFinding, AuditResult, AuditStatus, TriState

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOT = PROJECT_ROOT / "src" / "t2s"

LOG_METHOD_NAMES = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "critical",
    "exception",
    "msg",
    "log",
}
SENSITIVE_ARG_NAMES = {
    "password",
    "token",
    "secret",
    "api_key",
    "gold_sql",
    "gold_answer",
    "ground_truth",
}


def audit_logging_privacy(prod_root: Path | None = None) -> AuditResult:
    """Audit logging statements and privacy protections across production code."""
    target_dir = prod_root or PRODUCTION_ROOT
    now_iso = datetime.now(UTC).isoformat()

    violations: list[AuditFinding] = []
    scanned_files = 0
    logging_calls_count = 0
    print_calls_count = 0

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
            if not isinstance(node, ast.Call):
                continue

            # Check for print() calls
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                print_calls_count += 1
                violations.append(
                    AuditFinding(
                        finding_id="UNSTRUCTURED_PRINT_CALL",
                        category="LOGGING_HYGIENE",
                        location=f"{rel_path}:{node.lineno}",
                        description=(
                            "Unstructured print() call in production code "
                            "bypasses redaction filters"
                        ),
                        evidence=f"print(...) at line {node.lineno}",
                        severity="MEDIUM",
                    )
                )

            # Check for logging calls
            is_log_call = False
            if isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHOD_NAMES:
                is_log_call = True

            if is_log_call:
                logging_calls_count += 1
                # Check keyword arguments for sensitive keys
                for kw in node.keywords:
                    if kw.arg and kw.arg.lower() in SENSITIVE_ARG_NAMES:
                        violations.append(
                            AuditFinding(
                                finding_id=f"LOGGING_SENSITIVE_ARG_{kw.arg.upper()}",
                                category="PRIVACY_LEAK",
                                location=f"{rel_path}:{node.lineno}",
                                description=f"Logging call passes sensitive argument '{kw.arg}'",
                                evidence=f"kwarg {kw.arg} at line {node.lineno}",
                                severity="CRITICAL",
                            )
                        )

    # Check whether structlog has secret scrubbing processor configured
    logging_config_path = PROJECT_ROOT / "src" / "t2s" / "observability" / "logging.py"
    scrubbing_configured = TriState.UNKNOWN
    if logging_config_path.is_file():
        text = logging_config_path.read_text(encoding="utf-8")
        if "_scrub_secrets_processor" in text or "sanitize_data" in text:
            scrubbing_configured = TriState.YES
        else:
            scrubbing_configured = TriState.NO
            violations.append(
                AuditFinding(
                    finding_id="MISSING_LOG_SECRET_SCRUBBER",
                    category="PRIVACY_HYGIENE",
                    location=logging_config_path.relative_to(PROJECT_ROOT).as_posix(),
                    description=(
                        "Structured logging pipeline does not include secret sanitization processor"
                    ),
                    evidence="sanitize_data processor not found in structlog config",
                    severity="HIGH",
                )
            )

    status = AuditStatus.PASS if not violations else AuditStatus.FAIL

    return AuditResult(
        check_name="logging_privacy",
        status=status,
        timestamp=now_iso,
        tool_or_function="audit_logging_privacy",
        scope=f"production_code={scanned_files}_files",
        checked_count=scanned_files,
        violation_count=len(violations),
        violations=violations,
        evidence_paths=[logging_config_path.relative_to(PROJECT_ROOT).as_posix()],
        limitations=["Only static AST analysis of production Python files performed"],
        details={
            "scanned_files_count": scanned_files,
            "logging_calls_count": logging_calls_count,
            "print_calls_count": print_calls_count,
            "secret_scrubbing_configured": scrubbing_configured.value,
        },
    )
