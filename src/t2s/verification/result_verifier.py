"""Result-aware verifier evaluating query execution outputs against semantic expectations."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from t2s.database.query_execution_result import QueryExecutionResult
from t2s.semantics.semantic_plan import (
    ExpectedValueType,
    MetricAggregation,
    ResultExpectation,
    ResultShape,
    SemanticPlan,
)


class ResultVerificationDecision(StrEnum):
    """Decision emitted by the result-aware verifier."""

    ACCEPT = "ACCEPT"
    SUSPICIOUS = "SUSPICIOUS"
    AMBIGUOUS = "AMBIGUOUS"
    ABSTAIN = "ABSTAIN"


class ResultVerificationOutcome(BaseModel):
    """Structured outcome from result verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ResultVerificationDecision
    failure_code: str | None = None
    is_suspicious: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    recommended_probe: str | None = None


class ResultVerifier:
    """Evaluates executed query result shapes against expectations.

    Ensures that successful execution is not falsely equated with semantic accuracy
    (e.g., catching NULL aggregates, empty populations, or all-null rows), even
    when operating in decoupled mode without a semantic planner.
    """

    def verify_result(
        self,
        execution_result: QueryExecutionResult,
        plan: SemanticPlan | None = None,
        expectation: ResultExpectation | None = None,
    ) -> ResultVerificationOutcome:
        if expectation is None:
            if plan is not None:
                expectation = plan.expectation
            else:
                expectation = ResultExpectation(
                    expected_shape=ResultShape.UNKNOWN,
                    can_be_empty=False,
                )

        rows = execution_result.rows
        row_count = execution_result.row_count
        columns = execution_result.columns

        # 1. Zero rows check
        if row_count == 0:
            if not expectation.can_be_empty:
                return ResultVerificationOutcome(
                    decision=ResultVerificationDecision.SUSPICIOUS,
                    failure_code="SUSPICIOUS_EMPTY_RESULT",
                    is_suspicious=True,
                    details={
                        "row_count": 0,
                        "expected_shape": expectation.expected_shape.value,
                        "can_be_empty": expectation.can_be_empty,
                    },
                    recommended_probe="POPULATION_COUNT_PROBE",
                )
            return ResultVerificationOutcome(
                decision=ResultVerificationDecision.ACCEPT,
                details={"row_count": 0, "can_be_empty": True},
            )

        # 2. Scalar aggregate check
        is_scalar = expectation.expected_shape == ResultShape.SCALAR
        has_aggregate = (
            plan.aggregation != MetricAggregation.NONE
            if plan is not None
            else False
        )
        is_inferred_scalar = row_count == 1 and len(columns) == 1
        if is_scalar or has_aggregate or is_inferred_scalar:
            if row_count == 1 and columns:
                first_val = rows[0].get(columns[0])
                # Distinguish mathematical 0 / False from None
                if first_val is None:
                    aggregation_val = (
                        plan.aggregation.value
                        if plan is not None
                        else "UNKNOWN"
                    )
                    return ResultVerificationOutcome(
                        decision=ResultVerificationDecision.SUSPICIOUS,
                        failure_code="SUSPICIOUS_NULL_RESULT",
                        is_suspicious=True,
                        details={
                            "first_value": None,
                            "column": columns[0],
                            "aggregation": aggregation_val,
                        },
                        recommended_probe="METRIC_NON_NULL_PROBE",
                    )
                # If numeric expectation, check valid number
                if expectation.expected_value_type == ExpectedValueType.NUMERIC:
                    try:
                        float(first_val)
                    except (ValueError, TypeError):
                        return ResultVerificationOutcome(
                            decision=ResultVerificationDecision.SUSPICIOUS,
                            failure_code="SEMANTIC_VALUE_TYPE_MISMATCH",
                            is_suspicious=True,
                            details={"val": str(first_val), "expected": "NUMERIC"},
                        )

        # 3. All cells NULL check across returned rows
        all_null = True
        for row in rows:
            for col in columns:
                if row.get(col) is not None:
                    all_null = False
                    break
            if not all_null:
                break

        if all_null and row_count > 0:
            return ResultVerificationOutcome(
                decision=ResultVerificationDecision.SUSPICIOUS,
                failure_code="ALL_ROWS_NULL",
                is_suspicious=True,
                details={"row_count": row_count, "columns": columns},
                recommended_probe="METRIC_NON_NULL_PROBE",
            )

        # Result matches expectation
        return ResultVerificationOutcome(
            decision=ResultVerificationDecision.ACCEPT,
            is_suspicious=False,
            details={"row_count": row_count, "column_count": len(columns)},
        )
