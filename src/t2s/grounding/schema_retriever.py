import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

from t2s.catalog.metadata_document import CatalogSearchDocument

CandidateResourceType = Literal["table", "column"]

TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


@dataclass(frozen=True)
class SchemaCandidate:
    table_fqn: str
    resource_type: CandidateResourceType
    retrieval_score: float
    matched_fields: tuple[str, ...]
    document_id: str
    column_fqn: str | None = None
    column_name: str | None = None


class SchemaSearchPort(Protocol):
    def search_schema_documents(
        self,
        query_text: str,
        allowed_table_fqns: set[str],
        limit: int,
    ) -> list[CatalogSearchDocument]:
        ...


class SchemaRetriever:
    def __init__(self, schema_search: SchemaSearchPort) -> None:
        self.schema_search = schema_search

    def retrieve_schema_candidates(
        self,
        question: str,
        allowed_table_fqns: set[str],
        limit: int,
    ) -> list[SchemaCandidate]:
        search_documents = self.schema_search.search_schema_documents(
            query_text=question,
            allowed_table_fqns=allowed_table_fqns,
            limit=limit,
        )
        query_tokens = tokenize_search_text(question)
        candidates: list[SchemaCandidate] = []
        for search_document in search_documents:
            matched_fields = self._match_document_fields(search_document, query_tokens)
            retrieval_score = self._score_document(search_document, query_tokens, matched_fields)
            candidates.append(
                SchemaCandidate(
                    table_fqn=search_document.table_fqn,
                    resource_type=search_document.document_type,
                    retrieval_score=retrieval_score,
                    matched_fields=tuple(matched_fields),
                    document_id=search_document.document_id,
                    column_fqn=search_document.column_fqn,
                    column_name=search_document.column_name,
                )
            )
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.retrieval_score,
                candidate.resource_type == "table",
                candidate.table_fqn,
                candidate.column_fqn or "",
            ),
            reverse=True,
        )

    def _match_document_fields(
        self,
        search_document: CatalogSearchDocument,
        query_tokens: set[str],
    ) -> list[str]:
        matched_fields: list[str] = []
        field_values = {
            "table_name": search_document.table_name,
            "column_name": search_document.column_name or "",
            "title": search_document.title,
            "description_or_text": search_document.searchable_text,
            "tags": " ".join(search_document.tags),
            "glossary_terms": " ".join(search_document.glossary_terms),
        }
        for field_name, field_value in field_values.items():
            field_tokens = tokenize_search_text(field_value)
            if query_tokens & field_tokens:
                matched_fields.append(field_name)
        return matched_fields

    def _score_document(
        self,
        search_document: CatalogSearchDocument,
        query_tokens: set[str],
        matched_fields: list[str],
    ) -> float:
        if not query_tokens:
            return 0.0
        searchable_tokens = tokenize_search_text(search_document.searchable_text)
        overlap_count = len(query_tokens & searchable_tokens)
        coverage_score = overlap_count / len(query_tokens)
        field_score = sum(
            {
                "table_name": 2.0,
                "column_name": 2.5,
                "title": 1.0,
                "description_or_text": 0.75,
                "tags": 1.5,
                "glossary_terms": 1.75,
            }[matched_field]
            for matched_field in matched_fields
        )
        document_type_score = 0.25 if search_document.document_type == "table" else 0.0
        return round(coverage_score + field_score + document_type_score, 6)


def tokenize_search_text(search_text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_token in TOKEN_PATTERN.findall(search_text):
        normalized_token = raw_token.lower().strip()
        if not normalized_token or len(normalized_token) <= 1:
            continue
        tokens.add(normalized_token)
        tokens.update(
            token_part
            for token_part in normalized_token.split("_")
            if token_part and len(token_part) > 1
        )
    return tokens


@dataclass
class InMemorySchemaSearch:
    search_documents: list[CatalogSearchDocument] = field(default_factory=list)

    def search_schema_documents(
        self,
        query_text: str,
        allowed_table_fqns: set[str],
        limit: int,
    ) -> list[CatalogSearchDocument]:
        query_tokens = tokenize_search_text(query_text)
        scored_documents: list[tuple[float, CatalogSearchDocument]] = []
        for search_document in self.search_documents:
            if search_document.table_fqn not in allowed_table_fqns:
                continue
            document_tokens = tokenize_search_text(
                " ".join(
                    [
                        search_document.title,
                        search_document.searchable_text,
                        search_document.table_fqn,
                        " ".join(search_document.tags),
                        " ".join(search_document.glossary_terms),
                    ]
                )
            )
            score = len(query_tokens & document_tokens)
            if score > 0:
                scored_documents.append((float(score), search_document))
        return [
            search_document
            for _, search_document in sorted(
                scored_documents,
                key=lambda scored_document: (
                    scored_document[0],
                    scored_document[1].document_type == "table",
                    scored_document[1].table_fqn,
                    scored_document[1].document_id,
                ),
                reverse=True,
            )[:limit]
        ]
