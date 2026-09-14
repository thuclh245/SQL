"""Unit tests for the deterministic escalation policy."""

from t2s.contracts import (
    ColumnContext,
    GenerationTrace,
    GroundingContext,
    GroundingIssue,
    RelationshipEvidence,
    SqlCandidate,
    TableContext,
)
from t2s.orchestration.escalation_contracts import (
    EscalationAction,
    EscalationReason,
)
from t2s.orchestration.escalation_policy import EscalationPolicy


def _build_grounding_context(
    tables: list[TableContext] | None = None,
    unresolved: list[GroundingIssue] | None = None,
) -> GroundingContext:
    return GroundingContext(
        scope_id="test-scope",
        tables=tables or [],
        unresolved=unresolved or [],
    )


def _build_sql_candidate(
    sql: str = "SELECT 1",
    referenced_tables: list[str] | None = None,
    unresolved: list[str] | None = None,
) -> SqlCandidate:
    return SqlCandidate(
        sql=sql,
        dialect="postgres",
        referenced_tables=referenced_tables or [],
        referenced_columns=[],
        expected_columns=[],
        assumptions=[],
        unresolved=unresolved or [],
        generation_trace=GenerationTrace(
            run_id="test-run",
            model_name="test-model",
            prompt_version="v001",
        ),
    )


def _build_table_context(
    fqn: str = "service.db.schema.table",
    sql_identifier: str = "schema.table",
    columns: list[ColumnContext] | None = None,
    relationships: list[RelationshipEvidence] | None = None,
) -> TableContext:
    return TableContext(
        fqn=fqn,
        sql_identifier=sql_identifier,
        columns=columns
        or [ColumnContext(name="id", data_type="integer", is_primary_key=True)],
        relationships=relationships or [],
    )


# --- Test: No escalation when everything is clean ---


def test_no_escalation_when_context_and_candidate_are_clean() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[_build_table_context()],
    )
    candidate = _build_sql_candidate(
        referenced_tables=["schema.table"],
    )

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=candidate,
        budget_remaining=1,
    )

    assert decision.should_escalate is False


# --- Test: Unresolved SQL identifier causes STOP_UNRESOLVED ---


def test_unresolved_sql_identifier_causes_stop_not_retry() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        unresolved=[
            GroundingIssue(
                code="unresolved_sql_identifier",
                message="Table X has no executable SQL identifier.",
            )
        ],
    )

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=None,
        budget_remaining=1,
    )

    assert decision.should_escalate is False
    assert decision.reason == EscalationReason.UNRESOLVED_IDENTIFIER
    assert decision.action == EscalationAction.STOP_UNRESOLVED
    assert len(decision.evidence) == 1
    assert "unresolved_sql_identifier" in decision.evidence[0]


# --- Test: Recoverable grounding issue triggers escalation ---


def test_recoverable_grounding_issue_triggers_reground() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[_build_table_context()],
        unresolved=[
            GroundingIssue(
                code="insufficient_column_coverage",
                message="Too few columns matched for table X.",
            )
        ],
    )
    candidate = _build_sql_candidate()

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=candidate,
        budget_remaining=1,
    )

    assert decision.should_escalate is True
    assert decision.reason == EscalationReason.GROUNDING_INCOMPLETE
    assert decision.action == EscalationAction.REGROUND_WITH_EXPANDED_BUDGET


# --- Test: Solver unresolved items trigger escalation ---


def test_solver_unresolved_triggers_reground() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[_build_table_context()],
    )
    candidate = _build_sql_candidate(
        referenced_tables=["schema.table"],
        unresolved=["Could not determine join condition for table Y"],
    )

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=candidate,
        budget_remaining=1,
    )

    assert decision.should_escalate is True
    assert decision.reason == EscalationReason.SOLVER_UNRESOLVED
    assert decision.action == EscalationAction.REGROUND_WITH_EXPANDED_BUDGET
    assert "solver_unresolved" in decision.evidence[0]


# --- Test: Schema reference mismatch triggers escalation ---


def test_schema_reference_mismatch_triggers_reground() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[_build_table_context(sql_identifier="schema.table_a")],
    )
    candidate = _build_sql_candidate(
        referenced_tables=["schema.table_a", "schema.table_b"],
    )

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=candidate,
        budget_remaining=1,
    )

    assert decision.should_escalate is True
    assert decision.reason == EscalationReason.SCHEMA_REFERENCE_MISMATCH
    assert decision.action == EscalationAction.REGROUND_WITH_EXPANDED_BUDGET
    assert "schema.table_b" in decision.evidence[0]


# --- Test: Relationship ambiguity with multiple tables ---


def test_relationship_ambiguity_with_multiple_tables_and_zero_relationships() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[
            _build_table_context(fqn="service.db.schema.orders", sql_identifier="schema.orders"),
            _build_table_context(
                fqn="service.db.schema.customers", sql_identifier="schema.customers"
            ),
        ],
    )
    candidate = _build_sql_candidate(
        referenced_tables=["schema.orders", "schema.customers"],
    )

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=candidate,
        budget_remaining=1,
    )

    assert decision.should_escalate is True
    assert decision.reason == EscalationReason.RELATIONSHIP_AMBIGUITY
    assert decision.action == EscalationAction.REGROUND_WITH_EXPANDED_BUDGET


# --- Test: No ambiguity when relationships exist ---


def test_no_ambiguity_when_relationships_exist_between_multiple_tables() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[
            _build_table_context(
                fqn="service.db.schema.orders",
                sql_identifier="schema.orders",
                relationships=[
                    RelationshipEvidence(
                        from_table_fqn="service.db.schema.orders",
                        from_columns=["customer_id"],
                        to_table_fqn="service.db.schema.customers",
                        to_columns=["customer_id"],
                    )
                ],
            ),
            _build_table_context(
                fqn="service.db.schema.customers",
                sql_identifier="schema.customers",
            ),
        ],
    )
    candidate = _build_sql_candidate(
        referenced_tables=["schema.orders", "schema.customers"],
    )

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=candidate,
        budget_remaining=1,
    )

    assert decision.should_escalate is False


# --- Test: Budget exhausted prevents escalation ---


def test_budget_exhausted_prevents_escalation_regardless_of_evidence() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[_build_table_context()],
        unresolved=[
            GroundingIssue(
                code="insufficient_column_coverage",
                message="Recoverable issue",
            )
        ],
    )
    candidate = _build_sql_candidate()

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=candidate,
        budget_remaining=0,
    )

    assert decision.should_escalate is False


# --- Test: Solver failure (None candidate) without grounding issues ---


def test_solver_failure_without_grounding_issues_is_not_escalatable() -> None:
    policy = EscalationPolicy()
    context = _build_grounding_context(
        tables=[_build_table_context()],
    )

    decision = policy.assess_and_decide(
        grounding_context=context,
        sql_candidate=None,
        budget_remaining=1,
    )

    assert decision.should_escalate is False
    assert "solver_produced_no_candidate" in decision.evidence
