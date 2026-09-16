"""OpenMetadata Provider Port Implementation.

Acquires, filters, normalizes, and canonicalizes metadata from OpenMetadata REST APIs
into the provider-neutral T2S Canonical Metadata Model, enforcing strict scope
containment, pagination completeness, and pilot cardinality caps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from t2s.catalog.canonical_metadata import CatalogTable
from t2s.catalog.metadata_provider import MetadataProviderPort
from t2s.catalog.metadata_scope import MetadataScope
from t2s.errors import (
    MetadataCardinalityLimitExceededError,
    MetadataCatalogError,
    MetadataSyncError,
)
from t2s.security.error_sanitizer import sanitize_error_message

if TYPE_CHECKING:
    from t2s.integrations.openmetadata.openmetadata_client import OpenMetadataClient

logger = structlog.get_logger("t2s.catalog.openmetadata_provider")


class OpenMetadataProvider(MetadataProviderPort):
    """MetadataProviderPort implementation for OpenMetadata."""

    def __init__(
        self,
        client: OpenMetadataClient,
        service_name: str = "openmetadata",
        pilot_fqns: list[str] | None = None,
        default_scope: MetadataScope | None = None,
    ) -> None:
        self.client = client
        self.service_name = service_name
        self.pilot_fqns = [f.strip() for f in pilot_fqns if f.strip()] if pilot_fqns else None
        self.default_scope = default_scope

    @property
    def source_system(self) -> str:
        return "openmetadata"

    def fetch_metadata(self, scope: MetadataScope | None = None) -> list[CatalogTable]:
        """Acquire, filter, normalize, and validate canonical table metadata from OpenMetadata.

        Enforces:
        1. Exact FQN direct retrieval when exact pilot FQNs are configured or scoped.
        2. Filter pushdown to database/databaseSchema list queries.
        3. Strict cardinality limits (fail-closed, zero silent truncation).
        4. In-depth post-filtering against `MetadataScope.matches_table()`.
        5. Deterministic sorting by canonical table_fqn.
        """
        effective_scope = scope if scope is not None else self.default_scope
        if (effective_scope is None or effective_scope.is_unrestricted) and not self.pilot_fqns:
            raise MetadataSyncError(
                "OpenMetadataProvider in pilot mode requires explicit pilot_fqns or a "
                "restricted MetadataScope. Unrestricted acquisition is prohibited."
            )

        tables: list[CatalogTable] = []

        try:
            # Mode A: Exact Pilot FQNs retrieval (Minimal exposure pilot strategy)
            if self.pilot_fqns:
                tables = self._fetch_exact_pilot_fqns(self.pilot_fqns, effective_scope)
            elif effective_scope is not None and self._is_exact_fqn_scope(effective_scope):
                assert effective_scope.include_tables is not None
                exact_fqns = sorted(list(effective_scope.include_tables))
                tables = self._fetch_exact_pilot_fqns(exact_fqns, effective_scope)
            else:
                # Mode B: Scoped paginated query
                tables = self._fetch_scoped_list(effective_scope)

            # Defense-in-depth: post-filter against scope
            if effective_scope is not None:
                tables = [
                    t
                    for t in tables
                    if effective_scope.matches_table(
                        table_name=t.table_name,
                        schema_name=t.schema_name,
                        database_name=t.database_name,
                        asset_type=t.table_type,
                    )
                ]

            # Cardinality enforcement on final result
            if len(tables) > self.client.max_assets:
                raise MetadataCardinalityLimitExceededError(
                    f"OpenMetadata provider produced {len(tables)} assets, exceeding "
                    f"configured maximum of {self.client.max_assets}. Aborting."
                )

            # Deterministic sorting
            tables.sort(key=lambda t: t.table_fqn)

            logger.info(
                "openmetadata_fetch_completed",
                table_count=len(tables),
                service_name=self.service_name,
                scope_fingerprint=effective_scope.compute_fingerprint()
                if effective_scope
                else None,
            )
            return tables

        except MetadataCatalogError as exc:
            clean_error = sanitize_error_message(str(exc))
            logger.error("openmetadata_fetch_failed", error=clean_error)
            raise
        except Exception as exc:
            clean_error = sanitize_error_message(str(exc))
            logger.error("openmetadata_fetch_failed", error=clean_error)
            raise MetadataSyncError(
                f"OpenMetadata metadata acquisition failed: {clean_error}"
            ) from exc

    def _is_exact_fqn_scope(self, scope: MetadataScope) -> bool:
        """Evaluate whether scope defines solely exact full names with dots and no wildcards."""
        if not scope.include_tables:
            return False
        return all("." in pat and "*" not in pat and "?" not in pat for pat in scope.include_tables)

    def _fetch_exact_pilot_fqns(
        self,
        fqns: list[str],
        scope: MetadataScope | None,
    ) -> list[CatalogTable]:
        """Retrieve exact FQNs ensuring 100% completeness (no partial drops)."""
        if len(fqns) > self.client.max_assets:
            raise MetadataCardinalityLimitExceededError(
                f"Requested exact pilot set of {len(fqns)} assets exceeds maximum "
                f"allowed limit of {self.client.max_assets}."
            )

        acquired_tables: list[CatalogTable] = []
        for fqn in fqns:
            table = self.client.get_table_by_fqn(fqn)
            acquired_tables.append(table)

        return acquired_tables

    def _fetch_scoped_list(self, scope: MetadataScope | None) -> list[CatalogTable]:
        """Retrieve tables using source-side database / schema filters."""
        database_filter: str | None = None
        schema_filter: str | None = None

        if scope is not None:
            if scope.database_names and len(scope.database_names) == 1:
                db_cand = next(iter(scope.database_names))
                if "*" not in db_cand and "?" not in db_cand:
                    database_filter = db_cand

            if scope.schema_names and len(scope.schema_names) == 1:
                sch_cand = next(iter(scope.schema_names))
                if "*" not in sch_cand and "?" not in sch_cand:
                    schema_filter = sch_cand

        return self.client.list_tables(
            database=database_filter,
            database_schema=schema_filter,
            limit=min(25, self.client.max_assets),
        )
