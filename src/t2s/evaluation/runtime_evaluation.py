"""Evaluation harness for measuring end-to-end safe runtime behavior."""

from dataclasses import dataclass, field
from statistics import mean
from typing import Literal

from pydantic import BaseModel, Field

from t2s.runtime.runtime_contracts import RuntimeExecutionResult, RuntimeStatus


class RuntimeBenchmarkCase(BaseModel):
    """A benchmark case for evaluating end-to-end runtime behavior."""

    case_id: str
    question: str
    locale: Literal["vi", "en", "auto"] = "auto"
    expected_status: RuntimeStatus = RuntimeStatus.COMPLETED
    expected_tables: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class RuntimeEvaluationResult:
    """Aggregated evaluation metrics for safe runtime evaluation."""

    case_count: int
    completed_count: int
    unresolved_count: int
    generation_failed_count: int
    safety_rejected_count: int
    access_denied_count: int
    execution_failed_count: int
    timeout_count: int
    total_executor_calls: int
    average_runtime_latency_ms: float


@dataclass
class RuntimeEvaluationCollector:
    """Collects runtime execution results and computes aggregate metrics."""

    results: list[RuntimeExecutionResult] = field(default_factory=list)
    executor_call_counts: list[int] = field(default_factory=list)

    def add_result(
        self,
        result: RuntimeExecutionResult,
        executor_calls: int = 0,
    ) -> None:
        self.results.append(result)
        self.executor_call_counts.append(executor_calls)

    def compute_metrics(self) -> RuntimeEvaluationResult:
        if not self.results:
            return RuntimeEvaluationResult(
                case_count=0,
                completed_count=0,
                unresolved_count=0,
                generation_failed_count=0,
                safety_rejected_count=0,
                access_denied_count=0,
                execution_failed_count=0,
                timeout_count=0,
                total_executor_calls=0,
                average_runtime_latency_ms=0.0,
            )

        case_count = len(self.results)
        completed_count = sum(
            1 for result in self.results if result.status == RuntimeStatus.COMPLETED
        )
        unresolved_count = sum(
            1 for result in self.results if result.status == RuntimeStatus.UNRESOLVED
        )
        generation_failed_count = sum(
            1 for result in self.results if result.status == RuntimeStatus.GENERATION_FAILED
        )
        safety_rejected_count = sum(
            1 for result in self.results if result.status == RuntimeStatus.SAFETY_REJECTED
        )
        access_denied_count = sum(
            1 for result in self.results if result.status == RuntimeStatus.ACCESS_DENIED
        )
        execution_failed_count = sum(
            1 for result in self.results if result.status == RuntimeStatus.EXECUTION_FAILED
        )
        timeout_count = sum(
            1 for result in self.results if result.status == RuntimeStatus.TIMEOUT
        )

        total_executor_calls = sum(self.executor_call_counts)
        latencies = [result.total_latency_ms for result in self.results]
        average_latency = round(mean(latencies), 3) if latencies else 0.0

        return RuntimeEvaluationResult(
            case_count=case_count,
            completed_count=completed_count,
            unresolved_count=unresolved_count,
            generation_failed_count=generation_failed_count,
            safety_rejected_count=safety_rejected_count,
            access_denied_count=access_denied_count,
            execution_failed_count=execution_failed_count,
            timeout_count=timeout_count,
            total_executor_calls=total_executor_calls,
            average_runtime_latency_ms=average_latency,
        )
