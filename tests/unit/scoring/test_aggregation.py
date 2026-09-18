"""Replicate-aware aggregation: F in denominator, no pooling, confounding."""

from __future__ import annotations

import pytest

from t2s.evaluation.scoring.aggregation import (
    aggregate,
    assert_not_pooled,
    case_level_metrics,
    check_comparability,
    paired_case_comparison,
    replicate_level_metrics,
)
from t2s.evaluation.scoring.records import new_semantic_audit_record
from t2s.evaluation.scoring.taxonomy import Grade


def _rec(case_id: str, replicate_id: str, grade: Grade, strict: bool | None = None):
    return new_semantic_audit_record(
        case_id=case_id,
        replicate_id=replicate_id,
        classification=grade,
        rationale="test",
        reviewer_id_or_role="test",
        strict_ex=strict,
    )


def test_f_stays_in_denominator() -> None:
    records = [
        _rec("c1", "r1", Grade.A),
        _rec("c2", "r1", Grade.F),
        _rec("c3", "r1", Grade.D),
        _rec("c4", "r1", Grade.F),
    ]
    metrics = case_level_metrics(records)
    # Production semantic safe = (A+B)/Total => 1/4, F counted in denominator.
    assert metrics.production_semantic_safe.numerator == 1
    assert metrics.production_semantic_safe.denominator == 4
    assert metrics.unknown.numerator == 2
    assert metrics.unknown.denominator == 4
    # Audited coverage excludes F from numerator but not denominator.
    assert metrics.audited_coverage.numerator == 2
    assert metrics.audited_coverage.denominator == 4
    # Conditional safe = (A+B)/(A+B+C+D+E) => 1/2.
    assert metrics.conditional_safe.numerator == 1
    assert metrics.conditional_safe.denominator == 2


def test_all_required_metrics_present() -> None:
    records = [_rec("c1", "r1", g) for g in (Grade.A, Grade.B, Grade.C, Grade.D, Grade.E, Grade.F)]
    m = case_level_metrics(records).to_dict()["metrics"]
    for key in (
        "strict_ex",
        "audited_coverage",
        "production_semantic_safe",
        "conditional_safe",
        "ambiguity",
        "true_error",
        "lucky_match",
        "unknown",
    ):
        assert key in m
        assert "numerator" in m[key] and "denominator" in m[key]


def test_pooling_guard_raises_on_multi_replicate() -> None:
    records = [_rec("c1", "r1", Grade.A), _rec("c1", "r2", Grade.D)]
    with pytest.raises(ValueError, match="Refusing to pool"):
        assert_not_pooled(records)


def test_case_clustering_denominator_is_cases_not_replicates() -> None:
    # 2 cases x 3 replicates = 6 rows, but case-level denominator must be 2.
    records = []
    for case in ("c1", "c2"):
        for rep in ("r1", "r2", "r3"):
            records.append(_rec(case, rep, Grade.A))
    case_metrics = case_level_metrics(records)
    rep_metrics = replicate_level_metrics(records)
    assert case_metrics.total == 2
    assert rep_metrics.total == 6
    assert rep_metrics.warnings  # carries the non-independence warning


def test_dominant_grade_tiebreak_is_pessimistic() -> None:
    # One case: A, D (tie 1-1) -> dominant must be D (least optimistic).
    records = [_rec("c1", "r1", Grade.A), _rec("c1", "r2", Grade.D)]
    metrics = case_level_metrics(records)
    assert metrics.counts["D"] == 1
    assert metrics.counts["A"] == 0


def test_confounded_comparison_detected() -> None:
    base = {
        "dataset_cases": "d1",
        "split": "dev",
        "db_fixture": "f1",
        "model": "m1",
        "temperature": 0.0,
        "retry_policy": "none",
        "prompt_base": "p1",
        "grounding_base": "g1",
        "scorer_version": "s1",
        "execution_environment": "e1",
    }
    # Only prompt differs and prompt IS the treatment -> comparable.
    arm = {**base, "prompt_base": "p2"}
    ok = check_comparability(base, arm, treatment_vars=("prompt_base",))
    assert ok.status == "COMPARABLE"
    assert ok.causal_claim_allowed is True

    # Prompt AND model differ, only prompt declared -> confounded.
    arm2 = {**base, "prompt_base": "p2", "model": "m2"}
    conf = check_comparability(base, arm2, treatment_vars=("prompt_base",))
    assert conf.status == "CONFOUNDED"
    assert conf.causal_claim_allowed is False
    assert "model" in conf.unexpected_differences


def test_paired_case_comparison_is_case_level() -> None:
    arm_a = [_rec("c1", "r1", Grade.A), _rec("c2", "r1", Grade.D)]
    arm_b = [_rec("c1", "r1", Grade.D), _rec("c2", "r1", Grade.A)]
    cmp = paired_case_comparison(arm_a, arm_b)
    assert cmp.paired_cases == 2
    assert cmp.only_a_safe == 1
    assert cmp.only_b_safe == 1
    assert "McNemar" in cmp.note


def test_bootstrap_ci_deterministic_and_clustered() -> None:
    records = [_rec(f"c{i}", "r1", Grade.A) for i in range(10)]
    agg = aggregate(records)
    ci = agg.safe_rate_ci
    assert ci.point == 1.0
    assert ci.method == "case-cluster-bootstrap"
