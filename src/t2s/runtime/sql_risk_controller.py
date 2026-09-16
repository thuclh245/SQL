"""Runtime controller for deterministic SQL semantic risk validation."""

from __future__ import annotations

import time

import structlog
from pydantic import BaseModel
from structlog.contextvars import get_contextvars

from t2s.runtime.runtime_contracts import (
    ValidatorMode,
    ValidatorRuntimeAction,
    ValidatorRuntimeOutcome,
)
from t2s.verification.sql_semantic_risk_validator import (
    SqlSemanticRiskValidator,
    ValidationInput,
    ValidatorRecommendedAction,
    ViolationConfidence,
)


class SqlValidatorMetricsSnapshot(BaseModel):
    """In-memory counters for risk validator executions."""

    validator_total: int = 0
    validator_violation_total: int = 0
    validator_high_risk_total: int = 0
    validator_shadow_divergence_total: int = 0
    validator_blocked_enforce_total: int = 0
    validator_error_total: int = 0


class SqlValidatorMetricsSink:
    """Lightweight in-memory sink for validator telemetry."""

    def __init__(self) -> None:
        self.snapshot = SqlValidatorMetricsSnapshot()

    def record(
        self,
        outcome: ValidatorRuntimeOutcome,
        existing_action: ValidatorRuntimeAction,
    ) -> None:
        if not outcome.invoked:
            return
        self.snapshot.validator_total += 1
        if outcome.error_message:
            self.snapshot.validator_error_total += 1
        if outcome.violation_codes:
            self.snapshot.validator_violation_total += 1
        if outcome.is_high_risk:
            self.snapshot.validator_high_risk_total += 1
        if outcome.shadow_divergence:
            self.snapshot.validator_shadow_divergence_total += 1
        if (
            outcome.mode == ValidatorMode.ENFORCE
            and outcome.effective_runtime_action != existing_action
        ):
            self.snapshot.validator_blocked_enforce_total += 1


class SqlRiskController:
    """Runs deterministic semantic risk validation and maps detection into runtime policy."""

    def __init__(
        self,
        validator: SqlSemanticRiskValidator | None = None,
        metrics_sink: SqlValidatorMetricsSink | None = None,
    ) -> None:
        self.validator = validator or SqlSemanticRiskValidator()
        self.metrics_sink = metrics_sink or SqlValidatorMetricsSink()
        self.logger = structlog.get_logger("t2s.runtime.sql_risk_controller")

    def evaluate(
        self,
        validation_input: ValidationInput,
        mode: ValidatorMode,
        existing_runtime_action: ValidatorRuntimeAction = ValidatorRuntimeAction.ACCEPT,
        candidate_id: str | None = None,
        run_id: str | None = None,
    ) -> ValidatorRuntimeOutcome:
        context_vars = get_contextvars()
        request_id = context_vars.get("request_id")
        resolved_run_id = run_id or context_vars.get("run_id")
        trace_id = context_vars.get("trace_id")

        if mode == ValidatorMode.DISABLED:
            return ValidatorRuntimeOutcome(
                invoked=False,
                mode=mode,
                effective_runtime_action=existing_runtime_action,
                request_id=request_id,
                run_id=resolved_run_id,
                trace_id=trace_id,
            )

        start_time = time.perf_counter()
        self.logger.info(
            "validator.started",
            mode=mode.value,
            candidate_id=candidate_id,
            request_id=request_id,
            run_id=resolved_run_id,
            trace_id=trace_id,
        )

        try:
            result = self.validator.validate(validation_input)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            has_high_confidence_violation = any(
                violation.confidence == ViolationConfidence.HIGH for violation in result.violations
            )
            validator_action = result.recommended_action.value

            divergence = (
                mode == ValidatorMode.SHADOW
                and validator_action != ValidatorRecommendedAction.ACCEPT.value
                and existing_runtime_action == ValidatorRuntimeAction.ACCEPT
            )

            effective_action = self._determine_runtime_action(
                mode=mode,
                validator_action=result.recommended_action,
                has_high_confidence_violation=has_high_confidence_violation,
                existing_runtime_action=existing_runtime_action,
            )

            outcome = ValidatorRuntimeOutcome(
                invoked=True,
                mode=mode,
                validator_version="v1-clean",
                rule_config_hash=self.validator.rule_config_hash,
                candidate_hash=candidate_id,
                request_id=request_id,
                run_id=resolved_run_id,
                trace_id=trace_id,
                latency_ms=latency_ms,
                is_high_risk=result.is_high_risk,
                violation_codes=[v.code for v in result.violations],
                violation_families=[v.validator.value for v in result.violations],
                violation_count=len(result.violations),
                recommended_action=validator_action,
                effective_runtime_action=effective_action,
                shadow_divergence=divergence,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            self.logger.error(
                "validator.failed",
                error=str(exc),
                request_id=request_id,
                run_id=resolved_run_id,
                trace_id=trace_id,
            )
            effective_action = (
                existing_runtime_action
                if mode == ValidatorMode.SHADOW
                else ValidatorRuntimeAction.NEEDS_SEMANTIC_REVIEW
            )
            outcome = ValidatorRuntimeOutcome(
                invoked=True,
                mode=mode,
                validator_version="v1-clean",
                rule_config_hash=self.validator.rule_config_hash,
                candidate_hash=candidate_id,
                request_id=request_id,
                run_id=resolved_run_id,
                trace_id=trace_id,
                latency_ms=latency_ms,
                error_message=str(exc),
                effective_runtime_action=effective_action,
                shadow_divergence=False,
            )

        self.logger.info(
            "validator.completed",
            mode=mode.value,
            latency_ms=outcome.latency_ms,
            effective_action=outcome.effective_runtime_action.value,
            shadow_divergence=outcome.shadow_divergence,
            request_id=request_id,
            run_id=resolved_run_id,
            trace_id=trace_id,
        )
        self.metrics_sink.record(outcome, existing_runtime_action)
        return outcome

    @staticmethod
    def _determine_runtime_action(
        mode: ValidatorMode,
        validator_action: ValidatorRecommendedAction,
        has_high_confidence_violation: bool,
        existing_runtime_action: ValidatorRuntimeAction,
    ) -> ValidatorRuntimeAction:
        if mode == ValidatorMode.SHADOW:
            return existing_runtime_action

        if (
            mode == ValidatorMode.ENFORCE
            and validator_action == ValidatorRecommendedAction.REJECT_OR_ESCALATE
            and has_high_confidence_violation
        ):
            return ValidatorRuntimeAction.NEEDS_SEMANTIC_REVIEW

        return existing_runtime_action
