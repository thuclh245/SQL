"""Trino readiness inspection.

Same weak check as the other dialects: the catalog must expose at least one
relation that actually holds a row. On a lakehouse this catches the failure mode
where the metastore has every table registered but the object storage behind it
was never loaded — grounding and generation both succeed and every answer is empty.
"""

from t2s.database.database_readiness import (
    DatabaseReadinessReport,
    DatabaseReadinessStatus,
)
from t2s.database.trino_rest_client import (
    TrinoClientError,
    TrinoRestClient,
    format_trino_identifier,
    format_trino_string_literal,
)

# Trino's own metadata schema, plus the staging schema the loader drops tables into.
_EXCLUDED_SCHEMAS = ("information_schema", "stg")

_READINESS_TIMEOUT_SECONDS = 30.0


class TrinoDatabaseReadinessInspector:
    """Checks a Trino catalog for relations that actually hold rows."""

    def __init__(
        self,
        client: TrinoRestClient,
        catalog: str,
        excluded_schemas: tuple[str, ...] = _EXCLUDED_SCHEMAS,
    ) -> None:
        self.client = client
        self.catalog = catalog
        self.excluded_schemas = excluded_schemas

    def inspect_readiness(self, max_relations_to_sample: int = 25) -> DatabaseReadinessReport:
        """Sample relations until one is found to be non-empty."""
        try:
            relations = self._list_relations()
        except TrinoClientError as exc:
            return DatabaseReadinessReport(
                status=DatabaseReadinessStatus.UNREACHABLE,
                detail=f"Catalog could not be inspected: {type(exc).__name__}",
            )

        if not relations:
            return DatabaseReadinessReport(
                status=DatabaseReadinessStatus.NO_USER_RELATIONS,
                detail="Catalog exposes no user relations.",
            )

        inspected = relations[:max_relations_to_sample]
        non_empty_count = 0
        for schema_name, relation_name in inspected:
            try:
                has_row = self._has_any_row(schema_name, relation_name)
            except TrinoClientError:
                # One unreadable relation is not a verdict on the catalog; a
                # partially loaded lake still counts as ready if anything reads.
                continue
            if has_row:
                non_empty_count += 1
                break

        status = (
            DatabaseReadinessStatus.READY
            if non_empty_count > 0
            else DatabaseReadinessStatus.NO_DATA_ROWS
        )
        return DatabaseReadinessReport(
            status=status,
            relation_count=len(relations),
            inspected_relation_count=len(inspected),
            non_empty_relation_count=non_empty_count,
            detail=(
                None
                if non_empty_count > 0
                else (
                    f"All {len(inspected)} inspected relations are empty or unreadable, "
                    "which indicates a catalog registered against unloaded storage."
                )
            ),
        )

    def _list_relations(self) -> list[tuple[str, str]]:
        excluded = ", ".join(
            format_trino_string_literal(schema) for schema in self.excluded_schemas
        )
        outcome = self.client.run(
            "SELECT table_schema, table_name "
            f"FROM {format_trino_identifier(self.catalog)}.information_schema.tables "
            f"WHERE table_schema NOT IN ({excluded}) "
            "ORDER BY table_schema, table_name",
            deadline_seconds=_READINESS_TIMEOUT_SECONDS,
        )
        return [(str(row[0]), str(row[1])) for row in outcome.rows]

    def _has_any_row(self, schema_name: str, relation_name: str) -> bool:
        qualified = format_trino_identifier(f"{self.catalog}.{schema_name}.{relation_name}")
        value = self.client.run_scalar(
            f"SELECT 1 FROM {qualified} LIMIT 1",
            deadline_seconds=_READINESS_TIMEOUT_SECONDS,
        )
        return value is not None
