from unittest.mock import MagicMock

from structlog.contextvars import bind_contextvars, clear_contextvars

from t2s.runtime.runtime_contracts import ValidatorMode, ValidatorRuntimeAction
from t2s.runtime.sql_risk_controller import SqlRiskController, SqlValidatorMetricsSink
from t2s.verification.sql_semantic_risk_validator import (
    SemanticViolation,
    ValidationInput,
    ValidationResult,
    ValidatorFamily,
    ValidatorRecommendedAction,
    ViolationConfidence,
    ViolationSeverity,
)


def _input(sql: str = "SELECT COUNT(*) FROM cards") -> ValidationInput:
    return ValidationInput(
        question="What percentage of cards have no content warning?",
        candidate_sql=sql,
    )


def test_disabled_mode_does_not_invoke_validator() -> None:
    validator = MagicMock()
    controller = SqlRiskController(validator=validator)

    outcome = controller.evaluate(_input(), ValidatorMode.DISABLED, run_id="run-1")

    validator.validate.assert_not_called()
    assert outcome.invoked is False
    assert outcome.effective_runtime_action == ValidatorRuntimeAction.ACCEPT
    assert outcome.run_id == "run-1"


def test_shadow_mode_records_divergence_without_changing_action() -> None:
    controller = SqlRiskController()

    outcome = controller.evaluate(_input(), ValidatorMode.SHADOW, run_id="run-1")

    assert outcome.invoked is True
    assert outcome.recommended_action == ValidatorRecommendedAction.REJECT_OR_ESCALATE.value
    assert outcome.effective_runtime_action == ValidatorRuntimeAction.ACCEPT
    assert outcome.shadow_divergence is True


def test_enforce_mode_blocks_high_confidence_reject() -> None:
    controller = SqlRiskController()

    outcome = controller.evaluate(_input(), ValidatorMode.ENFORCE, run_id="run-1")

    assert outcome.effective_runtime_action == ValidatorRuntimeAction.NEEDS_SEMANTIC_REVIEW


def test_enforce_mode_keeps_safe_candidate_unchanged() -> None:
    controller = SqlRiskController()

    outcome = controller.evaluate(
        ValidationInput(question="How many cards?", candidate_sql="SELECT COUNT(*) FROM cards"),
        ValidatorMode.ENFORCE,
    )

    assert outcome.violation_codes == []
    assert outcome.effective_runtime_action == ValidatorRuntimeAction.ACCEPT


def test_enforce_mode_does_not_block_medium_or_low_only() -> None:
    fake_validator = MagicMock(rule_config_hash="test-rules-v1")
    fake_validator.validate.return_value = ValidationResult(
        is_high_risk=False,
        violations=[
            SemanticViolation(
                code="MEDIUM_ONLY_TEST",
                validator=ValidatorFamily.PROJECTION_SHAPE,
                severity=ViolationSeverity.MEDIUM,
                confidence=ViolationConfidence.MEDIUM,
            )
        ],
        recommended_action=ValidatorRecommendedAction.REJECT_OR_ESCALATE,
    )
    controller = SqlRiskController(validator=fake_validator)

    outcome = controller.evaluate(_input("SELECT x FROM t"), ValidatorMode.ENFORCE)

    assert outcome.violation_codes == ["MEDIUM_ONLY_TEST"]
    assert outcome.effective_runtime_action == ValidatorRuntimeAction.ACCEPT


def test_validator_internal_error_fails_open_in_shadow() -> None:
    fake_validator = MagicMock(rule_config_hash="test-rules-v1")
    fake_validator.validate.side_effect = RuntimeError("boom")
    metrics = SqlValidatorMetricsSink()
    controller = SqlRiskController(validator=fake_validator, metrics_sink=metrics)

    outcome = controller.evaluate(_input(), ValidatorMode.SHADOW)

    assert outcome.error_message is not None
    assert outcome.effective_runtime_action == ValidatorRuntimeAction.ACCEPT
    assert metrics.snapshot.validator_error_total == 1


def test_validator_internal_error_needs_review_in_enforce() -> None:
    fake_validator = MagicMock(rule_config_hash="test-rules-v1")
    fake_validator.validate.side_effect = RuntimeError("boom")
    controller = SqlRiskController(validator=fake_validator)

    outcome = controller.evaluate(_input(), ValidatorMode.ENFORCE)

    assert outcome.error_message is not None
    assert outcome.effective_runtime_action == ValidatorRuntimeAction.NEEDS_SEMANTIC_REVIEW


def test_structured_logging_metrics_and_correlation_ids() -> None:
    clear_contextvars()
    bind_contextvars(request_id="req-1", run_id="run-1", trace_id="trace-1")
    metrics = SqlValidatorMetricsSink()
    controller = SqlRiskController(metrics_sink=metrics)
    controller.logger = MagicMock()

    outcome = controller.evaluate(_input(), ValidatorMode.SHADOW)

    assert outcome.request_id == "req-1"
    assert outcome.run_id == "run-1"
    assert outcome.trace_id == "trace-1"
    assert metrics.snapshot.validator_total == 1
    assert metrics.snapshot.validator_shadow_divergence_total == 1
    controller.logger.info.assert_any_call(
        "validator.started",
        mode="shadow",
        candidate_id=None,
        request_id="req-1",
        run_id="run-1",
        trace_id="trace-1",
    )
    clear_contextvars()


def test_repeated_execution_is_deterministic() -> None:
    controller = SqlRiskController()
    payload = _input()

    first = controller.evaluate(payload, ValidatorMode.SHADOW).model_dump(mode="json")
    second = controller.evaluate(payload, ValidatorMode.SHADOW).model_dump(mode="json")
    first["latency_ms"] = 0
    second["latency_ms"] = 0

    assert first == second
