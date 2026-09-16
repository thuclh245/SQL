from t2s.evaluation.verifier_evaluation import (
    VerifierCandidateRecord,
    build_confusion_matrix,
    evaluate_check_effectiveness,
    evaluate_counterfactual_policies,
    evaluate_policy_decisions,
)
from t2s.verification.contracts import (
    CheckStatus,
    SemanticCheckResult,
    VerificationDecision,
    VerificationResult,
)


def _make_candidate(
    cand_id: str, is_correct: bool, origin: str = "EXECUTED"
) -> VerifierCandidateRecord:
    return VerifierCandidateRecord(
        candidate_id=cand_id,
        source_run_id="run_1",
        case_id="case_1",
        db_id="db_1",
        question="Q?",
        evidence="E",
        candidate_sql="SELECT 1;",
        runtime_origin=origin,
        evaluator_correctness_label=is_correct,
    )


def _make_result(
    decision: VerificationDecision,
    failed_checks: list[str] | None = None,
    unknown_checks: list[str] | None = None,
) -> VerificationResult:
    pass_chk = SemanticCheckResult(status=CheckStatus.PASS, short_reason="OK")
    fail_chk = SemanticCheckResult(status=CheckStatus.FAIL, short_reason="Bad")
    unk_chk = SemanticCheckResult(status=CheckStatus.UNKNOWN, short_reason="Unk")

    f_list = failed_checks or []
    u_list = unknown_checks or []

    def get_chk(name: str) -> SemanticCheckResult:
        if name in f_list:
            return fail_chk
        if name in u_list:
            return unk_chk
        return pass_chk

    return VerificationResult(
        projection=get_chk("projection"),
        aggregation_and_grain=get_chk("aggregation_and_grain"),
        filters_and_values=get_chk("filters_and_values"),
        join_semantics=get_chk("join_semantics"),
        ordering_and_limit=get_chk("ordering_and_limit"),
        null_semantics=get_chk("null_semantics"),
        schema_reference=get_chk("schema_reference"),
        decision=decision,
        failed_checks=f_list,
        unknown_checks=u_list,
    )


def test_confusion_matrix_metrics() -> None:
    cands = [
        _make_candidate("c1", is_correct=True),
        _make_candidate("c2", is_correct=True),
        _make_candidate("c3", is_correct=False),
        _make_candidate("c4", is_correct=False),
        _make_candidate("c5", is_correct=False),
    ]
    results = [
        _make_result(VerificationDecision.ACCEPT),  # correct + accept
        _make_result(VerificationDecision.REJECT),  # correct + reject
        _make_result(VerificationDecision.ACCEPT),  # incorrect + accept (false accept!)
        _make_result(VerificationDecision.REJECT),  # incorrect + reject
        _make_result(VerificationDecision.ABSTAIN),  # incorrect + abstain
    ]

    cm = build_confusion_matrix(cands, results)
    assert cm.correct_accepted == 1
    assert cm.correct_rejected == 1
    assert cm.correct_abstained == 0
    assert cm.incorrect_accepted == 1
    assert cm.incorrect_rejected == 1
    assert cm.incorrect_abstained == 1

    assert cm.total_accepted == 2
    assert cm.accepted_precision == 0.5
    assert cm.selective_risk == 0.5
    assert cm.coverage == 2 / 5
    assert cm.false_accept_rate == 1 / 3
    assert cm.false_reject_rate == 1 / 2


def test_evaluate_policy_decisions() -> None:
    cands = [
        _make_candidate("c1", is_correct=True),
        _make_candidate("c2", is_correct=False),
    ]
    # Result has 0 fail, 1 unknown
    results = [
        _make_result(VerificationDecision.ABSTAIN, unknown_checks=["filters_and_values"]),
        _make_result(VerificationDecision.ABSTAIN, unknown_checks=["filters_and_values"]),
    ]

    # Under Policy A (0 unknowns allowed to accept): both abstain
    cm_a = evaluate_policy_decisions(cands, results, "Policy A")
    assert cm_a.total_accepted == 0
    assert cm_a.total_abstained == 2

    # Under Policy B (<=1 unknown allowed to accept): both accept!
    cm_b = evaluate_policy_decisions(cands, results, "Policy B")
    assert cm_b.total_accepted == 2
    assert cm_b.correct_accepted == 1
    assert cm_b.incorrect_accepted == 1


def test_evaluate_check_effectiveness() -> None:
    cands = [
        _make_candidate("c1", is_correct=False),
        _make_candidate("c2", is_correct=True),
    ]
    results = [
        _make_result(VerificationDecision.REJECT, failed_checks=["projection"]),
        _make_result(VerificationDecision.ACCEPT),
    ]
    eff = evaluate_check_effectiveness(cands, results)
    assert "projection" in eff["dimensions"]
    proj = eff["dimensions"]["projection"]
    assert proj["fail_count"] == 1
    assert proj["fail_when_incorrect"] == 1
    assert proj["fail_when_correct"] == 0
    assert proj["fail_precision"] == 1.0


def test_counterfactual_policies() -> None:
    cands = [
        _make_candidate("c1", is_correct=True, origin="EXECUTED"),
        _make_candidate("c2", is_correct=False, origin="EXECUTED"),
        _make_candidate("c3", is_correct=False, origin="REJECTED_BY_P5"),
    ]
    results = [
        _make_result(VerificationDecision.ACCEPT),
        _make_result(VerificationDecision.REJECT),
        _make_result(VerificationDecision.REJECT),
    ]
    cf = evaluate_counterfactual_policies(cands, results, total_benchmark_requests=3)
    # LLM verifier accepted only c1 (correct), rejected c2 and c3
    assert cf["llm_verifier"]["accepted_precision"] == 1.0
    assert cf["llm_verifier"]["selective_risk"] == 0.0
    assert cf["llm_verifier"]["ex"] == round(1 / 3, 4)
