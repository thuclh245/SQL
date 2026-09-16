from pathlib import Path
from typing import Any

from t2s.contracts import GroundingContext, QueryRequest
from t2s.contracts.sql_candidate import SupportedSqlDialect


class DirectSqlPromptBuilder:
    def __init__(
        self,
        prompt_directory: Path | None = None,
        prompt_version: str = "v001",
    ) -> None:
        self.prompt_version = prompt_version
        self.prompt_directory = prompt_directory or self._resolve_default_prompt_directory()

    def build_solver_messages(
        self,
        query_request: QueryRequest,
        grounding_context: GroundingContext,
        target_dialect: SupportedSqlDialect,
        semantic_plan: Any | None = None,
    ) -> list[dict[str, str]]:
        system_prompt = self._read_prompt_file(f"{self.prompt_version}_system.md")
        user_template = self._read_prompt_file(f"{self.prompt_version}_user_template.md")
        authorized_schema = self._format_authorized_schema(grounding_context)
        user_prompt = user_template.format(
            question=query_request.question,
            locale=query_request.locale,
            target_hint=query_request.target_hint or "",
            target_dialect=target_dialect,
            authorized_schema=authorized_schema,
            evidence=self._format_evidence(query_request),
            glossary_hits=self._format_glossary_hits(grounding_context),
            value_bindings=self._format_value_bindings(grounding_context),
            validated_examples=self._format_validated_examples(grounding_context),
            unresolved=self._format_unresolved(grounding_context),
        )
        if semantic_plan is not None:
            formatted_plan = self._format_semantic_plan(semantic_plan)
            user_prompt = f"{user_prompt}\n\nSemantic plan contract:\n{formatted_plan}"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _format_semantic_plan(self, plan: Any) -> str:
        raw_agg = getattr(plan, "aggregation", None)
        agg = getattr(raw_agg, "value", raw_agg)
        grain = getattr(plan, "grain", None)
        req_grain = getattr(grain, "requested_grain", "unknown")
        src_grain = getattr(grain, "source_grain", "unknown")
        norm_req = getattr(grain, "requires_normalization", False)

        dimensions = getattr(plan, "dimensions", [])
        filters = getattr(plan, "filters", [])
        filter_strs: list[str] = []
        for f in filters:
            col = getattr(f, "column_name", "")
            op = getattr(f, "operator", "")
            val = getattr(f, "target_value", "")
            filter_strs.append(f"{col} {op} {val}".strip())

        time_scope = getattr(plan, "time_scope", None)
        population_scope = getattr(plan, "population_scope", None)
        expectation = getattr(plan, "expectation", None)
        exp_shape = getattr(expectation, "expected_shape", None)
        exp_shape_val = getattr(exp_shape, "value", exp_shape)
        exp_type = getattr(expectation, "expected_value_type", None)
        exp_type_val = getattr(exp_type, "value", exp_type)
        can_empty = getattr(expectation, "can_be_empty", None)

        lines = [
            f"- metric: {getattr(plan, 'metric_name', None) or 'none'}",
            f"- aggregation: {agg}",
            f"- dimensions: {', '.join(dimensions) or 'none'}",
            f"- population_scope: {population_scope or 'none'}",
            f"- time_scope: {time_scope or 'none'}",
            f"- filters: {'; '.join(filter_strs) or 'none'}",
            f"- requested_grain: {req_grain}",
            f"- source_grain: {src_grain}",
            f"- normalization_required: {norm_req}",
            f"- expected_shape: {exp_shape_val or 'unknown'}",
            f"- expected_value_type: {exp_type_val or 'unknown'}",
            f"- can_be_empty: {can_empty if can_empty is not None else 'unknown'}",
            f"- relevant_tables: {', '.join(getattr(plan, 'relevant_tables', [])) or 'none'}",
            f"- relevant_columns: {', '.join(getattr(plan, 'relevant_columns', [])) or 'none'}",
            f"- assumptions: {'; '.join(getattr(plan, 'assumptions', [])) or 'none'}",
            f"- uncertainties: {'; '.join(getattr(plan, 'uncertainties', [])) or 'none'}",
        ]
        return "\n".join(lines)

    def _read_prompt_file(self, file_name: str) -> str:
        prompt_path = self.prompt_directory / file_name
        return prompt_path.read_text(encoding="utf-8")

    def _format_authorized_schema(self, grounding_context: GroundingContext) -> str:
        formatted_tables: list[str] = []
        for table_context in grounding_context.tables:
            formatted_columns = [
                (
                    f"  - name: {column.name}; type: {column.data_type}; "
                    f"nullable: {column.is_nullable}; primary_key: {column.is_primary_key}; "
                    f"description: {column.description or ''}"
                )
                for column in table_context.columns
            ]
            formatted_relationships = [
                (
                    f"  - type: {relationship.relationship_type}; "
                    f"from_fqn: {relationship.from_table_fqn}; "
                    f"from_columns: {', '.join(relationship.from_columns)}; "
                    f"to_fqn: {relationship.to_table_fqn}; "
                    f"to_columns: {', '.join(relationship.to_columns)}; "
                    f"evidence: {relationship.evidence_summary or ''}"
                )
                for relationship in table_context.relationships
            ]
            table_lines = [
                f"catalog_fqn: {table_context.fqn}",
                f"sql_identifier: {table_context.sql_identifier}",
                f"description: {table_context.description or ''}",
                "columns:",
                *formatted_columns,
                "relationships:",
                *formatted_relationships,
            ]
            formatted_tables.append("\n".join(table_lines))
        return "\n\n".join(formatted_tables)

    def _resolve_default_prompt_directory(self) -> Path:
        repository_root = Path(__file__).resolve().parents[3]
        return repository_root / "prompts" / "direct_sql"

    def _format_glossary_hits(self, grounding_context: GroundingContext) -> str:
        return "\n".join(
            f"- {glossary_hit.term}: {glossary_hit.definition}"
            for glossary_hit in grounding_context.glossary_hits
        )

    def _format_evidence(self, query_request: QueryRequest) -> str:
        """Render supplied business evidence as its own block.

        Kept out of the question text so the model reads it as reference material
        rather than as part of the user's instruction.
        """
        return "\n".join(f"- {statement}" for statement in query_request.evidence)

    def _format_value_bindings(self, grounding_context: GroundingContext) -> str:
        """Group observed literals by column, compactly.

        Values are rendered in the database's own spelling and quoted, so the
        model can copy a literal that will compare equal.
        """
        values_by_column: dict[str, list[str]] = {}
        phrases_by_column: dict[str, list[str]] = {}
        for value_binding in grounding_context.value_bindings:
            values = values_by_column.setdefault(value_binding.column_fqn, [])
            if value_binding.value not in values:
                values.append(value_binding.value)
            phrases = phrases_by_column.setdefault(value_binding.column_fqn, [])
            if value_binding.phrase not in phrases:
                phrases.append(value_binding.phrase)
        return "\n".join(
            f"- {column_fqn}: "
            + ", ".join(f"'{value}'" for value in values)
            + f"  (question terms: {', '.join(phrases_by_column[column_fqn])})"
            for column_fqn, values in values_by_column.items()
        )

    def _format_validated_examples(self, grounding_context: GroundingContext) -> str:
        return "\n\n".join(
            f"question: {example.question}\nsql: {example.sql}"
            for example in grounding_context.examples
        )

    def _format_unresolved(self, grounding_context: GroundingContext) -> str:
        return "\n".join(
            f"- {grounding_issue.code}: {grounding_issue.message}"
            for grounding_issue in grounding_context.unresolved
        )
