"""Benchmark harness test comparing baseline vs adaptive orchestration paths."""

import pytest

from t2s.contracts import QueryRequest
from t2s.evaluation import OrchestrationEvaluationCollector, OrchestrationEvaluationResult
from t2s.grounding import GroundingBudget
from t2s.orchestration import EscalationBudget
from t2s.security import UserIdentity
from t2s.solver import SolverRequest
from tests.unit.orchestration.test_adaptive_orchestrator import (
    _build_blocking_unresolved_solver_response,
    _build_clean_solver_response,
    _build_customers_table,
    _build_orchestrator,
    _build_orders_table,
    _build_schema_reference_mismatch_response,
    _build_secret_table,
    _build_unresolved_table,
)


@pytest.mark.anyio
async def test_orchestration_benchmark_suite_execution() -> None:
    """Run full benchmark cases and evaluate baseline vs adaptive metrics."""
    collector = OrchestrationEvaluationCollector()

    # Case 1: Clean single-table query (No escalation expected)
    customers = _build_customers_table()
    orch1, _ = _build_orchestrator(
        catalog_tables=[customers],
        authorized_tables=[customers],
        solver_response=_build_clean_solver_response(),
    )
    res1 = await orch1.run(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List active customers"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="bench-case-1",
    )
    collector.add_result(res1, is_escalation_expected=False)

    # Case 2: Solver unresolved, recovered via expanded context (Escalation expected)
    orders = _build_orders_table()
    orch2, _ = _build_orchestrator(
        catalog_tables=[customers, orders],
        authorized_tables=[customers, orders],
        solver_response=_build_schema_reference_mismatch_response(),
        grounding_budget=GroundingBudget(max_hydrated_tables=1, max_total_columns=5),
        escalation_budget=EscalationBudget(max_escalations=1, grounding_table_delta=4),
    )
    res2 = await orch2.run(
        query_request=QueryRequest(question="Customer revenue"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="Customer revenue"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="bench-case-2",
    )
    collector.add_result(res2, is_escalation_expected=True)

    # Case 3: Same context guard stops regeneration (Escalation attempted, no retry)
    orch3, _ = _build_orchestrator(
        catalog_tables=[customers],
        authorized_tables=[customers],
        solver_response=_build_blocking_unresolved_solver_response(),
        grounding_budget=GroundingBudget(max_hydrated_tables=10, max_total_columns=50),
        escalation_budget=EscalationBudget(max_escalations=1),
    )
    res3 = await orch3.run(
        query_request=QueryRequest(question="List active customers"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List active customers"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="bench-case-3",
    )
    collector.add_result(res3, is_escalation_expected=True)

    # Case 4: Missing sql_identifier (Unresolved, no escalation expected)
    leads = _build_unresolved_table()
    orch4, _ = _build_orchestrator(
        catalog_tables=[leads],
        authorized_tables=[leads],
        solver_response=_build_clean_solver_response(),
    )
    res4 = await orch4.run(
        query_request=QueryRequest(question="List marketing leads"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="List marketing leads"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="bench-case-4",
    )
    collector.add_result(res4, is_escalation_expected=False)

    # Case 5: Unauthorized table isolation (Clean, no escalation expected)
    secret = _build_secret_table()
    orch5, _ = _build_orchestrator(
        catalog_tables=[customers, secret],
        authorized_tables=[customers],
        solver_response=_build_clean_solver_response(),
    )
    res5 = await orch5.run(
        query_request=QueryRequest(question="customers and payroll"),
        user_identity=UserIdentity(user_id="analyst"),
        solver_request_factory=lambda ctx, rid: SolverRequest(
            run_id=rid,
            query_request=QueryRequest(question="customers and payroll"),
            target_dialect="postgres",
            grounding_context=ctx,
        ),
        run_id="bench-case-5",
    )
    collector.add_result(res5, is_escalation_expected=False)

    metrics = collector.compute_metrics()

    assert isinstance(metrics, OrchestrationEvaluationResult)
    assert metrics.case_count == 5
    assert metrics.baseline_success_count == 2
    assert metrics.escalated_success_count == 1
    assert metrics.unresolved_count == 2
    assert metrics.failed_count == 0
    assert metrics.escalation_count == 2
    assert metrics.escalation_rate == 0.4
    assert metrics.success_after_escalation_rate == 0.5
    assert metrics.unnecessary_escalation_count == 0
    assert metrics.average_grounding_calls_per_case == 1.4
    assert metrics.average_solver_calls_per_case == 1.0
