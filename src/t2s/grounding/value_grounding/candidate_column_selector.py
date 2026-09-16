"""Chooses which authorized columns are worth probing for literal values.

Selection uses only generic signals — declared data type, structural role,
governance tags and lexical overlap with the question. It never keys off a
particular table or column name, so behaviour is unchanged by renaming a schema.
"""

from collections.abc import Iterable, Sequence

from t2s.catalog.catalog_models import CatalogColumn, CatalogForeignKey, CatalogTable
from t2s.grounding.value_grounding.value_grounding_budget import ValueGroundingBudget
from t2s.grounding.value_grounding.value_grounding_contracts import ValueProbeColumn

# Type families whose stored form is a short label, so an equality probe against a
# term from the question is meaningful. Matched as substrings of the declared type
# to absorb parameterised spellings such as ``varchar(32)``.
TEXTUAL_TYPE_MARKERS: frozenset[str] = frozenset(
    {
        "char",
        "clob",
        "enum",
        "nvarchar",
        "string",
        "text",
        "varchar",
    }
)

# Type families excluded outright: identifiers, structured blobs and binary data
# carry no question-shaped literals, and probing them risks dumping large values.
EXCLUDED_TYPE_MARKERS: frozenset[str] = frozenset(
    {
        "array",
        "binary",
        "blob",
        "bytea",
        "geography",
        "geometry",
        "json",
        "uuid",
        "vector",
        "xml",
    }
)

# Temporal columns are deliberately excluded. Date semantics belong in query
# planning, not in distinct-value enumeration.
TEMPORAL_TYPE_MARKERS: frozenset[str] = frozenset(
    {
        "date",
        "datetime",
        "interval",
        "time",
        "timestamp",
    }
)

# Governance classifications that forbid reading sample values into a prompt.
# These are standard data-classification labels, not schema-specific rules.
SENSITIVE_TAG_MARKERS: frozenset[str] = frozenset(
    {
        "confidential",
        "credential",
        "pci",
        "phi",
        "pii",
        "restricted",
        "secret",
        "sensitive",
    }
)


def is_probeable_data_type(data_type: str) -> bool:
    """True when a declared type holds short labels suitable for equality probing."""
    normalized_type = data_type.strip().lower()
    if not normalized_type:
        return False
    if any(marker in normalized_type for marker in EXCLUDED_TYPE_MARKERS):
        return False
    if any(marker in normalized_type for marker in TEMPORAL_TYPE_MARKERS):
        return False
    return any(marker in normalized_type for marker in TEXTUAL_TYPE_MARKERS)


def is_sensitive_column(catalog_column: CatalogColumn) -> bool:
    """True when governance metadata marks the column as unsafe to sample."""
    labels = [*catalog_column.tags, *catalog_column.glossary_terms]
    return any(
        marker in label.strip().lower() for label in labels for marker in SENSITIVE_TAG_MARKERS
    )


class CandidateColumnSelector:
    """Ranks authorized columns by how likely they are to hold a filter literal."""

    def __init__(self, budget: ValueGroundingBudget | None = None) -> None:
        self.budget = budget or ValueGroundingBudget()

    def select_candidate_columns(
        self,
        catalog_tables: Sequence[CatalogTable],
        selected_column_names_by_table_fqn: dict[str, set[str]],
        relationships: Iterable[CatalogForeignKey],
        question_tokens: set[str],
    ) -> list[ValueProbeColumn]:
        """Return probeable columns, most question-relevant first.

        Columns are eligible only when they are already part of the grounded
        context, meaning they have passed authorization upstream.
        """
        join_column_names = self._collect_join_column_names(relationships)
        scored_columns: list[tuple[float, int, ValueProbeColumn]] = []

        for catalog_table in catalog_tables:
            if catalog_table.sql_identifier is None:
                continue
            grounded_column_names = selected_column_names_by_table_fqn.get(
                catalog_table.table_fqn, set()
            )
            for catalog_column in catalog_table.columns:
                if catalog_column.column_name not in grounded_column_names:
                    continue
                if not self._is_eligible(catalog_table, catalog_column, join_column_names):
                    continue
                relevance = self._score_relevance(catalog_column, question_tokens)
                scored_columns.append(
                    (
                        relevance,
                        catalog_column.ordinal_position or 0,
                        ValueProbeColumn(
                            table_fqn=catalog_table.table_fqn,
                            sql_identifier=catalog_table.sql_identifier,
                            column_name=catalog_column.column_name,
                            data_type=catalog_column.data_type,
                        ),
                    )
                )

        scored_columns.sort(key=lambda entry: (-entry[0], entry[1], entry[2].column_name))
        return [column for _, _, column in scored_columns[: self.budget.max_value_columns]]

    def _is_eligible(
        self,
        catalog_table: CatalogTable,
        catalog_column: CatalogColumn,
        join_column_names: set[tuple[str, str]],
    ) -> bool:
        if not is_probeable_data_type(catalog_column.data_type):
            return False
        if is_sensitive_column(catalog_column):
            return False
        # Keys identify rows rather than categorise them, and their domains are as
        # large as the table.
        if catalog_column.is_primary_key:
            return False
        if catalog_column.column_name in catalog_table.primary_key_column_names:
            return False
        return (catalog_table.table_fqn, catalog_column.column_name) not in join_column_names

    def _score_relevance(self, catalog_column: CatalogColumn, question_tokens: set[str]) -> float:
        """Score lexical overlap between the question and the column's own metadata."""
        from t2s.grounding.schema_retriever import tokenize_search_text

        column_tokens = tokenize_search_text(
            " ".join(
                [
                    catalog_column.column_name,
                    catalog_column.description or "",
                    " ".join(catalog_column.tags),
                    " ".join(catalog_column.glossary_terms),
                ]
            )
        )
        return float(len(question_tokens & column_tokens))

    def _collect_join_column_names(
        self, relationships: Iterable[CatalogForeignKey]
    ) -> set[tuple[str, str]]:
        join_column_names: set[tuple[str, str]] = set()
        for relationship in relationships:
            for column_name in relationship.from_column_names:
                join_column_names.add((relationship.from_table_fqn, column_name))
            for column_name in relationship.to_column_names:
                join_column_names.add((relationship.to_table_fqn, column_name))
        return join_column_names
