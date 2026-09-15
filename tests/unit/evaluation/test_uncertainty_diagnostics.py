"""Unit tests for Phase 7C uncertainty diagnostics and classification."""

from typing import Any

import pytest

from t2s.evaluation.uncertainty_diagnostics import (
    CaseUncertaintyCategory,
    classify_case_primary_uncertainty,
    extract_sql_structural_features,
    simulate_selective_release_for_replicate,
    wilson_score_interval,
)


def test_classify_case_pure_hard_blocker() -> None:
    notes = [
        "There is no telephone column in the authorized schema, so query cannot be formulated."
    ]
    cat = classify_case_primary_uncertainty(notes)
    assert cat == CaseUncertaintyCategory.HARD_BLOCKER_PRESENT


def test_classify_case_mixed_hard_and_soft() -> None:
    notes = [
        "Cannot be determined without a date column",
        "Assumed ordering by id DESC to break ties",
    ]
    cat = classify_case_primary_uncertainty(notes)
    assert cat == CaseUncertaintyCategory.MIXED_HARD_AND_SOFT


def test_classify_case_grounding_table_deficit_precedence() -> None:
    notes = ["Generic note without hard blocker"]
    cat = classify_case_primary_uncertainty(
        notes,
        has_grounding_table_deficit=True,
    )
    assert cat == CaseUncertaintyCategory.GROUNDING_TABLE_DEFICIT


def test_classify_case_relationship_evidence_deficit() -> None:
    notes: list[str] = []
    cat = classify_case_primary_uncertainty(
        notes,
        has_relationship_evidence_deficit=True,
    )
    assert cat == CaseUncertaintyCategory.RELATIONSHIP_EVIDENCE_DEFICIT


def test_classify_case_schema_reference_mismatch() -> None:
    notes: list[str] = []
    cat = classify_case_primary_uncertainty(
        notes,
        has_schema_reference_mismatch=True,
    )
    assert cat == CaseUncertaintyCategory.SCHEMA_REFERENCE_MISMATCH


def test_classify_case_single_soft_categories() -> None:
    # Tie break only
    assert (
        classify_case_primary_uncertainty(["Arbitrary top row using limit 1 to break ties"])
        == CaseUncertaintyCategory.TIE_BREAK_ONLY
    )

    # Soft assumption only
    assert (
        classify_case_primary_uncertainty(["I assumed that status = 'active' was intended"])
        == CaseUncertaintyCategory.SOFT_ASSUMPTION_ONLY
    )

    # Soft caveat only
    assert (
        classify_case_primary_uncertainty(["Null values in column amount are excluded"])
        == CaseUncertaintyCategory.SOFT_CAVEAT_ONLY
    )

    # Data semantic only
    assert (
        classify_case_primary_uncertainty(["Exact casing of country name 'USA' could differ"])
        == CaseUncertaintyCategory.DATA_SEMANTIC_UNCERTAINTY_ONLY
    )

    # Schema uncertainty only
    assert (
        classify_case_primary_uncertainty(
            ["Ambiguity regarding foreign key join between accounts and clients"]
        )
        == CaseUncertaintyCategory.SCHEMA_UNCERTAINTY_ONLY
    )


def test_classify_case_multiple_soft_types() -> None:
    notes = [
        "Null values in column amount are excluded",  # soft caveat
        "Arbitrary top row using limit 1 to break ties",  # tie break
    ]
    cat = classify_case_primary_uncertainty(notes)
    assert cat == CaseUncertaintyCategory.MULTIPLE_SOFT_TYPES


def test_classify_case_unknown() -> None:
    cat = classify_case_primary_uncertainty([])
    assert cat == CaseUncertaintyCategory.UNKNOWN

    cat2 = classify_case_primary_uncertainty(["Some completely unrelated freeform text"])
    assert cat2 == CaseUncertaintyCategory.UNKNOWN


def test_wilson_score_interval_bounds() -> None:
    # 0 total
    assert wilson_score_interval(0, 0) == (0.0, 0.0)

    # 10 / 10
    lower, upper = wilson_score_interval(10, 10, confidence=0.95)
    assert 0.70 < lower < 0.75
    assert upper == 1.0

    # 0 / 10
    lower, upper = wilson_score_interval(0, 10, confidence=0.95)
    assert lower == 0.0
    assert 0.25 < upper < 0.32

    # 5 / 10
    lower, upper = wilson_score_interval(5, 10, confidence=0.95)
    assert 0.20 < lower < 0.25
    assert 0.75 < upper < 0.80


def test_extract_sql_structural_features() -> None:
    sql = (
        "SELECT c.id, count(o.order_id) FROM customers c "
        "JOIN orders o ON c.id = o.cust_id WHERE o.amount > 100 "
        "GROUP BY c.id ORDER BY count(o.order_id) DESC LIMIT 5"
    )
    features = extract_sql_structural_features(sql)
    assert features["is_valid_ast"] is True
    assert features["table_count"] == 2
    assert features["is_multi_table"] is True
    assert features["join_count"] == 1
    assert features["has_aggregation"] is True
    assert features["has_group_by"] is True
    assert features["has_order_by"] is True
    assert features["has_limit"] is True


def test_simulate_selective_release_for_replicate() -> None:
    cases: list[dict[str, Any]] = [
        {"case_id": "c1", "runtime_status": "SUCCESS", "execution_correct": True},
        {"case_id": "c2", "runtime_status": "SUCCESS", "execution_correct": False},
        {"case_id": "c3", "runtime_status": "UNRESOLVED"},
        {"case_id": "c4", "runtime_status": "UNRESOLVED"},
    ]
    shadow_map = {
        "c3": {"status": "SHADOW_CORRECT"},
        "c4": {"status": "SHADOW_INCORRECT"},
    }
    case_category_map = {
        "c3": CaseUncertaintyCategory.TIE_BREAK_ONLY,
        "c4": CaseUncertaintyCategory.HARD_BLOCKER_PRESENT,
    }

    # Release TIE_BREAK_ONLY (c3: correct)
    res = simulate_selective_release_for_replicate(
        cases=cases,
        shadow_map=shadow_map,
        case_category_map=case_category_map,
        target_categories=[CaseUncertaintyCategory.TIE_BREAK_ONLY],
        total_population=4,
    )
    assert res.added_correct == 1
    assert res.added_incorrect == 0
    assert res.counterfactual_correct == 2
    assert res.counterfactual_executed == 3
    assert res.counterfactual_ex == 0.5
    assert res.counterfactual_executed_precision == pytest.approx(2 / 3, 0.001)
