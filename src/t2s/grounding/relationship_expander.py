from dataclasses import dataclass

from t2s.catalog import CatalogForeignKey, CatalogPort
from t2s.grounding.retrieval_ranker import RankedTableCandidate
from t2s.grounding.schema_retriever import tokenize_search_text


@dataclass(frozen=True)
class RelationshipExpansion:
    table_fqns: tuple[str, ...]
    relationships: tuple[CatalogForeignKey, ...]


class RelationshipExpander:
    def __init__(self, catalog: CatalogPort) -> None:
        self.catalog = catalog

    def expand_one_hop_relationships(
        self,
        question: str,
        ranked_table_candidates: list[RankedTableCandidate],
        allowed_table_fqns: set[str],
        max_hydrated_tables: int,
        max_relationships: int,
    ) -> RelationshipExpansion:
        query_tokens = tokenize_search_text(question)
        selected_table_fqns = [candidate.table_fqn for candidate in ranked_table_candidates]
        selected_table_fqn_set = set(selected_table_fqns)
        candidate_table_fqns = selected_table_fqn_set
        relationships: list[CatalogForeignKey] = []
        relationship_keys: set[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = set()

        for table_fqn in list(selected_table_fqns):
            for foreign_key in self.catalog.get_relationships(table_fqn):
                if len(relationships) >= max_relationships:
                    break
                related_table_fqn = self._get_related_table_fqn(table_fqn, foreign_key)
                if related_table_fqn not in allowed_table_fqns:
                    continue
                is_already_selected = related_table_fqn in selected_table_fqn_set
                if not is_already_selected and not self._relationship_matches_query(
                    foreign_key, query_tokens
                ):
                    continue
                relationship_key = (
                    foreign_key.from_table_fqn,
                    tuple(foreign_key.from_column_names),
                    foreign_key.to_table_fqn,
                    tuple(foreign_key.to_column_names),
                )
                if relationship_key in relationship_keys:
                    continue
                relationship_keys.add(relationship_key)
                relationships.append(foreign_key)
                if (
                    related_table_fqn not in candidate_table_fqns
                    and len(candidate_table_fqns) < max_hydrated_tables
                ):
                    selected_table_fqns.append(related_table_fqn)
                    candidate_table_fqns.add(related_table_fqn)

        return RelationshipExpansion(
            table_fqns=tuple(selected_table_fqns[:max_hydrated_tables]),
            relationships=tuple(relationships[:max_relationships]),
        )

    def _get_related_table_fqn(self, table_fqn: str, foreign_key: CatalogForeignKey) -> str:
        if table_fqn == foreign_key.from_table_fqn:
            return foreign_key.to_table_fqn
        return foreign_key.from_table_fqn

    def _relationship_matches_query(
        self,
        foreign_key: CatalogForeignKey,
        query_tokens: set[str],
    ) -> bool:
        relationship_tokens = tokenize_search_text(
            " ".join(
                [
                    foreign_key.from_table_fqn,
                    foreign_key.to_table_fqn,
                    " ".join(foreign_key.from_column_names),
                    " ".join(foreign_key.to_column_names),
                ]
            )
        )
        return bool(query_tokens & relationship_tokens)
