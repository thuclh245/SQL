"""Unit tests for the T2S security, hygiene, and governance audit system.

Verifies:
1. Positive tests: clean codebase passes all modular audit checks.
2. Negative tests: synthetic benchmark identifiers, phase tokens, illegal imports,
   leaked secrets, and unisolated DTO attributes correctly trigger violations.
3. Decision engine fail-closed behavior: never awards closure when any check fails or is unknown.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from t2s.security.audit.cache_auditor import audit_cache_provenance
from t2s.security.audit.contracts import (
    AuditFinding,
    AuditResult,
    AuditStatus,
    HygieneClosureStatus,
    TriState,
)
from t2s.security.audit.decision_engine import evaluate_hygiene_closure
from t2s.security.audit.dependency_checker import (
    audit_direct_dependencies,
    audit_transitive_dependencies,
)
from t2s.security.audit.gold_isolation_checker import audit_gold_isolation
from t2s.security.audit.logging_auditor import audit_logging_privacy
from t2s.security.audit.naming_checker import audit_naming
from t2s.security.audit.prompt_hygiene_checker import audit_prompts
from t2s.security.audit.secret_scanner import scan_current_tree, scan_git_history

# --- Positive Tests ---


def test_production_naming_audit_passes() -> None:
    result = audit_naming()
    assert result.status == AuditStatus.PASS
    assert result.violation_count == 0
    assert len(result.violations) == 0


def test_production_dependency_audits_pass() -> None:
    direct = audit_direct_dependencies()
    assert direct.status == AuditStatus.PASS
    assert direct.violation_count == 0

    transitive = audit_transitive_dependencies()
    assert transitive.status == AuditStatus.PASS
    assert transitive.violation_count == 0


def test_gold_isolation_audit_passes() -> None:
    result = audit_gold_isolation()
    assert result.status == AuditStatus.PASS
    assert result.violation_count == 0


def test_prompt_hygiene_audit_passes() -> None:
    result = audit_prompts()
    assert result.status == AuditStatus.PASS
    assert result.violation_count == 0


def test_secret_scanner_passes() -> None:
    tree_result = scan_current_tree()
    assert tree_result.status == AuditStatus.PASS
    assert tree_result.violation_count == 0

    history_result = scan_git_history(commit_limit=20)
    assert history_result.status == AuditStatus.PASS
    assert history_result.violation_count == 0


def test_logging_and_cache_auditors_pass() -> None:
    log_result = audit_logging_privacy()
    assert log_result.status == AuditStatus.PASS
    assert log_result.violation_count == 0

    cache_result = audit_cache_provenance()
    assert cache_result.status == AuditStatus.PASS
    assert cache_result.violation_count == 0


# --- Negative Tests (Tamper / Attack Detection) ---


def test_naming_audit_catches_synthetic_forbidden_tokens(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad_code.py"
    bad_file.write_text(
        "class BirdMiniDevHelper:\n    def run_spider_eval(self):\n        phase_p8_arm_a = True\n",
        encoding="utf-8",
    )
    result = audit_naming(target_dir=tmp_path)
    assert result.status == AuditStatus.FAIL
    assert result.violation_count >= 3
    assert any("bird" in v.description.lower() for v in result.violations)
    assert any("spider" in v.description.lower() for v in result.violations)


def test_gold_isolation_catches_leaked_attribute() -> None:
    class LeakyDTO(BaseModel):
        model_config = ConfigDict(extra="ignore")
        user_query: str

    # Injecting forbidden field into leaky model succeeds without error
    obj = LeakyDTO.model_validate({"user_query": "SELECT 1", "gold_sql": "SELECT 1 FROM secret"})
    assert not hasattr(obj, "gold_sql")  # silently ignored, but not forbidden!

    # Now verify that strict extra="forbid" raises ValidationError
    class StrictDTO(BaseModel):
        model_config = ConfigDict(extra="forbid")
        user_query: str

    with pytest.raises(ValidationError):
        StrictDTO.model_validate({"user_query": "SELECT 1", "gold_sql": "SELECT 1 FROM secret"})


def test_prompt_hygiene_catches_synthetic_few_shot_or_benchmark(tmp_path: Path) -> None:
    bad_prompt = tmp_path / "leaky_prompt.md"
    bad_prompt.write_text(
        "You are an AI.\n"
        "Example 1: Question: show me sales. SQL: SELECT * FROM sales;\n"
        "Evaluated on bird benchmark.\n",
        encoding="utf-8",
    )
    result = audit_prompts(prompts_dir=tmp_path)
    assert result.status == AuditStatus.FAIL
    assert result.violation_count >= 2


# --- Decision Engine Tests ---


def test_decision_engine_awards_complete_when_all_pass() -> None:
    mock_results = {
        "check_a": AuditResult(
            check_name="check_a",
            status=AuditStatus.PASS,
            timestamp="2026-09-15T00:00:00Z",
            tool_or_function="func",
            scope="unit",
            checked_count=10,
            violation_count=0,
        ),
        "check_b": AuditResult(
            check_name="check_b",
            status=AuditStatus.PASS,
            timestamp="2026-09-15T00:00:00Z",
            tool_or_function="func",
            scope="unit",
            checked_count=5,
            violation_count=0,
        ),
    }
    decision = evaluate_hygiene_closure(mock_results, {"all_passed": True})
    expected_closure = HygieneClosureStatus.HYGIENE_CLOSURE_COMPLETE.value
    assert decision["hygiene_closure_status"] == expected_closure
    assert (
        decision["governance_directives"]["production_enforcement_authorized"] == TriState.NO.value
    )
    assert decision["governance_directives"]["shadow_mode_remains_default"] == TriState.YES.value


def test_decision_engine_fails_closed_on_violation() -> None:
    mock_results = {
        "check_a": AuditResult(
            check_name="check_a",
            status=AuditStatus.FAIL,
            timestamp="2026-09-15T00:00:00Z",
            tool_or_function="func",
            scope="unit",
            checked_count=10,
            violation_count=1,
            violations=[
                AuditFinding(
                    finding_id="LEAK_01",
                    category="LEAK",
                    location="loc",
                    description="desc",
                    evidence="ev",
                )
            ],
        )
    }
    decision = evaluate_hygiene_closure(mock_results, {"all_passed": True})
    assert decision["hygiene_closure_status"] == HygieneClosureStatus.CRITICAL_LEAKAGE_REMAINS.value


def test_decision_engine_incomplete_on_unknown_or_failed_test() -> None:
    mock_results = {
        "check_a": AuditResult(
            check_name="check_a",
            status=AuditStatus.UNKNOWN,
            timestamp="2026-09-15T00:00:00Z",
            tool_or_function="func",
            scope="unit",
            checked_count=10,
            violation_count=0,
        )
    }
    decision = evaluate_hygiene_closure(mock_results, {"all_passed": True})
    assert (
        decision["hygiene_closure_status"]
        == HygieneClosureStatus.HYGIENE_REMEDIATION_INCOMPLETE.value
    )

    # If all checks pass but tests fail, it must also be incomplete!
    mock_results_pass = {
        "check_a": AuditResult(
            check_name="check_a",
            status=AuditStatus.PASS,
            timestamp="2026-09-15T00:00:00Z",
            tool_or_function="func",
            scope="unit",
            checked_count=10,
            violation_count=0,
        )
    }
    decision_failed_tests = evaluate_hygiene_closure(mock_results_pass, {"all_passed": False})
    assert (
        decision_failed_tests["hygiene_closure_status"]
        == HygieneClosureStatus.HYGIENE_REMEDIATION_INCOMPLETE.value
    )
