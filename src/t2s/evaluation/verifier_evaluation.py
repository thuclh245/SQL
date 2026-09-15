from dataclasses import dataclass
from typing import Any

from t2s.verification.contracts import (
    SEMANTIC_CHECK_DIMENSIONS,
    CheckStatus,
    VerificationDecision,
    VerificationResult,
    VerifierCandidateRecord,
)


@dataclass
class ConfusionMatrix:
    correct_accepted: int = 0
    correct_rejected: int = 0
    correct_abstained: int = 0
    incorrect_accepted: int = 0
    incorrect_rejected: int = 0
    incorrect_abstained: int = 0

    @property
    def total_candidates(self) -> int:
        return (
            self.correct_accepted
            + self.correct_rejected
            + self.correct_abstained
            + self.incorrect_accepted
            + self.incorrect_rejected
            + self.incorrect_abstained
        )

    @property
    def total_correct(self) -> int:
        return self.correct_accepted + self.correct_rejected + self.correct_abstained

    @property
    def total_incorrect(self) -> int:
        return self.incorrect_accepted + self.incorrect_rejected + self.incorrect_abstained

    @property
    def total_accepted(self) -> int:
        return self.correct_accepted + self.incorrect_accepted

    @property
    def total_rejected(self) -> int:
        return self.correct_rejected + self.incorrect_rejected

    @property
    def total_abstained(self) -> int:
        return self.correct_abstained + self.incorrect_abstained

    @property
    def accepted_precision(self) -> float:
        return (self.correct_accepted / self.total_accepted) if self.total_accepted > 0 else 0.0

    @property
    def selective_risk(self) -> float:
        return (self.incorrect_accepted / self.total_accepted) if self.total_accepted > 0 else 0.0

    @property
    def coverage(self) -> float:
        return (self.total_accepted / self.total_candidates) if self.total_candidates > 0 else 0.0

    @property
    def false_accept_rate(self) -> float:
        return (self.incorrect_accepted / self.total_incorrect) if self.total_incorrect > 0 else 0.0

    @property
    def false_reject_rate(self) -> float:
        return (self.correct_rejected / self.total_correct) if self.total_correct > 0 else 0.0

    @property
    def abstain_rate(self) -> float:
        return (self.total_abstained / self.total_candidates) if self.total_candidates > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "correct_accepted": self.correct_accepted,
            "correct_rejected": self.correct_rejected,
            "correct_abstained": self.correct_abstained,
            "incorrect_accepted": self.incorrect_accepted,
            "incorrect_rejected": self.incorrect_rejected,
            "incorrect_abstained": self.incorrect_abstained,
            "total_candidates": self.total_candidates,
            "total_correct": self.total_correct,
            "total_incorrect": self.total_incorrect,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "total_abstained": self.total_abstained,
            "accepted_precision": round(self.accepted_precision, 4),
            "selective_risk": round(self.selective_risk, 4),
            "coverage": round(self.coverage, 4),
            "false_accept_rate": round(self.false_accept_rate, 4),
            "false_reject_rate": round(self.false_reject_rate, 4),
            "abstain_rate": round(self.abstain_rate, 4),
        }


def build_confusion_matrix(
    candidates: list[VerifierCandidateRecord],
    results: list[VerificationResult],
) -> ConfusionMatrix:
    matrix = ConfusionMatrix()
    for cand, res in zip(candidates, results, strict=True):
        is_correct = cand.evaluator_correctness_label
        decision = res.decision
        if is_correct:
            if decision == VerificationDecision.ACCEPT:
                matrix.correct_accepted += 1
            elif decision == VerificationDecision.REJECT:
                matrix.correct_rejected += 1
            else:
                matrix.correct_abstained += 1
        else:
            if decision == VerificationDecision.ACCEPT:
                matrix.incorrect_accepted += 1
            elif decision == VerificationDecision.REJECT:
                matrix.incorrect_rejected += 1
            else:
                matrix.incorrect_abstained += 1
    return matrix


def evaluate_policy_decisions(
    candidates: list[VerifierCandidateRecord],
    results: list[VerificationResult],
    policy_name: str,
) -> ConfusionMatrix:
    """Evaluates candidates under a parameterized decision policy.

    - 'Policy A': ACCEPT only if all 7 checks PASS, else if any FAIL -> REJECT, else ABSTAIN
    - 'Policy B': ACCEPT if no FAIL and <= 1 UNKNOWN, else if any FAIL -> REJECT, else ABSTAIN
    - 'Policy C': ACCEPT if no FAIL regardless of UNKNOWN count, else REJECT
    """
    matrix = ConfusionMatrix()
    for cand, res in zip(candidates, results, strict=True):
        failed_count = len(res.failed_checks)
        unknown_count = len(res.unknown_checks)

        if policy_name == "Policy A":
            if failed_count > 0:
                dec = VerificationDecision.REJECT
            elif unknown_count == 0:
                dec = VerificationDecision.ACCEPT
            else:
                dec = VerificationDecision.ABSTAIN
        elif policy_name == "Policy B":
            if failed_count > 0:
                dec = VerificationDecision.REJECT
            elif unknown_count <= 1:
                dec = VerificationDecision.ACCEPT
            else:
                dec = VerificationDecision.ABSTAIN
        elif policy_name == "Policy C":
            if failed_count > 0:
                dec = VerificationDecision.REJECT
            else:
                dec = VerificationDecision.ACCEPT
        else:
            dec = res.decision

        is_correct = cand.evaluator_correctness_label
        if is_correct:
            if dec == VerificationDecision.ACCEPT:
                matrix.correct_accepted += 1
            elif dec == VerificationDecision.REJECT:
                matrix.correct_rejected += 1
            else:
                matrix.correct_abstained += 1
        else:
            if dec == VerificationDecision.ACCEPT:
                matrix.incorrect_accepted += 1
            elif dec == VerificationDecision.REJECT:
                matrix.incorrect_rejected += 1
            else:
                matrix.incorrect_abstained += 1

    return matrix


def evaluate_check_effectiveness(
    candidates: list[VerifierCandidateRecord],
    results: list[VerificationResult],
) -> dict[str, Any]:
    """Measures predictive precision and false alarm rates for each verification dimension."""
    stats: dict[str, dict[str, Any]] = {}
    for dim in SEMANTIC_CHECK_DIMENSIONS:
        stats[dim] = {
            "fail_count": 0,
            "pass_count": 0,
            "unknown_count": 0,
            "fail_when_incorrect": 0,
            "fail_when_correct": 0,  # false alarms
        }

    for cand, res in zip(candidates, results, strict=True):
        is_incorrect = not cand.evaluator_correctness_label
        for dim in SEMANTIC_CHECK_DIMENSIONS:
            chk = getattr(res, dim)
            if chk.status == CheckStatus.FAIL:
                stats[dim]["fail_count"] += 1
                if is_incorrect:
                    stats[dim]["fail_when_incorrect"] += 1
                else:
                    stats[dim]["fail_when_correct"] += 1
            elif chk.status == CheckStatus.PASS:
                stats[dim]["pass_count"] += 1
            else:
                stats[dim]["unknown_count"] += 1

    effectiveness: dict[str, Any] = {}
    for dim, s in stats.items():
        total_fail = s["fail_count"]
        precision = (s["fail_when_incorrect"] / total_fail) if total_fail > 0 else 0.0
        false_alarm = (s["fail_when_correct"] / total_fail) if total_fail > 0 else 0.0
        effectiveness[dim] = {
            **s,
            "fail_precision": round(precision, 4),
            "false_alarm_rate": round(false_alarm, 4),
        }

    # Rank dimensions by fail_precision descending, then fail_when_incorrect descending
    ranked = sorted(
        effectiveness.items(),
        key=lambda kv: (kv[1]["fail_precision"], kv[1]["fail_when_incorrect"]),
        reverse=True,
    )
    return {
        "dimensions": effectiveness,
        "ranking": [k for k, _ in ranked],
    }


def evaluate_origin_analysis(
    candidates: list[VerifierCandidateRecord],
    results: list[VerificationResult],
) -> dict[str, Any]:
    """Compares verifier performance between EXECUTED and REJECTED_BY_P5 candidate origins."""
    executed_cands: list[VerifierCandidateRecord] = []
    executed_res: list[VerificationResult] = []
    rejected_cands: list[VerifierCandidateRecord] = []
    rejected_res: list[VerificationResult] = []

    for c, r in zip(candidates, results, strict=True):
        if c.runtime_origin == "EXECUTED":
            executed_cands.append(c)
            executed_res.append(r)
        else:
            rejected_cands.append(c)
            rejected_res.append(r)

    matrix_executed = build_confusion_matrix(executed_cands, executed_res)
    matrix_rejected = build_confusion_matrix(rejected_cands, rejected_res)

    return {
        "executed_origin": matrix_executed.to_dict(),
        "rejected_origin": matrix_rejected.to_dict(),
    }


def evaluate_counterfactual_policies(
    candidates: list[VerifierCandidateRecord],
    results: list[VerificationResult],
    total_benchmark_requests: int = 85,
) -> dict[str, Any]:
    """Computes comparison table metrics for baseline and verifier policies."""
    # Baseline 0: Accept All
    total_cands = len(candidates)
    total_corr = sum(1 for c in candidates if c.evaluator_correctness_label)
    accept_all_prec = round(total_corr / total_cands, 4) if total_cands > 0 else 0.0
    accept_all_risk = (
        round((total_cands - total_corr) / total_cands, 4) if total_cands > 0 else 0.0
    )
    accept_all = {
        "accepted_precision": accept_all_prec,
        "coverage": 1.0,
        "selective_risk": accept_all_risk,
        "ex": round(total_corr / total_benchmark_requests, 4),
        "incorrect_execution_rate": round(
            (total_cands - total_corr) / total_benchmark_requests, 4
        ),
    }

    # Baseline 1: Existing P5 Control
    p5_executed = [c for c in candidates if c.runtime_origin == "EXECUTED"]
    p5_corr = sum(1 for c in p5_executed if c.evaluator_correctness_label)
    p5_incorr = len(p5_executed) - p5_corr
    existing_p5 = {
        "accepted_precision": round(p5_corr / len(p5_executed), 4) if p5_executed else 0.0,
        "coverage": round(len(p5_executed) / total_cands, 4) if total_cands > 0 else 0.0,
        "selective_risk": round(p5_incorr / len(p5_executed), 4) if p5_executed else 0.0,
        "ex": round(p5_corr / total_benchmark_requests, 4),
        "incorrect_execution_rate": round(p5_incorr / total_benchmark_requests, 4),
    }

    # LLM Verifier Solo
    ver_matrix = build_confusion_matrix(candidates, results)
    llm_verifier = {
        "accepted_precision": round(ver_matrix.accepted_precision, 4),
        "coverage": round(ver_matrix.coverage, 4),
        "selective_risk": round(ver_matrix.selective_risk, 4),
        "ex": round(ver_matrix.correct_accepted / total_benchmark_requests, 4),
        "incorrect_execution_rate": round(
            ver_matrix.incorrect_accepted / total_benchmark_requests, 4
        ),
    }

    # P5 AND LLM Verifier (P5 executed AND verifier ACCEPT)
    p5_and_ver_corr = 0
    p5_and_ver_incorr = 0
    p5_and_ver_accepted = 0
    for c, r in zip(candidates, results, strict=True):
        if c.runtime_origin == "EXECUTED" and r.decision == VerificationDecision.ACCEPT:
            p5_and_ver_accepted += 1
            if c.evaluator_correctness_label:
                p5_and_ver_corr += 1
            else:
                p5_and_ver_incorr += 1

    p5_prec = (
        round(p5_and_ver_corr / p5_and_ver_accepted, 4) if p5_and_ver_accepted > 0 else 0.0
    )
    p5_cov = round(p5_and_ver_accepted / total_cands, 4) if total_cands > 0 else 0.0
    p5_risk = (
        round(p5_and_ver_incorr / p5_and_ver_accepted, 4) if p5_and_ver_accepted > 0 else 0.0
    )

    p5_and_verifier = {
        "accepted_precision": p5_prec,
        "coverage": p5_cov,
        "selective_risk": p5_risk,
        "ex": round(p5_and_ver_corr / total_benchmark_requests, 4),
        "incorrect_execution_rate": round(
            p5_and_ver_incorr / total_benchmark_requests, 4
        ),
    }

    return {
        "accept_all": accept_all,
        "existing_p5": existing_p5,
        "llm_verifier": llm_verifier,
        "p5_and_llm_verifier": p5_and_verifier,
    }


def evaluate_failure_slice_detection(
    candidates: list[VerifierCandidateRecord],
    results: list[VerificationResult],
) -> dict[str, Any]:
    """Cross-tabulates verifier detections against gold-derived semantic failure slices."""
    from t2s.evaluation.uncertainty_diagnostics import classify_sql_failure_slice

    slice_stats: dict[str, dict[str, Any]] = {}
    dimension_map = {
        "PROJECTION_ERROR": "projection",
        "AGGREGATION_OR_GRAIN_ERROR": "aggregation_and_grain",
        "FILTER_OR_VALUE_ERROR": "filters_and_values",
        "JOIN_SEMANTICS_ERROR": "join_semantics",
        "ORDER_OR_LIMIT_ERROR": "ordering_and_limit",
        "NULL_SEMANTICS_ERROR": "null_semantics",
    }

    for c, r in zip(candidates, results, strict=True):
        if c.evaluator_correctness_label:
            continue
        if not c.gold_sql:
            continue

        f_slice = classify_sql_failure_slice(c.candidate_sql, c.gold_sql).value
        if f_slice not in slice_stats:
            slice_stats[f_slice] = {
                "total_failures": 0,
                "overall_rejected": 0,
                "dimension_rejected": 0,
                "overall_abstained": 0,
                "false_accepted": 0,
            }

        slice_stats[f_slice]["total_failures"] += 1
        if r.decision == VerificationDecision.REJECT:
            slice_stats[f_slice]["overall_rejected"] += 1
        elif r.decision == VerificationDecision.ABSTAIN:
            slice_stats[f_slice]["overall_abstained"] += 1
        else:
            slice_stats[f_slice]["false_accepted"] += 1

        matched_dim = dimension_map.get(f_slice)
        if matched_dim:
            chk = getattr(r, matched_dim, None)
            if chk and chk.status == CheckStatus.FAIL:
                slice_stats[f_slice]["dimension_rejected"] += 1

    summary: dict[str, Any] = {}
    for sl, st in slice_stats.items():
        tot = st["total_failures"]
        summary[sl] = {
            **st,
            "overall_rejection_rate": round(st["overall_rejected"] / tot, 4) if tot > 0 else 0.0,
            "dimension_rejection_rate": round(
                st["dimension_rejected"] / tot, 4
            ) if tot > 0 else 0.0,
            "false_acceptance_rate": round(st["false_accepted"] / tot, 4) if tot > 0 else 0.0,
        }
    return summary
