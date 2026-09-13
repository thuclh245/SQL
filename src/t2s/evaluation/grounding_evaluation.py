from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import mean
from time import perf_counter
from typing import Literal

from t2s.contracts import GroundingContext, QueryRequest
from t2s.security import UserIdentity


@dataclass(frozen=True)
class GroundingBenchmarkCase:
    case_id: str
    question: str
    expected_table_fqns: frozenset[str]
    expected_column_fqns: frozenset[str] = field(default_factory=frozenset)
    locale: Literal["vi", "en", "auto"] = "auto"


@dataclass(frozen=True)
class GroundingEvaluationResult:
    case_count: int
    table_recall_at_k: float
    column_recall_at_k: float
    average_selected_tables: float
    average_selected_columns: float
    average_grounding_latency_ms: float
    false_negative_classifications: dict[str, int]


class GroundingEvaluator:
    def evaluate_grounding_cases(
        self,
        benchmark_cases: list[GroundingBenchmarkCase],
        user_identity: UserIdentity,
        build_grounding_context: Callable[[QueryRequest, UserIdentity], GroundingContext],
    ) -> GroundingEvaluationResult:
        table_recalls: list[float] = []
        column_recalls: list[float] = []
        selected_table_counts: list[int] = []
        selected_column_counts: list[int] = []
        latency_measurements_ms: list[float] = []
        false_negative_classifications: dict[str, int] = {}

        for benchmark_case in benchmark_cases:
            started_at = perf_counter()
            grounding_context = build_grounding_context(
                QueryRequest(
                    question=benchmark_case.question,
                    locale=benchmark_case.locale,
                ),
                user_identity,
            )
            latency_measurements_ms.append(round((perf_counter() - started_at) * 1000, 3))
            selected_table_fqns = {table_context.fqn for table_context in grounding_context.tables}
            selected_column_fqns = {
                f"{table_context.fqn}.{column_context.name}"
                for table_context in grounding_context.tables
                for column_context in table_context.columns
            }
            table_recalls.append(
                self._calculate_recall(benchmark_case.expected_table_fqns, selected_table_fqns)
            )
            column_recalls.append(
                self._calculate_recall(benchmark_case.expected_column_fqns, selected_column_fqns)
            )
            selected_table_counts.append(len(selected_table_fqns))
            selected_column_counts.append(len(selected_column_fqns))
            for classification in self._classify_false_negatives(
                benchmark_case,
                grounding_context,
                selected_table_fqns,
                selected_column_fqns,
            ):
                false_negative_classifications[classification] = (
                    false_negative_classifications.get(classification, 0) + 1
                )

        return GroundingEvaluationResult(
            case_count=len(benchmark_cases),
            table_recall_at_k=mean(table_recalls) if table_recalls else 0.0,
            column_recall_at_k=mean(column_recalls) if column_recalls else 0.0,
            average_selected_tables=mean(selected_table_counts) if selected_table_counts else 0.0,
            average_selected_columns=mean(selected_column_counts)
            if selected_column_counts
            else 0.0,
            average_grounding_latency_ms=mean(latency_measurements_ms)
            if latency_measurements_ms
            else 0.0,
            false_negative_classifications=false_negative_classifications,
        )

    def _calculate_recall(
        self,
        expected_values: frozenset[str],
        observed_values: set[str],
    ) -> float:
        if not expected_values:
            return 1.0
        return len(expected_values & observed_values) / len(expected_values)

    def _classify_false_negatives(
        self,
        benchmark_case: GroundingBenchmarkCase,
        grounding_context: GroundingContext,
        selected_table_fqns: set[str],
        selected_column_fqns: set[str],
    ) -> list[str]:
        classifications: list[str] = []
        if benchmark_case.expected_table_fqns - selected_table_fqns:
            classifications.append("table_retrieval_miss")
        if benchmark_case.expected_column_fqns - selected_column_fqns:
            classifications.append("column_retrieval_miss")
        if any(issue.code == "unresolved_sql_identifier" for issue in grounding_context.unresolved):
            classifications.append("identifier_unresolved")
        return classifications
