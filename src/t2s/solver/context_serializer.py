"""Deterministic context serializers for evaluation and production prompts."""

from collections.abc import Callable
from typing import Literal

from t2s.contracts import GroundingContext

SerializationArm = Literal["S0", "S1", "S2", "S3"]


def serialize_schema_s0_baseline(grounding_context: GroundingContext) -> str:
    """S0: Exact frozen B0 baseline serialization.

    Preserves legacy formatting with all catalog prefixes and empty attributes.
    """
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


def serialize_schema_s1_deduplicated_relationships(grounding_context: GroundingContext) -> str:
    """S1: Relationship deduplication.

    Eliminates duplicated/bidirectional foreign key descriptions across tables.
    Each unique (from_table, from_cols, to_table, to_cols) relationship is rendered once.
    """
    formatted_tables: list[str] = []
    seen_relationships: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()

    for table_context in grounding_context.tables:
        formatted_columns = [
            (
                f"  - name: {column.name}; type: {column.data_type}; "
                f"nullable: {column.is_nullable}; primary_key: {column.is_primary_key}; "
                f"description: {column.description or ''}"
            )
            for column in table_context.columns
        ]
        formatted_relationships: list[str] = []
        for rel in table_context.relationships:
            rel_key = (
                rel.from_table_fqn,
                tuple(rel.from_columns),
                rel.to_table_fqn,
                tuple(rel.to_columns),
            )
            if rel_key in seen_relationships:
                continue
            seen_relationships.add(rel_key)
            formatted_relationships.append(
                f"  - type: {rel.relationship_type}; "
                f"from_fqn: {rel.from_table_fqn}; "
                f"from_columns: {', '.join(rel.from_columns)}; "
                f"to_fqn: {rel.to_table_fqn}; "
                f"to_columns: {', '.join(rel.to_columns)}; "
                f"evidence: {rel.evidence_summary or ''}"
            )

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


def serialize_schema_s2_compact_identifiers(grounding_context: GroundingContext) -> str:
    """S2: Compact identifier representation.

    Reduces long catalog prefix noise by using unambiguous identifiers for relationships,
    preserving full qualification only where necessary.
    """
    fqn_to_identifier: dict[str, str] = {
        table.fqn: table.sql_identifier or table.fqn.split(".")[-1]
        for table in grounding_context.tables
    }

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
        formatted_relationships = []
        for rel in table_context.relationships:
            from_ident = fqn_to_identifier.get(rel.from_table_fqn, rel.from_table_fqn)
            to_ident = fqn_to_identifier.get(rel.to_table_fqn, rel.to_table_fqn)
            formatted_relationships.append(
                f"  - type: {rel.relationship_type}; "
                f"from_fqn: {from_ident}; "
                f"from_columns: {', '.join(rel.from_columns)}; "
                f"to_fqn: {to_ident}; "
                f"to_columns: {', '.join(rel.to_columns)}; "
                f"evidence: {rel.evidence_summary or ''}"
            )
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


def serialize_schema_s3_empty_metadata_suppression(grounding_context: GroundingContext) -> str:
    """S3: Empty / low-information metadata suppression.

    Suppresses empty placeholder fields (such as 'description: ' when empty),
    presenting only populated attributes.
    """
    formatted_tables: list[str] = []
    for table_context in grounding_context.tables:
        formatted_columns: list[str] = []
        for column in table_context.columns:
            parts = [
                f"name: {column.name}",
                f"type: {column.data_type}",
                f"nullable: {column.is_nullable}",
                f"primary_key: {column.is_primary_key}",
            ]
            if column.description:
                parts.append(f"description: {column.description}")
            formatted_columns.append(f"  - {'; '.join(parts)}")

        formatted_relationships: list[str] = []
        for relationship in table_context.relationships:
            parts = [
                f"type: {relationship.relationship_type}",
                f"from_fqn: {relationship.from_table_fqn}",
                f"from_columns: {', '.join(relationship.from_columns)}",
                f"to_fqn: {relationship.to_table_fqn}",
                f"to_columns: {', '.join(relationship.to_columns)}",
            ]
            if relationship.evidence_summary:
                parts.append(f"evidence: {relationship.evidence_summary}")
            formatted_relationships.append(f"  - {'; '.join(parts)}")

        table_lines = [
            f"catalog_fqn: {table_context.fqn}",
            f"sql_identifier: {table_context.sql_identifier}",
        ]
        if table_context.description:
            table_lines.append(f"description: {table_context.description}")
        table_lines.append("columns:")
        table_lines.extend(formatted_columns)
        if formatted_relationships:
            table_lines.append("relationships:")
            table_lines.extend(formatted_relationships)
        formatted_tables.append("\n".join(table_lines))
    return "\n\n".join(formatted_tables)


def get_schema_serializer(arm: SerializationArm) -> Callable[[GroundingContext], str]:
    """Factory to retrieve the schema serializer for the given experimental arm."""
    if arm == "S0":
        return serialize_schema_s0_baseline
    if arm == "S1":
        return serialize_schema_s1_deduplicated_relationships
    if arm == "S2":
        return serialize_schema_s2_compact_identifiers
    if arm == "S3":
        return serialize_schema_s3_empty_metadata_suppression
    raise ValueError(f"Unknown serialization arm: {arm}")
