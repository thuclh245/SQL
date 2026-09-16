"""Cheap, deterministic consistency checker comparing SemanticPlan against generated SQL AST."""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from t2s.semantics.semantic_plan import MetricAggregation, SemanticPlan


@dataclass(frozen=True)
class PlanConsistencyResult:
    """Consolidated outcome of plan vs SQL AST alignment check."""

    is_consistent: bool
    mismatches: tuple[str, ...] = field(default_factory=tuple)
    failure_code: str | None = None


class SemanticPlanConsistencyChecker:
    """Validates structural alignment between the planned semantics and the parsed SQL AST."""

    def check_alignment(
        self,
        plan: SemanticPlan,
        sql: str,
        dialect: str = "sqlite",
    ) -> PlanConsistencyResult:
        mismatches: list[str] = []

        try:
            ast = sqlglot.parse_one(sql, read=dialect)
        except Exception as exc:
            return PlanConsistencyResult(
                is_consistent=False,
                mismatches=(f"SQL failed to parse: {exc}",),
                failure_code="PLAN_SQL_PARSE_ERROR",
            )

        # 1. Aggregation alignment
        if plan.aggregation not in {MetricAggregation.NONE, MetricAggregation.UNKNOWN}:
            has_aggregate = bool(
                ast.find(exp.Count)
                or ast.find(exp.Sum)
                or ast.find(exp.Avg)
                or ast.find(exp.Min)
                or ast.find(exp.Max)
                or ast.find(exp.AggFunc)
            )
            if not has_aggregate:
                mismatches.append(
                    f"SemanticPlan requires {plan.aggregation.value} aggregation, "
                    "but SQL AST has no aggregate function."
                )

        # 2. Dimensions and GROUP BY alignment
        has_plan_agg = plan.aggregation not in {MetricAggregation.NONE, MetricAggregation.UNKNOWN}
        if plan.dimensions and has_plan_agg:
            has_group_by = bool(ast.find(exp.Group))
            if not has_group_by:
                mismatches.append(
                    f"SemanticPlan specifies dimensions {plan.dimensions} with aggregation, "
                    "but SQL AST lacks a GROUP BY clause."
                )

        # 3. Filter representation check
        if plan.filters:
            has_where_or_having = bool(ast.find(exp.Where) or ast.find(exp.Having))
            if not has_where_or_having:
                mismatches.append(
                    "SemanticPlan requires specific filters, but SQL AST contains "
                    "neither WHERE nor HAVING."
                )

        # 4. Relevant tables representation
        if plan.relevant_tables:
            ast_tables = {t.name.lower() for t in ast.find_all(exp.Table) if t.name}
            planned_tables = {t.lower().split(".")[-1] for t in plan.relevant_tables}
            # Check if any planned table appears in AST
            if not ast_tables.intersection(planned_tables):
                mismatches.append(
                    f"None of the planned relevant tables ({planned_tables}) "
                    f"appear in SQL AST ({ast_tables})."
                )

        if mismatches:
            return PlanConsistencyResult(
                is_consistent=False,
                mismatches=tuple(mismatches),
                failure_code="PLAN_SQL_MISMATCH",
            )

        return PlanConsistencyResult(
            is_consistent=True,
            mismatches=(),
            failure_code=None,
        )
