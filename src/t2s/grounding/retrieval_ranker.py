from dataclasses import dataclass

from t2s.grounding.schema_retriever import SchemaCandidate


@dataclass(frozen=True)
class RankedTableCandidate:
    table_fqn: str
    ranking_score: float
    candidates: tuple[SchemaCandidate, ...]
    matched_fields: tuple[str, ...]
    matched_column_names: tuple[str, ...]


class RetrievalRanker:
    def rank_table_candidates(
        self,
        schema_candidates: list[SchemaCandidate],
        max_tables: int,
    ) -> list[RankedTableCandidate]:
        grouped_candidates: dict[str, list[SchemaCandidate]] = {}
        for schema_candidate in schema_candidates:
            grouped_candidates.setdefault(schema_candidate.table_fqn, []).append(schema_candidate)

        ranked_tables: list[RankedTableCandidate] = []
        for table_fqn, table_candidates in grouped_candidates.items():
            table_score = sum(candidate.retrieval_score for candidate in table_candidates)
            table_score += 1.0 if any(
                candidate.resource_type == "table" for candidate in table_candidates
            ) else 0.0
            matched_fields = sorted(
                {
                    matched_field
                    for candidate in table_candidates
                    for matched_field in candidate.matched_fields
                }
            )
            matched_column_names = sorted(
                {
                    candidate.column_name
                    for candidate in table_candidates
                    if candidate.column_name is not None
                }
            )
            ranked_tables.append(
                RankedTableCandidate(
                    table_fqn=table_fqn,
                    ranking_score=round(table_score, 6),
                    candidates=tuple(
                        sorted(
                            table_candidates,
                            key=lambda candidate: (
                                candidate.retrieval_score,
                                candidate.resource_type == "table",
                                candidate.document_id,
                            ),
                            reverse=True,
                        )
                    ),
                    matched_fields=tuple(matched_fields),
                    matched_column_names=tuple(matched_column_names),
                )
            )

        return sorted(
            ranked_tables,
            key=lambda candidate: (candidate.ranking_score, candidate.table_fqn),
            reverse=True,
        )[:max_tables]
