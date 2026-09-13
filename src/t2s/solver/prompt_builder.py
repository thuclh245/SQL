from pathlib import Path

from t2s.contracts import GroundingContext, QueryRequest
from t2s.contracts.sql_candidate import SupportedSqlDialect


class DirectSqlPromptBuilder:
    def __init__(
        self,
        prompt_directory: Path | None = None,
        prompt_version: str = "v001",
    ) -> None:
        self.prompt_version = prompt_version
        self.prompt_directory = prompt_directory or Path("prompts/direct_sql")

    def build_solver_messages(
        self,
        query_request: QueryRequest,
        grounding_context: GroundingContext,
        target_dialect: SupportedSqlDialect,
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
            glossary_hits=self._format_glossary_hits(grounding_context),
            value_bindings=self._format_value_bindings(grounding_context),
            validated_examples=self._format_validated_examples(grounding_context),
            unresolved=self._format_unresolved(grounding_context),
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _read_prompt_file(self, file_name: str) -> str:
        prompt_path = self.prompt_directory / file_name
        return prompt_path.read_text(encoding="utf-8")

    def _format_authorized_schema(self, grounding_context: GroundingContext) -> str:
        formatted_tables: list[str] = []
        for table_context in grounding_context.tables:
            formatted_columns = [
                (
                    f"  - {column.name} {column.data_type}"
                    f"{': ' + column.description if column.description else ''}"
                )
                for column in table_context.columns
            ]
            formatted_relationships = [
                (
                    "  relationship: "
                    f"{relationship.from_table_fqn}.{relationship.from_column} -> "
                    f"{relationship.to_table_fqn}.{relationship.to_column}"
                )
                for relationship in table_context.relationships
            ]
            table_lines = [
                f"table: {table_context.fqn}",
                f"description: {table_context.description or ''}",
                "columns:",
                *formatted_columns,
                *formatted_relationships,
            ]
            formatted_tables.append("\n".join(table_lines))
        return "\n\n".join(formatted_tables)

    def _format_glossary_hits(self, grounding_context: GroundingContext) -> str:
        return "\n".join(
            f"- {glossary_hit.term}: {glossary_hit.definition}"
            for glossary_hit in grounding_context.glossary_hits
        )

    def _format_value_bindings(self, grounding_context: GroundingContext) -> str:
        return "\n".join(
            f"- {value_binding.phrase} -> {value_binding.column_fqn} = {value_binding.value}"
            for value_binding in grounding_context.value_bindings
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
