from collections.abc import Iterable
from time import perf_counter

from t2s.catalog import CatalogColumn, CatalogForeignKey, CatalogPort, CatalogTable
from t2s.contracts import (
    ColumnContext,
    EvidenceRef,
    GroundingContext,
    GroundingIssue,
    QueryRequest,
    RelationshipEvidence,
    TableContext,
    ValueBinding,
)
from t2s.grounding.grounding_budget import GroundingBudget
from t2s.grounding.relationship_expander import RelationshipExpander
from t2s.grounding.retrieval_ranker import RankedTableCandidate, RetrievalRanker
from t2s.grounding.schema_retriever import SchemaRetriever, tokenize_search_text
from t2s.grounding.value_grounding.value_grounder import ValueGrounder
from t2s.grounding.value_grounding.value_grounding_contracts import (
    ValueGroundingDiagnostics,
    ValueGroundingResult,
)
from t2s.security import AuthorizationService, UserIdentity


class GroundingContextBuilder:
    def __init__(
        self,
        catalog: CatalogPort,
        schema_retriever: SchemaRetriever,
        authorization_service: AuthorizationService,
        grounding_budget: GroundingBudget | None = None,
        retrieval_ranker: RetrievalRanker | None = None,
        relationship_expander: RelationshipExpander | None = None,
        value_grounder: ValueGrounder | None = None,
    ) -> None:
        self.catalog = catalog
        self.schema_retriever = schema_retriever
        self.authorization_service = authorization_service
        self.grounding_budget = grounding_budget or GroundingBudget()
        self.retrieval_ranker = retrieval_ranker or RetrievalRanker()
        self.relationship_expander = relationship_expander or RelationshipExpander(catalog)
        # Optional: when unset, value_bindings stays empty and the solver falls
        # back to schema evidence alone.
        self.value_grounder = value_grounder

    def build_grounding_context(
        self,
        query_request: QueryRequest,
        user_identity: UserIdentity,
        metadata_snapshot_id: str = "unknown",
    ) -> GroundingContext:
        started_at = perf_counter()
        authorized_table_fqns = {
            resource.catalog_fqn
            for resource in self.authorization_service.get_authorized_resources(user_identity)
        }
        is_small_db = (
            self.grounding_budget.small_db_threshold > 0
            and len(authorized_table_fqns) <= self.grounding_budget.small_db_threshold
        )
        if is_small_db:
            schema_candidates = []
            ranked_table_candidates = []
            selected_table_fqns = sorted(list(authorized_table_fqns))[
                : self.grounding_budget.max_hydrated_tables
            ]
            selected_set = set(selected_table_fqns)
            all_relationships: list[CatalogForeignKey] = []
            rel_keys: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()
            for tfqn in selected_table_fqns:
                for fk in self.catalog.get_relationships(tfqn):
                    if len(all_relationships) >= self.grounding_budget.max_relationships:
                        break
                    related = fk.to_table_fqn if tfqn == fk.from_table_fqn else fk.from_table_fqn
                    if related in selected_set:
                        k = (
                            fk.from_table_fqn,
                            tuple(fk.from_column_names),
                            fk.to_table_fqn,
                            tuple(fk.to_column_names),
                        )
                        if k not in rel_keys:
                            rel_keys.add(k)
                            all_relationships.append(fk)
            relationships: tuple[CatalogForeignKey, ...] = tuple(all_relationships)
        else:
            schema_candidates = self.schema_retriever.retrieve_schema_candidates(
                question=query_request.question,
                allowed_table_fqns=authorized_table_fqns,
                limit=self.grounding_budget.max_candidate_tables,
            )
            ranked_table_candidates = self.retrieval_ranker.rank_table_candidates(
                schema_candidates,
                max_tables=self.grounding_budget.max_hydrated_tables,
            )
            relationship_expansion = self.relationship_expander.expand_one_hop_relationships(
                question=query_request.question,
                ranked_table_candidates=ranked_table_candidates,
                allowed_table_fqns=authorized_table_fqns,
                max_hydrated_tables=self.grounding_budget.max_hydrated_tables,
                max_relationships=self.grounding_budget.max_relationships,
                expansion_mode=self.grounding_budget.relationship_expansion_mode,
            )
            selected_table_fqns = list(relationship_expansion.table_fqns)
            relationships = relationship_expansion.relationships

        ranked_candidates_by_fqn = {
            ranked_candidate.table_fqn: ranked_candidate
            for ranked_candidate in ranked_table_candidates
        }
        selected_catalog_tables = self.catalog.get_tables_by_fqn(selected_table_fqns)
        table_contexts, unresolved_issues = self._build_table_contexts(
            catalog_tables=selected_catalog_tables,
            ranked_candidates_by_fqn=ranked_candidates_by_fqn,
            relationships=relationships,
            query_text=query_request.question,
        )
        value_grounding_result = self._ground_values(
            question=query_request.question,
            catalog_tables=selected_catalog_tables,
            table_contexts=table_contexts,
            relationships=relationships,
        )
        evidence_refs = self._build_evidence_refs(
            ranked_table_candidates=ranked_table_candidates,
            relationships=relationships,
            metadata_snapshot_id=metadata_snapshot_id,
        )
        evidence_refs.extend(self._build_value_evidence_refs(value_grounding_result))
        latency_ms = round((perf_counter() - started_at) * 1000, 3)
        selected_column_count = sum(len(table_context.columns) for table_context in table_contexts)
        return GroundingContext(
            scope_id=user_identity.tenant_id or user_identity.user_id,
            tables=table_contexts,
            value_bindings=self._build_value_bindings(value_grounding_result),
            unresolved=unresolved_issues,
            evidence=evidence_refs,
            retrieval_signals={
                "candidate_count": float(len(schema_candidates)),
                "ranked_table_count": float(len(ranked_table_candidates)),
                "selected_table_count": float(len(table_contexts)),
                "selected_column_count": float(selected_column_count),
                "grounding_latency_ms": latency_ms,
                "value_binding_count": float(value_grounding_result.diagnostics.binding_count),
                "value_probe_count": float(value_grounding_result.diagnostics.probe_count),
                "value_grounding_latency_ms": value_grounding_result.diagnostics.elapsed_ms,
            },
        )

    def _ground_values(
        self,
        question: str,
        catalog_tables: list[CatalogTable],
        table_contexts: list[TableContext],
        relationships: Iterable[CatalogForeignKey],
    ) -> ValueGroundingResult:
        """Probe grounded columns for literals, or return an empty, disabled result.

        Only columns already present in the context are offered to the grounder,
        so value lookup inherits the authorization decision made above.
        """
        if self.value_grounder is None:
            return ValueGroundingResult(
                diagnostics=ValueGroundingDiagnostics(
                    enabled=False, skipped_reason="value_grounding_disabled"
                )
            )
        grounded_column_names_by_table_fqn = {
            table_context.fqn: {column.name for column in table_context.columns}
            for table_context in table_contexts
        }
        grounded_table_fqns = set(grounded_column_names_by_table_fqn)
        return self.value_grounder.ground_values(
            question=question,
            catalog_tables=[
                catalog_table
                for catalog_table in catalog_tables
                if catalog_table.table_fqn in grounded_table_fqns
            ],
            selected_column_names_by_table_fqn=grounded_column_names_by_table_fqn,
            relationships=list(relationships),
        )

    def _build_value_bindings(
        self, value_grounding_result: ValueGroundingResult
    ) -> list[ValueBinding]:
        return [
            ValueBinding(
                phrase=binding.phrase,
                column_fqn=f"{binding.table_fqn}.{binding.column_name}",
                value=binding.candidate_value,
                match_type=binding.match_type.value,
                evidence_score=binding.evidence_score,
                evidence_ref=f"db_probe:{binding.table_fqn}.{binding.column_name}",
            )
            for binding in value_grounding_result.bindings
        ]

    def _build_value_evidence_refs(
        self, value_grounding_result: ValueGroundingResult
    ) -> list[EvidenceRef]:
        """Record that literals came from a live probe, not from metadata."""
        if not value_grounding_result.bindings:
            return []
        diagnostics = value_grounding_result.diagnostics
        return [
            EvidenceRef(
                kind="db_probe",
                source_id="value_grounding",
                summary=(
                    f"bindings={diagnostics.binding_count}; "
                    f"probed_columns={diagnostics.probed_column_count}; "
                    f"probes={diagnostics.probe_count}"
                ),
            )
        ]

    def _build_table_contexts(
        self,
        catalog_tables: list[CatalogTable],
        ranked_candidates_by_fqn: dict[str, RankedTableCandidate],
        relationships: Iterable[CatalogForeignKey],
        query_text: str,
    ) -> tuple[list[TableContext], list[GroundingIssue]]:
        table_contexts: list[TableContext] = []
        unresolved_issues: list[GroundingIssue] = []
        remaining_column_budget = self.grounding_budget.max_total_columns
        relationships_by_table_fqn = self._group_relationships_by_table_fqn(relationships)
        query_tokens = tokenize_search_text(query_text)

        for catalog_table in catalog_tables:
            if catalog_table.sql_identifier is None:
                unresolved_issues.append(
                    GroundingIssue(
                        code="unresolved_sql_identifier",
                        message=(
                            f"Catalog table {catalog_table.table_fqn} was relevant but has no "
                            "executable SQL identifier."
                        ),
                    )
                )
                continue
            if remaining_column_budget <= 0:
                break
            ranked_candidate = ranked_candidates_by_fqn.get(catalog_table.table_fqn)
            selected_columns = self._select_columns_for_table(
                catalog_table=catalog_table,
                ranked_candidate=ranked_candidate,
                table_relationships=relationships_by_table_fqn.get(catalog_table.table_fqn, []),
                query_tokens=query_tokens,
                remaining_column_budget=remaining_column_budget,
            )
            remaining_column_budget -= len(selected_columns)
            table_contexts.append(
                TableContext(
                    fqn=catalog_table.table_fqn,
                    sql_identifier=catalog_table.sql_identifier,
                    description=catalog_table.description,
                    columns=[
                        ColumnContext(
                            name=column.column_name,
                            data_type=column.data_type,
                            description=column.description,
                            # Preserve unknown (None) instead of asserting True;
                            # fabricating nullability misleads the solver (F1).
                            is_nullable=column.is_nullable,
                            is_primary_key=column.is_primary_key
                            or column.column_name in catalog_table.primary_key_column_names,
                        )
                        for column in selected_columns
                    ],
                    relationships=[
                        self._build_relationship_evidence(relationship)
                        for relationship in relationships_by_table_fqn.get(
                            catalog_table.table_fqn,
                            [],
                        )
                    ],
                )
            )
        return table_contexts, unresolved_issues

    def _select_columns_for_table(
        self,
        catalog_table: CatalogTable,
        ranked_candidate: RankedTableCandidate | None,
        table_relationships: list[CatalogForeignKey],
        query_tokens: set[str],
        remaining_column_budget: int,
    ) -> list[CatalogColumn]:
        matched_column_names = (
            set(ranked_candidate.matched_column_names) if ranked_candidate else set()
        )
        required_column_names = {
            *catalog_table.primary_key_column_names,
            *[
                column_name
                for relationship in table_relationships
                for column_name in self._relationship_column_names(catalog_table, relationship)
            ],
        }
        scored_columns = [
            (
                self._score_column(
                    catalog_column,
                    query_tokens,
                    matched_column_names,
                    required_column_names,
                ),
                catalog_column.ordinal_position
                if catalog_column.ordinal_position is not None
                else len(catalog_table.columns),
                catalog_column,
            )
            for catalog_column in catalog_table.columns
        ]
        selected_columns: list[CatalogColumn] = []
        selected_column_names: set[str] = set()
        maximum_columns = min(self.grounding_budget.max_columns_per_table, remaining_column_budget)
        for _, _, catalog_column in sorted(
            scored_columns,
            key=lambda scored_column: (scored_column[0], -scored_column[1]),
            reverse=True,
        ):
            if len(selected_columns) >= maximum_columns:
                break
            if catalog_column.column_name in selected_column_names:
                continue
            if (
                catalog_column.column_name in required_column_names
                or catalog_column.column_name in matched_column_names
                or self._column_matches_query(catalog_column, query_tokens)
                or (
                    not self.grounding_budget.fill_column_budget
                    and len(selected_columns) < min(3, maximum_columns)
                )
            ):
                selected_columns.append(catalog_column)
                selected_column_names.add(catalog_column.column_name)
        if self.grounding_budget.fill_column_budget:
            for _, _, catalog_column in sorted(
                scored_columns,
                key=lambda scored_column: (scored_column[0], -scored_column[1]),
                reverse=True,
            ):
                if len(selected_columns) >= maximum_columns:
                    break
                if catalog_column.column_name in selected_column_names:
                    continue
                selected_columns.append(catalog_column)
                selected_column_names.add(catalog_column.column_name)
        return sorted(
            selected_columns,
            key=lambda column: (
                column.ordinal_position
                if column.ordinal_position is not None
                else len(catalog_table.columns)
            ),
        )

    def _score_column(
        self,
        catalog_column: CatalogColumn,
        query_tokens: set[str],
        matched_column_names: set[str],
        required_column_names: set[str],
    ) -> float:
        score = 0.0
        if catalog_column.column_name in required_column_names:
            score += 5.0
        if catalog_column.column_name in matched_column_names:
            score += 4.0
        if catalog_column.is_primary_key:
            score += 2.0
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
        score += len(query_tokens & column_tokens)
        return score

    def _column_matches_query(
        self,
        catalog_column: CatalogColumn,
        query_tokens: set[str],
    ) -> bool:
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
        return bool(query_tokens & column_tokens)

    def _relationship_column_names(
        self,
        catalog_table: CatalogTable,
        relationship: CatalogForeignKey,
    ) -> list[str]:
        if catalog_table.table_fqn == relationship.from_table_fqn:
            return relationship.from_column_names
        if catalog_table.table_fqn == relationship.to_table_fqn:
            return relationship.to_column_names
        return []

    def _group_relationships_by_table_fqn(
        self,
        relationships: Iterable[CatalogForeignKey],
    ) -> dict[str, list[CatalogForeignKey]]:
        relationships_by_table_fqn: dict[str, list[CatalogForeignKey]] = {}
        for relationship in relationships:
            relationships_by_table_fqn.setdefault(
                relationship.from_table_fqn,
                [],
            ).append(relationship)
            relationships_by_table_fqn.setdefault(
                relationship.to_table_fqn,
                [],
            ).append(relationship)
        return relationships_by_table_fqn

    def _build_relationship_evidence(
        self,
        foreign_key: CatalogForeignKey,
    ) -> RelationshipEvidence:
        return RelationshipEvidence(
            from_table_fqn=foreign_key.from_table_fqn,
            from_columns=foreign_key.from_column_names,
            to_table_fqn=foreign_key.to_table_fqn,
            to_columns=foreign_key.to_column_names,
            relationship_type="many_to_one",
            evidence_summary=foreign_key.relationship_name or foreign_key.provenance,
        )

    def _build_evidence_refs(
        self,
        ranked_table_candidates: list[RankedTableCandidate],
        relationships: Iterable[CatalogForeignKey],
        metadata_snapshot_id: str,
    ) -> list[EvidenceRef]:
        evidence_refs = [
            EvidenceRef(
                kind="metadata",
                source_id=f"retrieval:{ranked_candidate.table_fqn}",
                source_version=metadata_snapshot_id,
                summary=(
                    f"score={ranked_candidate.ranking_score}; "
                    f"matched_fields={','.join(ranked_candidate.matched_fields)}; "
                    f"matched_columns={','.join(ranked_candidate.matched_column_names)}"
                ),
            )
            for ranked_candidate in ranked_table_candidates
        ]
        evidence_refs.extend(
            EvidenceRef(
                kind="metadata",
                source_id=f"relationship:{relationship.from_table_fqn}->{relationship.to_table_fqn}",
                source_version=metadata_snapshot_id,
                summary=(
                    f"{relationship.from_table_fqn}({','.join(relationship.from_column_names)}) "
                    f"-> {relationship.to_table_fqn}({','.join(relationship.to_column_names)})"
                ),
            )
            for relationship in relationships
        )
        return evidence_refs
