"""Uncertainty Category Predictive Analysis and Selective-Release Diagnostics.

Diagnostic, evaluator-only module for Phase 7C.
Evaluates case-level uncertainty predictability, Wilson confidence intervals,
stability across stochastic replicates, and counterfactual selective release.
Preserves all runtime security boundaries and performs no production modifications.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import sqlglot
from sqlglot import exp

from t2s.evaluation.shadow_evaluator import (
    ShadowEvaluationStatus,
    UnresolvedNoteCategory,
    classify_unresolved_note,
)


class CaseUncertaintyCategory(StrEnum):
    """Mutually exclusive case-level primary uncertainty categories."""

    HARD_BLOCKER_PRESENT = "HARD_BLOCKER_PRESENT"
    GROUNDING_TABLE_DEFICIT = "GROUNDING_TABLE_DEFICIT"
    RELATIONSHIP_EVIDENCE_DEFICIT = "RELATIONSHIP_EVIDENCE_DEFICIT"
    SCHEMA_REFERENCE_MISMATCH = "SCHEMA_REFERENCE_MISMATCH"
    SCHEMA_UNCERTAINTY_ONLY = "SCHEMA_UNCERTAINTY_ONLY"
    DATA_SEMANTIC_UNCERTAINTY_ONLY = "DATA_SEMANTIC_UNCERTAINTY_ONLY"
    TIE_BREAK_ONLY = "TIE_BREAK_ONLY"
    SOFT_ASSUMPTION_ONLY = "SOFT_ASSUMPTION_ONLY"
    SOFT_CAVEAT_ONLY = "SOFT_CAVEAT_ONLY"
    MULTIPLE_SOFT_TYPES = "MULTIPLE_SOFT_TYPES"
    MIXED_HARD_AND_SOFT = "MIXED_HARD_AND_SOFT"
    UNKNOWN = "UNKNOWN"


SOFT_NOTE_CATEGORIES: frozenset[UnresolvedNoteCategory] = frozenset(
    {
        UnresolvedNoteCategory.SOFT_ASSUMPTION,
        UnresolvedNoteCategory.SOFT_CAVEAT,
        UnresolvedNoteCategory.TIE_BREAK_NOTE,
        UnresolvedNoteCategory.DATA_SEMANTIC_UNCERTAINTY,
        UnresolvedNoteCategory.SCHEMA_UNCERTAINTY,
    }
)


def classify_case_primary_uncertainty(
    unresolved_notes: list[str],
    has_grounding_table_deficit: bool = False,
    has_relationship_evidence_deficit: bool = False,
    has_schema_reference_mismatch: bool = False,
) -> CaseUncertaintyCategory:
    """Classify a single unresolved case into exactly one primary category.

    Precedence Hierarchy:
    1. If HARD_BLOCKER note exists AND any soft note exists: MIXED_HARD_AND_SOFT
    2. If HARD_BLOCKER note exists: HARD_BLOCKER_PRESENT
    3. If required physical table is missing from grounding: GROUNDING_TABLE_DEFICIT
    4. If required relationship evidence is missing: RELATIONSHIP_EVIDENCE_DEFICIT
    5. If model generated table outside authorized schema: SCHEMA_REFERENCE_MISMATCH
    6. If exactly one soft category exists: corresponding *_ONLY category
    7. If multiple soft categories exist: MULTIPLE_SOFT_TYPES
    8. Otherwise: UNKNOWN
    """
    classified_notes = [classify_unresolved_note(note) for note in unresolved_notes]
    note_categories = set(classified_notes)

    has_hard_blocker = UnresolvedNoteCategory.HARD_BLOCKER in note_categories
    soft_categories_present = note_categories.intersection(SOFT_NOTE_CATEGORIES)

    # 1. Mixed Hard and Soft
    if has_hard_blocker and soft_categories_present:
        return CaseUncertaintyCategory.MIXED_HARD_AND_SOFT

    # 2. Pure Hard Blocker
    if has_hard_blocker:
        return CaseUncertaintyCategory.HARD_BLOCKER_PRESENT

    # 3. Grounding Table Deficit
    if has_grounding_table_deficit:
        return CaseUncertaintyCategory.GROUNDING_TABLE_DEFICIT

    # 4. Relationship Evidence Deficit
    if has_relationship_evidence_deficit:
        return CaseUncertaintyCategory.RELATIONSHIP_EVIDENCE_DEFICIT

    # 5. Schema Reference Mismatch
    if has_schema_reference_mismatch:
        return CaseUncertaintyCategory.SCHEMA_REFERENCE_MISMATCH

    # 6. Single Soft Category Only
    if len(soft_categories_present) == 1:
        single_cat = next(iter(soft_categories_present))
        if single_cat == UnresolvedNoteCategory.SCHEMA_UNCERTAINTY:
            return CaseUncertaintyCategory.SCHEMA_UNCERTAINTY_ONLY
        if single_cat == UnresolvedNoteCategory.DATA_SEMANTIC_UNCERTAINTY:
            return CaseUncertaintyCategory.DATA_SEMANTIC_UNCERTAINTY_ONLY
        if single_cat == UnresolvedNoteCategory.TIE_BREAK_NOTE:
            return CaseUncertaintyCategory.TIE_BREAK_ONLY
        if single_cat == UnresolvedNoteCategory.SOFT_ASSUMPTION:
            return CaseUncertaintyCategory.SOFT_ASSUMPTION_ONLY
        if single_cat == UnresolvedNoteCategory.SOFT_CAVEAT:
            return CaseUncertaintyCategory.SOFT_CAVEAT_ONLY

    # 7. Multiple Soft Categories
    if len(soft_categories_present) > 1:
        return CaseUncertaintyCategory.MULTIPLE_SOFT_TYPES

    return CaseUncertaintyCategory.UNKNOWN


def wilson_score_interval(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Returns:
        (ci_lower, ci_upper) clamped to [0.0, 1.0].
    """
    if total <= 0:
        return (0.0, 0.0)

    # Normal critical value for two-sided confidence
    z_values = {
        0.90: 1.644853,
        0.95: 1.959964,
        0.99: 2.575829,
    }
    z = z_values.get(confidence, 1.959964)

    p_hat = successes / total
    denominator = 1.0 + (z * z) / total
    center = (p_hat + (z * z) / (2.0 * total)) / denominator
    radicand = (p_hat * (1.0 - p_hat) / total) + ((z * z) / (4.0 * total * total))
    half_width = (z / denominator) * math.sqrt(radicand)

    ci_lower = max(0.0, center - half_width)
    ci_upper = min(1.0, center + half_width)
    return (round(ci_lower, 4), round(ci_upper, 4))


def extract_sql_structural_features(
    sql: str | None,
    dialect: str = "sqlite",
) -> dict[str, Any]:
    """Extract AST-derived structural features from candidate SQL."""
    if not sql or not sql.strip():
        return {
            "is_valid_ast": False,
            "table_count": 0,
            "is_multi_table": False,
            "join_count": 0,
            "has_aggregation": False,
            "has_group_by": False,
            "has_subquery": False,
            "has_cte": False,
            "has_order_by": False,
            "has_limit": False,
            "selected_column_count": 0,
        }

    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return {
            "is_valid_ast": False,
            "table_count": 0,
            "is_multi_table": False,
            "join_count": 0,
            "has_aggregation": False,
            "has_group_by": False,
            "has_subquery": False,
            "has_cte": False,
            "has_order_by": False,
            "has_limit": False,
            "selected_column_count": 0,
        }

    tables = {t.name.lower() for t in parsed.find_all(exp.Table)}
    joins = list(parsed.find_all(exp.Join))
    aggs = list(parsed.find_all(exp.AggFunc))
    group_bys = list(parsed.find_all(exp.Group))
    subqueries = [s for s in parsed.find_all(exp.Subquery) if s != parsed]
    ctes = list(parsed.find_all(exp.CTE))
    order_bys = list(parsed.find_all(exp.Order))
    limits = list(parsed.find_all(exp.Limit))

    select_exprs = parsed.expressions if isinstance(parsed, exp.Select) else []

    return {
        "is_valid_ast": True,
        "table_count": len(tables),
        "is_multi_table": len(tables) > 1,
        "join_count": len(joins),
        "has_aggregation": bool(aggs),
        "has_group_by": bool(group_bys),
        "has_subquery": bool(subqueries),
        "has_cte": bool(ctes),
        "has_order_by": bool(order_bys),
        "has_limit": bool(limits),
        "selected_column_count": len(select_exprs),
    }


class VerifierTargetSlice(StrEnum):
    """Categorization of semantic failure modes for verifier targeting."""

    PROJECTION_ERROR = "PROJECTION_ERROR"
    AGGREGATION_OR_GRAIN_ERROR = "AGGREGATION_OR_GRAIN_ERROR"
    FILTER_OR_VALUE_ERROR = "FILTER_OR_VALUE_ERROR"
    JOIN_SEMANTICS_ERROR = "JOIN_SEMANTICS_ERROR"
    ORDER_OR_LIMIT_ERROR = "ORDER_OR_LIMIT_ERROR"
    NULL_SEMANTICS_ERROR = "NULL_SEMANTICS_ERROR"
    OTHER_SEMANTIC_MISMATCH = "OTHER_SEMANTIC_MISMATCH"


def classify_sql_failure_slice(
    candidate_sql: str | None,
    gold_sql: str | None,
    details: str | None = None,
) -> VerifierTargetSlice:
    """Diagnose the probable primary semantic failure slice between candidate and gold SQL."""
    if not candidate_sql or not gold_sql:
        return VerifierTargetSlice.OTHER_SEMANTIC_MISMATCH

    cand_lower = candidate_sql.lower()
    gold_lower = gold_sql.lower()

    # 1. Aggregation / Grain differences
    cand_has_agg = any(fn in cand_lower for fn in ["count(", "sum(", "avg(", "min(", "max("])
    gold_has_agg = any(fn in gold_lower for fn in ["count(", "sum(", "avg(", "min(", "max("])
    if cand_has_agg != gold_has_agg:
        return VerifierTargetSlice.AGGREGATION_OR_GRAIN_ERROR
    if ("group by" in cand_lower) != ("group by" in gold_lower):
        return VerifierTargetSlice.AGGREGATION_OR_GRAIN_ERROR

    # 2. Order / Limit differences
    cand_has_limit = "limit" in cand_lower
    gold_has_limit = "limit" in gold_lower
    if cand_has_limit != gold_has_limit:
        return VerifierTargetSlice.ORDER_OR_LIMIT_ERROR

    # 3. Join semantics differences
    try:
        cand_parsed = sqlglot.parse_one(candidate_sql, read="sqlite")
        gold_parsed = sqlglot.parse_one(gold_sql, read="sqlite")
        cand_tbls = {t.name.lower() for t in cand_parsed.find_all(exp.Table)}
        gold_tbls = {t.name.lower() for t in gold_parsed.find_all(exp.Table)}
        if cand_tbls != gold_tbls:
            return VerifierTargetSlice.JOIN_SEMANTICS_ERROR
    except Exception:
        pass

    # 4. Projection / Column differences
    try:
        cand_parsed = sqlglot.parse_one(candidate_sql, read="sqlite")
        gold_parsed = sqlglot.parse_one(gold_sql, read="sqlite")
        cand_cols = len(cand_parsed.expressions) if isinstance(cand_parsed, exp.Select) else 0
        gold_cols = len(gold_parsed.expressions) if isinstance(gold_parsed, exp.Select) else 0
        if cand_cols != gold_cols and cand_cols > 0 and gold_cols > 0:
            return VerifierTargetSlice.PROJECTION_ERROR
    except Exception:
        pass

    # 5. Filter / Value differences
    if ("where" in cand_lower) != ("where" in gold_lower):
        return VerifierTargetSlice.FILTER_OR_VALUE_ERROR

    # 6. Null semantics
    if "is not null" in cand_lower or "is not null" in gold_lower:
        return VerifierTargetSlice.NULL_SEMANTICS_ERROR

    return VerifierTargetSlice.FILTER_OR_VALUE_ERROR


@dataclass
class SelectiveReleaseSimulationResult:
    """Counterfactual outcome of selectively releasing a specific candidate category."""

    policy_name: str
    target_categories: list[CaseUncertaintyCategory]
    baseline_executed: int
    baseline_correct: int
    baseline_incorrect: int
    added_correct: int
    added_incorrect: int
    added_errors: int
    counterfactual_executed: int
    counterfactual_correct: int
    counterfactual_incorrect: int
    counterfactual_ex: float
    counterfactual_executed_precision: float
    counterfactual_incorrect_execution_rate: float


def simulate_selective_release_for_replicate(
    cases: list[dict[str, Any]],
    shadow_map: dict[str, Any],
    case_category_map: dict[str, CaseUncertaintyCategory],
    target_categories: list[CaseUncertaintyCategory],
    total_population: int = 85,
) -> SelectiveReleaseSimulationResult:
    """Simulate releasing candidate SQL for specified categories on one replicate."""
    success_cases = [c for c in cases if c.get("runtime_status") == "SUCCESS"]
    baseline_correct = sum(1 for c in success_cases if c.get("execution_correct") is True)
    baseline_incorrect = sum(1 for c in success_cases if c.get("execution_correct") is False)
    baseline_executed = len(success_cases)

    added_correct = 0
    added_incorrect = 0
    added_errors = 0

    target_set = set(target_categories)
    for c in cases:
        if c.get("runtime_status") == "UNRESOLVED":
            cid = c["case_id"]
            cat = case_category_map.get(cid, CaseUncertaintyCategory.UNKNOWN)
            if cat in target_set:
                sh_res = shadow_map.get(cid)
                if sh_res:
                    status = sh_res.get("status")
                    if status == ShadowEvaluationStatus.SHADOW_CORRECT.value:
                        added_correct += 1
                    elif status == ShadowEvaluationStatus.SHADOW_INCORRECT.value:
                        added_incorrect += 1
                    else:
                        added_errors += 1

    cf_executed = baseline_executed + added_correct + added_incorrect + added_errors
    cf_correct = baseline_correct + added_correct
    cf_incorrect = baseline_incorrect + added_incorrect + added_errors

    cf_ex = cf_correct / total_population if total_population > 0 else 0.0
    cf_precision = cf_correct / cf_executed if cf_executed > 0 else 0.0
    cf_incorrect_rate = cf_incorrect / total_population if total_population > 0 else 0.0

    return SelectiveReleaseSimulationResult(
        policy_name="+".join(c.value for c in target_categories),
        target_categories=target_categories,
        baseline_executed=baseline_executed,
        baseline_correct=baseline_correct,
        baseline_incorrect=baseline_incorrect,
        added_correct=added_correct,
        added_incorrect=added_incorrect,
        added_errors=added_errors,
        counterfactual_executed=cf_executed,
        counterfactual_correct=cf_correct,
        counterfactual_incorrect=cf_incorrect,
        counterfactual_ex=round(cf_ex, 4),
        counterfactual_executed_precision=round(cf_precision, 4),
        counterfactual_incorrect_execution_rate=round(cf_incorrect_rate, 4),
    )
