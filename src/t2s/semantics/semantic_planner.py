"""Grounded semantic planner implementation.

Interprets the user question against grounded schema evidence into a SemanticPlan
prior to SQL code generation.
"""

from typing import Protocol
from uuid import uuid4

from t2s.contracts import GroundingContext, QueryRequest
from t2s.semantics.semantic_plan import (
    ExpectedValueType,
    MetricAggregation,
    PlannerStatus,
    ResultExpectation,
    ResultShape,
    SemanticEvidence,
    SemanticFilter,
    SemanticGrain,
    SemanticPlan,
)
from t2s.solver.chat_client import StructuredChatClient


class SemanticPlannerPort(Protocol):
    """Protocol boundary for grounded semantic planning."""

    async def plan(
        self,
        query_request: QueryRequest,
        grounding_context: GroundingContext,
    ) -> SemanticPlan:
        """Produce a structured SemanticPlan from question and grounding context."""
        ...


class GroundedSemanticPlanner:
    """Evidence-driven grounded semantic planner.

    Operates in two modes:
    1. LLM-backed mode: uses StructuredChatClient to formulate the semantic plan
       constrained by grounding evidence.
    2. Deterministic mode: extracts semantic structure directly from GroundingContext
       metadata and relationships without remote network calls.
    """

    def __init__(
        self,
        chat_client: StructuredChatClient | None = None,
        model_name: str = "gpt-oss-120b",
    ) -> None:
        self.chat_client = chat_client
        self.model_name = model_name

    async def plan(
        self,
        query_request: QueryRequest,
        grounding_context: GroundingContext,
    ) -> SemanticPlan:
        plan_id = f"plan-{uuid4()}"

        if self.chat_client is not None:
            return await self._plan_with_llm(query_request, grounding_context, plan_id)

        return self._plan_deterministic(query_request, grounding_context, plan_id)

    def _plan_deterministic(
        self,
        query_request: QueryRequest,
        grounding_context: GroundingContext,
        plan_id: str,
    ) -> SemanticPlan:
        evidence_items: list[SemanticEvidence] = []
        relevant_tables: list[str] = []
        relevant_columns: list[str] = []
        uncertainties: list[str] = []
        assumptions: list[str] = []
        filters: list[SemanticFilter] = []

        # 1. Harvest evidence from GroundingContext
        for table in grounding_context.tables:
            relevant_tables.append(table.sql_identifier)
            if table.description:
                evidence_items.append(
                    SemanticEvidence(
                        source="metadata_description",
                        entity="table",
                        field="description",
                        value=f"{table.sql_identifier}: {table.description}",
                        confidence=1.0,
                    )
                )
            for column in table.columns:
                relevant_columns.append(f"{table.sql_identifier}.{column.name}")
                if column.description:
                    evidence_items.append(
                        SemanticEvidence(
                            source="metadata_description",
                            entity="column",
                            field="description",
                            value=f"{table.sql_identifier}.{column.name}: {column.description}",
                            confidence=1.0,
                        )
                    )

        # 2. Check value bindings from grounding
        for binding in grounding_context.value_bindings:
            filters.append(
                SemanticFilter(
                    column_name=binding.column_fqn,
                    operator="=",
                    target_value=str(binding.value),
                    is_temporal=False,
                    evidence_source="grounded_value_binding",
                )
            )
            evidence_items.append(
                SemanticEvidence(
                    source="value_binding",
                    entity="column",
                    field="grounded_value",
                    value=f"{binding.phrase} -> {binding.column_fqn}={binding.value}",
                    confidence=1.0,
                )
            )

        # 3. Assess semantic grain and unit availability from evidence
        grain_discovered = "unknown"
        for ev in evidence_items:
            lower_val = ev.value.lower()
            if "monthly" in lower_val or "per month" in lower_val:
                grain_discovered = "month"
            elif "annual" in lower_val or "per year" in lower_val:
                grain_discovered = "year"
            elif "daily" in lower_val or "per day" in lower_val:
                grain_discovered = "day"

        if grain_discovered == "unknown":
            uncertainties.append("UNKNOWN_METRIC_GRAIN")
            assumptions.append("Source grain is unstated in metadata; no normalization applied.")

        # 4. Aggregation intent and metric column detection
        q_lower = query_request.question.lower()
        aggregation = MetricAggregation.NONE
        expected_shape = ResultShape.LIST
        if any(w in q_lower for w in ("total", "sum", "tổng")):
            aggregation = MetricAggregation.SUM
            expected_shape = ResultShape.SCALAR
        elif any(w in q_lower for w in ("average", "avg", "trung bình")):
            aggregation = MetricAggregation.AVG
            expected_shape = ResultShape.SCALAR
        elif any(w in q_lower for w in ("count", "how many", "số lượng", "bao nhiêu")):
            aggregation = MetricAggregation.COUNT
            expected_shape = ResultShape.SCALAR
        elif any(w in q_lower for w in ("minimum", "min", "nhỏ nhất", "thấp nhất", "ít nhất")):
            aggregation = MetricAggregation.MIN
            expected_shape = ResultShape.SCALAR
        elif any(w in q_lower for w in ("maximum", "max", "lớn nhất", "cao nhất", "nhiều nhất")):
            aggregation = MetricAggregation.MAX
            expected_shape = ResultShape.SCALAR

        # Identify target metric column from tables and columns
        target_metric: str | None = None
        for table in grounding_context.tables:
            for column in table.columns:
                col_desc = (column.description or "").lower()
                words = [w.strip("?,.") for w in q_lower.split() if len(w) > 3]
                if any(w in col_desc for w in words):
                    target_metric = column.name
                    break
                if target_metric is None and column.data_type.upper() in (
                    "NUMERIC", "INTEGER", "FLOAT", "DOUBLE", "DECIMAL", "REAL"
                ) and not column.is_primary_key and not column.name.endswith("_id"):
                    target_metric = column.name
            if target_metric:
                break

        # 5. Determine status based on grounded evidence completeness
        status = PlannerStatus.READY
        uncertainty_level = "LOW"
        if not relevant_tables:
            status = PlannerStatus.INSUFFICIENT_EVIDENCE
            uncertainty_level = "HIGH"
        elif uncertainties:
            uncertainty_level = "HIGH"

        # 6. Formulate expectation
        expectation = ResultExpectation(
            expected_shape=expected_shape,
            expected_value_type=(
                ExpectedValueType.NUMERIC
                if aggregation != MetricAggregation.NONE
                else ExpectedValueType.UNKNOWN
            ),
            can_be_empty=aggregation == MetricAggregation.NONE,
            can_be_null=False,
        )

        return SemanticPlan(
            plan_id=plan_id,
            status=status,
            metric_name=target_metric,
            aggregation=aggregation,
            dimensions=[],
            population_scope=None,
            filters=filters,
            time_scope=None,
            grain=SemanticGrain(
                requested_grain="unknown",
                source_grain=grain_discovered,
                requires_normalization=False,
            ),
            relevant_tables=relevant_tables,
            relevant_columns=relevant_columns,
            required_relationships=[
                f"{rel.from_table_fqn} -> {rel.to_table_fqn}"
                for table in grounding_context.tables
                for rel in table.relationships
            ],
            expectation=expectation,
            assumptions=assumptions,
            uncertainties=uncertainties,
            evidence=evidence_items,
            semantic_uncertainty_level=uncertainty_level,
        )

    async def _plan_with_llm(
        self,
        query_request: QueryRequest,
        grounding_context: GroundingContext,
        plan_id: str,
    ) -> SemanticPlan:
        # Structured schema generation using StructuredChatClient
        assert self.chat_client is not None
        schema = SemanticPlan.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Grounded Semantic Planner for an enterprise Text-to-SQL system.\n"
                    "Interpret the semantic meaning of the user question given ONLY the "
                    "authorized grounding context and metadata.\n"
                    "CRITICAL OPERATIONAL RULES:\n"
                    "1. Do NOT generate SQL statements.\n"
                    "2. Use only supplied grounding evidence; do not invent missing "
                    "business definitions.\n"
                    "3. If metric grain, unit, or business meaning is unstated in metadata, "
                    "mark it unknown.\n"
                    "4. Return structured output conforming strictly to SemanticPlan schema.\n"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {query_request.question}\n\n"
                    f"Target Dialect: {query_request.database_dialect or 'sqlite'}\n\n"
                    f"Authorized Grounding Context:\n"
                    + "\n".join(
                        f"Table: {t.sql_identifier} (Desc: {t.description})\n"
                        + "\n".join(
                            f"  Col: {c.name} ({c.data_type}) Desc: {c.description}"
                            for c in t.columns
                        )
                        for t in grounding_context.tables
                    )
                ),
            },
        ]
        response = await self.chat_client.generate_structured_response(
            messages=messages,
            response_schema={"name": "semantic_plan", "schema": schema, "strict": True},
            model_name=self.model_name,
            reasoning_effort=None,
            max_output_tokens=2048,
        )
        data = dict(response.content)
        data["plan_id"] = plan_id
        return SemanticPlan.model_validate(data)
