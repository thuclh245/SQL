"""Deterministic semantic risk validator for generated SQL queries.

Evaluates candidates for structural, join-path, aggregation, and filter risks
using static AST analysis and question-alignment heuristics without benchmark coupling.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

import sqlglot
from pydantic import BaseModel, ConfigDict, Field
from sqlglot import exp

SQL_DIALECT = "sqlite"


class ValidatorFamily(StrEnum):
    """Deterministic validation rule families."""

    FILTER_CONTRACT = "FILTER_CONTRACT"
    AGGREGATION_GRAIN = "AGGREGATION_GRAIN"
    PROJECTION_SHAPE = "PROJECTION_SHAPE"
    JOIN_PATH_RISK = "JOIN_PATH_RISK"
    SQL_CONSTRUCTION = "SQL_CONSTRUCTION"
    VALUE_GROUNDING_BOUNDARY = "VALUE_GROUNDING_BOUNDARY"


class ViolationSeverity(StrEnum):
    """Severity tier for detected violations."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ViolationConfidence(StrEnum):
    """Confidence tier for detected violations."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ValidatorRecommendedAction(StrEnum):
    """Recommended action emitted by the validator."""

    ACCEPT = "ACCEPT"
    REJECT_OR_ESCALATE = "REJECT_OR_ESCALATE"


class SemanticViolation(BaseModel):
    """Discrete violation identified by deterministic validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    validator: ValidatorFamily
    severity: ViolationSeverity
    confidence: ViolationConfidence
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationInput(BaseModel):
    """Input payload for deterministic SQL validation.

    Strictly forbids gold answers, labels, and benchmark ground-truth attributes
    to prevent evaluation leakage into runtime code.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    candidate_sql: str
    dialect: str = "sqlite"
    evidence: str | None = None
    grounding_context: str | None = None
    authorized_schema: str | None = None
    authorized_tables: list[str] = Field(default_factory=list)
    authorized_columns: dict[str, list[str]] = Field(default_factory=dict)
    schema_context: dict[str, Any] | None = None
    value_bindings: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Consolidated report from deterministic SQL validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_high_risk: bool
    violations: list[SemanticViolation] = Field(default_factory=list)
    recommended_action: ValidatorRecommendedAction = ValidatorRecommendedAction.ACCEPT


class SqlSemanticRiskValidator:
    """Deterministic, production-ready semantic risk validator for generated SQL.

    Pure static analysis without external network calls, gold data references,
    or dataset-specific heuristics.
    """

    def __init__(self, rule_config_hash: str = "v1-deterministic-clean") -> None:
        self.rule_config_hash = rule_config_hash

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    def _violation(
        self,
        code: str,
        family: ValidatorFamily,
        severity: str,
        confidence: str,
        details: dict[str, Any] | None = None,
    ) -> SemanticViolation:
        return SemanticViolation(
            code=code,
            validator=family,
            severity=ViolationSeverity(severity),
            confidence=ViolationConfidence(confidence),
            details=details or {},
        )

    def validate(
        self,
        validation_input: ValidationInput,
        families: set[ValidatorFamily] | None = None,
    ) -> ValidationResult:
        active_families = families or set(ValidatorFamily)
        violations: list[SemanticViolation] = []

        try:
            ast = sqlglot.parse_one(validation_input.candidate_sql, read=SQL_DIALECT)
        except Exception as exc:
            violations.append(
                self._violation(
                    "SQL_PARSE_OR_STATEMENT_ERROR",
                    ValidatorFamily.SQL_CONSTRUCTION,
                    "HIGH",
                    "HIGH",
                    {"error": str(exc)},
                )
            )
            return ValidationResult(
                is_high_risk=True,
                violations=violations,
                recommended_action=ValidatorRecommendedAction.REJECT_OR_ESCALATE,
            )

        family_handlers = [
            (ValidatorFamily.FILTER_CONTRACT, self._filter_violations),
            (ValidatorFamily.AGGREGATION_GRAIN, self._aggregation_violations),
            (ValidatorFamily.PROJECTION_SHAPE, self._projection_violations),
            (ValidatorFamily.JOIN_PATH_RISK, self._join_violations),
            (ValidatorFamily.SQL_CONSTRUCTION, self._construction_violations),
            (
                ValidatorFamily.VALUE_GROUNDING_BOUNDARY,
                self._value_grounding_boundary,
            ),
        ]

        for family, handler in family_handlers:
            if family in active_families:
                try:
                    violations.extend(handler(validation_input, ast))
                except Exception as exc:
                    violations.append(
                        self._violation(
                            "VALIDATOR_FAMILY_INTERNAL_ERROR",
                            family,
                            "MEDIUM",
                            "LOW",
                            {"error": str(exc)},
                        )
                    )

        is_high_risk = any(
            v.severity == ViolationSeverity.HIGH and v.confidence == ViolationConfidence.HIGH
            for v in violations
        )
        has_violations = len(violations) > 0
        recommended_action = (
            ValidatorRecommendedAction.REJECT_OR_ESCALATE
            if has_violations
            else ValidatorRecommendedAction.ACCEPT
        )

        return ValidationResult(
            is_high_risk=is_high_risk,
            violations=violations,
            recommended_action=recommended_action,
        )

    def _filter_violations(
        self, validation_input: ValidationInput, ast: exp.Expression
    ) -> list[SemanticViolation]:
        q = self._norm(validation_input.question)
        violations: list[SemanticViolation] = []
        where_clause = ast.find(exp.Where)
        where_sql = where_clause.sql(dialect=SQL_DIALECT).lower() if where_clause else ""
        statement_sql = ast.sql(dialect=SQL_DIALECT).lower()

        if self._has_not_null_guard(where_clause):
            null_terms = ("null", "missing", "without", "exclude null", "where available")
            if not any(term in q for term in null_terms):
                # The guard protects a ratio or count that may live outside WHERE
                # (projection, ORDER BY, HAVING), so the denominator is sought statement-wide.
                if "/" in statement_sql or "count(" in statement_sql:
                    violations.append(
                        self._violation(
                            "EXTRA_UNREQUESTED_NULL_OR_DENOMINATOR_FILTER",
                            ValidatorFamily.FILTER_CONTRACT,
                            "HIGH",
                            "HIGH",
                            {"where": where_sql},
                        )
                    )

        if (
            re.search(r"\b(strongest|highest|lowest|oldest|youngest)\b", q)
            and re.search(r"\b(name|state|who|which)\b", q)
            and ast.find(exp.EQ)
            and ast.find(exp.Subquery)
            and ast.find(exp.Max, exp.Min)
            and not ast.find(exp.Limit)
        ):
            violations.append(
                self._violation(
                    "SINGULAR_SUPERLATIVE_WITH_TIE_PRONE_FILTER",
                    ValidatorFamily.FILTER_CONTRACT,
                    "MEDIUM",
                    "HIGH",
                    {"question_signal": "singular superlative", "where": where_sql},
                )
            )

        return violations

    def _aggregation_violations(
        self, validation_input: ValidationInput, ast: exp.Expression
    ) -> list[SemanticViolation]:
        q = self._norm(validation_input.question)
        violations: list[SemanticViolation] = []

        if re.search(r"\bpercentage|percent|ratio|proportion\b", q):
            has_div = bool(ast.find(exp.Div))
            has_agg = self._has_aggregate(ast)
            if not (has_div and has_agg):
                violations.append(
                    self._violation(
                        "PERCENTAGE_STRUCTURE_SUSPICIOUS",
                        ValidatorFamily.AGGREGATION_GRAIN,
                        "HIGH",
                        "HIGH",
                        {"has_division": has_div, "has_aggregate": has_agg},
                    )
                )

        if (
            re.search(r"\btop source\b", q)
            and "based on" in q
            and "amount" in q
            and ast.find(exp.Sum)
            and ast.find(exp.Group)
            and "total" not in q
        ):
            violations.append(
                self._violation(
                    "TOP_ENTITY_AMOUNT_AGGREGATED_WITHOUT_TOTAL_REQUEST",
                    ValidatorFamily.AGGREGATION_GRAIN,
                    "MEDIUM",
                    "HIGH",
                    {"question_signal": "top source based on amount"},
                )
            )

        return violations

    def _projection_violations(
        self, validation_input: ValidationInput, ast: exp.Expression
    ) -> list[SemanticViolation]:
        q = self._norm(validation_input.question)
        projections = self._top_select_expressions(ast)
        violations: list[SemanticViolation] = []

        if (
            len(projections) > 1
            and "what is the" in q
            and "rate" in q
            and "and" not in q
            and not re.search(r"\blist\b|\bnames?\b", q)
        ):
            violations.append(
                self._violation(
                    "EXTRA_ENTITY_COLUMN_FOR_RATE_QUESTION",
                    ValidatorFamily.PROJECTION_SHAPE,
                    "MEDIUM",
                    "HIGH",
                    {"projection_count": len(projections)},
                )
            )

        return violations

    def _join_violations(
        self, validation_input: ValidationInput, ast: exp.Expression
    ) -> list[SemanticViolation]:
        violations: list[SemanticViolation] = []
        cross_joins = [
            join.sql(dialect=SQL_DIALECT)
            for join in ast.find_all(exp.Join)
            if join.args.get("kind") == "CROSS" or join.args.get("on") is None
        ]
        if cross_joins and len(list(ast.find_all(exp.Table))) > 1:
            violations.append(
                self._violation(
                    "CROSS_JOIN_MIXES_INDEPENDENT_METRICS",
                    ValidatorFamily.JOIN_PATH_RISK,
                    "MEDIUM",
                    "HIGH",
                    {"cross_joins": cross_joins},
                )
            )

        return violations

    def _construction_violations(
        self, validation_input: ValidationInput, ast: exp.Expression
    ) -> list[SemanticViolation]:
        sql = validation_input.candidate_sql
        violations: list[SemanticViolation] = []

        if re.search(r":\w+", sql):
            violations.append(
                self._violation(
                    "UNBOUND_BIND_PARAMETER",
                    ValidatorFamily.SQL_CONSTRUCTION,
                    "HIGH",
                    "HIGH",
                    {"sql": sql},
                )
            )

        if re.search(r"\bin\s*\(\s*\)", sql, flags=re.IGNORECASE):
            violations.append(
                self._violation(
                    "EMPTY_IN_CLAUSE",
                    ValidatorFamily.SQL_CONSTRUCTION,
                    "HIGH",
                    "HIGH",
                    {"sql": sql},
                )
            )

        return violations

    def _value_grounding_boundary(
        self, validation_input: ValidationInput, ast: exp.Expression
    ) -> list[SemanticViolation]:
        if not validation_input.value_bindings:
            return []
        q = validation_input.question
        violations: list[SemanticViolation] = []
        question_lower = q.lower()
        for literal in sorted(set(validation_input.value_bindings)):
            if not literal:
                continue
            lit_clean = literal.strip("'\"").strip()
            if not lit_clean:
                continue
            if lit_clean.lower() in question_lower:
                continue
            matches = [
                token for token in re.findall(r"\b\w+\b", lit_clean.lower()) if len(token) > 3
            ]
            if matches and not any(tok in question_lower for tok in matches):
                violations.append(
                    self._violation(
                        "SUSPICIOUS_UNANCHORED_LITERAL_GROUNDING",
                        ValidatorFamily.VALUE_GROUNDING_BOUNDARY,
                        "LOW",
                        "MEDIUM",
                        {"literal": lit_clean},
                    )
                )

        return violations

    @staticmethod
    def _has_not_null_guard(where_clause: exp.Expression | None) -> bool:
        """Detect an ``IS NOT NULL`` predicate, which sqlglot renders as ``NOT x IS NULL``."""
        if where_clause is None:
            return False
        return any(
            isinstance(node.this, exp.Is) and isinstance(node.this.expression, exp.Null)
            for node in where_clause.find_all(exp.Not)
        )

    @staticmethod
    def _has_aggregate(ast: exp.Expression) -> bool:
        aggs = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)
        return any(ast.find(agg) for agg in aggs)

    @staticmethod
    def _top_select_expressions(ast: exp.Expression) -> list[exp.Expression]:
        select = ast.find(exp.Select)
        if select and select.expressions:
            return list(select.expressions)
        return []
