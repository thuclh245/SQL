"""Executable gold isolation contract tester for production DTOs and models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from t2s.contracts.grounding_context import GroundingContext
from t2s.contracts.query_request import QueryRequest
from t2s.contracts.sql_candidate import SqlCandidate
from t2s.runtime.runtime_contracts import (
    RuntimeExecutionResult,
    RuntimeState,
    RuntimeStatus,
    RuntimeTrace,
)
from t2s.security.audit.contracts import AuditFinding, AuditResult, AuditStatus
from t2s.solver.solver_request import SolverRequest
from t2s.solver.solver_response import SolverStructuredOutput
from t2s.verification.contracts import VerificationInput
from t2s.verification.sql_semantic_risk_validator import ValidationInput


class GoldIsolationChecker:
    """Injects forbidden gold/evaluation fields into production DTOs to prove isolation."""

    FORBIDDEN_FIELDS = [
        "gold_sql",
        "gold_answer",
        "gold_tables",
        "gold_columns",
        "expected_sql",
        "expected_result",
        "reference_sql",
        "ground_truth",
        "execution_score",
        "correctness",
    ]

    @staticmethod
    def _dto_factories() -> dict[str, Any]:
        return {
            "ValidationInput": {
                "cls": ValidationInput,
                "valid_payload": {
                    "question": "Count users",
                    "candidate_sql": "SELECT COUNT(*) FROM users",
                },
            },
            "QueryRequest": {
                "cls": QueryRequest,
                "valid_payload": {
                    "question": "Count users",
                },
            },
            "VerificationInput": {
                "cls": VerificationInput,
                "valid_payload": {
                    "question": "Count users",
                    "evidence": "users table",
                    "dialect": "sqlite",
                    "authorized_schema": "TABLE users (id INT)",
                    "candidate_sql": "SELECT COUNT(*) FROM users",
                },
            },
            "SqlCandidate": {
                "cls": SqlCandidate,
                "valid_payload": {
                    "sql": "SELECT COUNT(*) FROM users",
                    "dialect": "sqlite",
                    "generation_trace": {
                        "run_id": "r1",
                        "model_name": "test-model",
                        "prompt_version": "v1",
                    },
                },
            },
            "SolverRequest": {
                "cls": SolverRequest,
                "valid_payload": {
                    "run_id": "r1",
                    "query_request": QueryRequest(question="Count users"),
                    "target_dialect": "sqlite",
                    "grounding_context": GroundingContext(scope_id="default", tables=[]),
                },
            },
            "SolverStructuredOutput": {
                "cls": SolverStructuredOutput,
                "valid_payload": {
                    "sql": "SELECT 1",
                    "dialect": "sqlite",
                    "referenced_tables": [],
                    "referenced_columns": [],
                    "expected_columns": [],
                    "assumptions": [],
                    "unresolved": [],
                },
            },
            "GroundingContext": {
                "cls": GroundingContext,
                "valid_payload": {
                    "scope_id": "default",
                    "tables": [],
                },
            },
            "RuntimeExecutionResult": {
                "cls": RuntimeExecutionResult,
                "valid_payload": {
                    "run_id": "test-run",
                    "status": RuntimeStatus.COMPLETED,
                    "trace": RuntimeTrace(run_id="test-run", final_state=RuntimeState.COMPLETED),
                },
            },
        }

    def check_gold_isolation(self) -> AuditResult:
        dto_factories = self._dto_factories()
        findings: list[AuditFinding] = []
        total_injections = 0
        successful_rejections = 0

        for dto_name, config in dto_factories.items():
            cls = config["cls"]
            base_payload = config["valid_payload"]

            # First verify the base payload is valid
            try:
                cls.model_validate(base_payload)
            except Exception as exc:
                findings.append(
                    AuditFinding(
                        finding_id=f"BASE-DTO-ERR-{len(findings) + 1:03d}",
                        category="DTO_SETUP_FAILURE",
                        location=f"t2s.contracts.{dto_name}",
                        description=f"Base payload for {dto_name} failed validation: {exc}",
                        evidence=str(exc),
                        severity="CRITICAL",
                    )
                )
                continue

            # Now attempt injecting each forbidden gold field
            for field_name in self.FORBIDDEN_FIELDS:
                total_injections += 1
                injection_payload = dict(base_payload)
                injection_payload[field_name] = "FORBIDDEN_GOLD_TEST_VALUE"

                try:
                    cls.model_validate(injection_payload)
                    # If this succeeds, it's a LEAK / FAILURE
                    findings.append(
                        AuditFinding(
                            finding_id=f"GOLD-LEAK-{len(findings) + 1:03d}",
                            category="GOLD_ISOLATION_FAILURE",
                            location=f"{cls.__module__}.{dto_name}",
                            description=(
                                f"DTO {dto_name} accepted forbidden gold field '{field_name}'"
                            ),
                            evidence=f"Field '{field_name}' accepted without ValidationError",
                            severity="CRITICAL",
                        )
                    )
                except ValidationError:
                    successful_rejections += 1

        status = AuditStatus.PASS if len(findings) == 0 else AuditStatus.FAIL
        return AuditResult(
            check_name="gold_isolation_contract_audit",
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
            tool_or_function="GoldIsolationChecker.check_gold_isolation",
            scope="Production DTOs and models (extra='forbid')",
            checked_count=len(dto_factories),
            violation_count=len(findings),
            violations=findings,
            evidence_paths=[str(config["cls"].__module__) for config in dto_factories.values()],
            limitations=[
                "Tests Pydantic validation boundaries; does not inspect internal helper dicts."
            ],
            details={
                "dtos_tested": list(dto_factories.keys()),
                "total_injection_attempts": total_injections,
                "successful_rejections": successful_rejections,
                "forbidden_fields": self.FORBIDDEN_FIELDS,
            },
        )


def audit_gold_isolation() -> AuditResult:
    """Convenience top-level wrapper to audit gold isolation across production DTOs."""
    return GoldIsolationChecker().check_gold_isolation()
