"""Unit tests for the orchestration evaluation collector and metrics."""

from t2s.contracts import GroundingContext
from t2s.evaluation.orchestration_evaluation import (
    OrchestrationEvaluationCollector,
    OrchestrationEvaluationResult,
)
from t2s.orchestration.escalation_contracts import (
    EscalationAction,
    EscalationReason,
    EscalationRecord,
    OrchestrationOutcome,
    OrchestrationResult,
    OrchestrationTrace,
)


def _make_dummy_result(
    outcome: OrchestrationOutcome,
    total_grounding_calls: int = 1,
    total_solver_calls: int = 1,
    has_escalation: bool = False,
) -> OrchestrationResult:
    records = []
    if has_escalation:
        records.append(
            EscalationRecord(
                attempt=1,
                reason=EscalationReason.SOLVER_UNRESOLVED,
                action=EscalationAction.REGROUND_WITH_EXPANDED_BUDGET,
                evidence=["dummy evidence"],
                outcome="solver_succeeded"
                if outcome == OrchestrationOutcome.ESCALATED_SUCCESS
                else "context_unchanged",
            )
        )
    return OrchestrationResult(
        outcome=outcome,
        sql_candidate=None,
        grounding_context=GroundingContext(scope_id="test", tables=[]),
        trace=OrchestrationTrace(
            run_id="run-test",
            outcome=outcome,
            total_grounding_calls=total_grounding_calls,
            total_solver_calls=total_solver_calls,
            escalation_records=records,
        ),
    )


def test_empty_collector_returns_zero_metrics() -> None:
    collector = OrchestrationEvaluationCollector()
    metrics = collector.compute_metrics()
    assert isinstance(metrics, OrchestrationEvaluationResult)
    assert metrics.case_count == 0
    assert metrics.escalation_rate == 0.0


def test_collector_computes_accurate_rates() -> None:
    collector = OrchestrationEvaluationCollector()

    # Case 1: Baseline success (no escalation, not expected)
    collector.add_result(
        _make_dummy_result(OrchestrationOutcome.BASELINE_SUCCESS, 1, 1, has_escalation=False),
        is_escalation_expected=False,
    )
    # Case 2: Escalated success (escalated, expected)
    collector.add_result(
        _make_dummy_result(OrchestrationOutcome.ESCALATED_SUCCESS, 2, 2, has_escalation=True),
        is_escalation_expected=True,
    )
    # Case 3: Unresolved after escalation (escalated, not expected -> unnecessary)
    collector.add_result(
        _make_dummy_result(OrchestrationOutcome.UNRESOLVED, 2, 1, has_escalation=True),
        is_escalation_expected=False,
    )
    # Case 4: Unresolved directly (no escalation, not expected)
    collector.add_result(
        _make_dummy_result(OrchestrationOutcome.UNRESOLVED, 1, 0, has_escalation=False),
        is_escalation_expected=False,
    )

    metrics = collector.compute_metrics()
    assert metrics.case_count == 4
    assert metrics.baseline_success_count == 1
    assert metrics.escalated_success_count == 1
    assert metrics.unresolved_count == 2
    assert metrics.failed_count == 0
    assert metrics.escalation_count == 2
    assert metrics.escalation_rate == 0.5
    assert metrics.success_after_escalation_rate == 0.5
    assert metrics.unnecessary_escalation_count == 1
    assert metrics.average_grounding_calls_per_case == 1.5
    assert metrics.average_solver_calls_per_case == 1.0
