"""Evaluation harness for comparing baseline vs adaptive orchestration behavior."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from t2s.orchestration.escalation_contracts import OrchestrationOutcome, OrchestrationResult


class OrchestrationBenchmarkCase(BaseModel):
    """A single benchmark case for orchestration evaluation."""

    case_id: str
    question: str
    locale: Literal["vi", "en", "auto"] = "auto"
    expected_tables: list[str] = Field(default_factory=list)
    is_escalation_expected: bool = False


@dataclass(frozen=True)
class OrchestrationEvaluationResult:
    """Aggregated evaluation metrics for orchestration benchmark."""

    case_count: int
    baseline_success_count: int
    escalated_success_count: int
    unresolved_count: int
    failed_count: int
    escalation_count: int
    escalation_rate: float
    success_after_escalation_rate: float
    unnecessary_escalation_count: int
    average_solver_calls_per_case: float
    average_grounding_calls_per_case: float


@dataclass
class OrchestrationEvaluationCollector:
    """Collects orchestration results and computes evaluation metrics."""

    results: list[OrchestrationResult] = field(default_factory=list)
    expected_escalations: list[bool] = field(default_factory=list)

    def add_result(
        self,
        result: OrchestrationResult,
        is_escalation_expected: bool = False,
    ) -> None:
        self.results.append(result)
        self.expected_escalations.append(is_escalation_expected)

    def compute_metrics(self) -> OrchestrationEvaluationResult:
        if not self.results:
            return OrchestrationEvaluationResult(
                case_count=0,
                baseline_success_count=0,
                escalated_success_count=0,
                unresolved_count=0,
                failed_count=0,
                escalation_count=0,
                escalation_rate=0.0,
                success_after_escalation_rate=0.0,
                unnecessary_escalation_count=0,
                average_solver_calls_per_case=0.0,
                average_grounding_calls_per_case=0.0,
            )

        case_count = len(self.results)
        baseline_success_count = sum(
            1
            for result in self.results
            if result.outcome == OrchestrationOutcome.BASELINE_SUCCESS
        )
        escalated_success_count = sum(
            1
            for result in self.results
            if result.outcome == OrchestrationOutcome.ESCALATED_SUCCESS
        )
        unresolved_count = sum(
            1
            for result in self.results
            if result.outcome == OrchestrationOutcome.UNRESOLVED
        )
        failed_count = sum(
            1
            for result in self.results
            if result.outcome == OrchestrationOutcome.FAILED
        )

        escalation_count = sum(
            1
            for result in self.results
            if len(result.trace.escalation_records) > 0
        )
        escalation_rate = escalation_count / case_count

        escalated_cases_with_records = [
            result
            for result in self.results
            if len(result.trace.escalation_records) > 0
        ]
        success_after_escalation_rate = (
            escalated_success_count / len(escalated_cases_with_records)
            if escalated_cases_with_records
            else 0.0
        )

        unnecessary_escalation_count = sum(
            1
            for result, expected in zip(self.results, self.expected_escalations, strict=True)
            if len(result.trace.escalation_records) > 0 and not expected
        )

        total_solver_calls = sum(
            result.trace.total_solver_calls for result in self.results
        )
        total_grounding_calls = sum(
            result.trace.total_grounding_calls for result in self.results
        )

        return OrchestrationEvaluationResult(
            case_count=case_count,
            baseline_success_count=baseline_success_count,
            escalated_success_count=escalated_success_count,
            unresolved_count=unresolved_count,
            failed_count=failed_count,
            escalation_count=escalation_count,
            escalation_rate=round(escalation_rate, 4),
            success_after_escalation_rate=round(success_after_escalation_rate, 4),
            unnecessary_escalation_count=unnecessary_escalation_count,
            average_solver_calls_per_case=round(total_solver_calls / case_count, 4),
            average_grounding_calls_per_case=round(total_grounding_calls / case_count, 4),
        )
