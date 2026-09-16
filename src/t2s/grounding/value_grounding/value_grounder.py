"""Turns a question plus authorized columns into observed database literals.

Two bounded passes per candidate column, both parameterized and read-only:

1. targeted — one batched equality probe carrying every question term at once,
   which is what makes the cost one round trip per column rather than one per
   (term, column) pair;
2. domain — for columns the targeted pass did not hit, a capped distinct read
   that is kept only when the column proves to be enum-like.

A failed probe degrades to "no bindings" and is recorded in diagnostics; it never
propagates as a pipeline error.
"""

import difflib
from collections.abc import Callable, Sequence
from time import perf_counter

import structlog

from t2s.catalog.catalog_models import CatalogForeignKey, CatalogTable
from t2s.grounding.schema_retriever import tokenize_search_text
from t2s.grounding.value_grounding.candidate_column_selector import CandidateColumnSelector
from t2s.grounding.value_grounding.question_term_extractor import (
    QuestionTerm,
    QuestionTermExtractor,
    build_match_variants,
    normalize_term,
)
from t2s.grounding.value_grounding.value_grounding_budget import ValueGroundingBudget
from t2s.grounding.value_grounding.value_grounding_contracts import (
    ValueBindingCandidate,
    ValueGroundingDiagnostics,
    ValueGroundingResult,
    ValueMatchType,
    ValueProbeColumn,
    ValueProbeOutcome,
    ValueProbeRequest,
)
from t2s.grounding.value_grounding.value_probe_port import ValueProbePort

logger = structlog.get_logger(__name__)

# Minimum normalized similarity for a lexical binding within an enum-like domain.
LEXICAL_SIMILARITY_THRESHOLD = 0.82

_MATCH_TYPE_SCORES: dict[ValueMatchType, float] = {
    ValueMatchType.EXACT: 1.0,
    ValueMatchType.CASE_INSENSITIVE: 0.9,
    ValueMatchType.LEXICAL: 0.6,
}


class ValueGrounder:
    """Grounds question terms against literals stored in authorized columns."""

    def __init__(
        self,
        value_probe: ValueProbePort,
        budget: ValueGroundingBudget | None = None,
        candidate_column_selector: CandidateColumnSelector | None = None,
        question_term_extractor: QuestionTermExtractor | None = None,
    ) -> None:
        self.value_probe = value_probe
        self.budget = budget or ValueGroundingBudget()
        self.candidate_column_selector = candidate_column_selector or CandidateColumnSelector(
            self.budget
        )
        self.question_term_extractor = question_term_extractor or QuestionTermExtractor(self.budget)

    def ground_values(
        self,
        question: str,
        catalog_tables: Sequence[CatalogTable],
        selected_column_names_by_table_fqn: dict[str, set[str]],
        relationships: Sequence[CatalogForeignKey] = (),
    ) -> ValueGroundingResult:
        """Probe the most relevant authorized columns and return ranked bindings."""
        started_at = perf_counter()
        terms = self.question_term_extractor.extract_terms(question)
        if not terms:
            return ValueGroundingResult(
                diagnostics=ValueGroundingDiagnostics(
                    term_count=0,
                    skipped_reason="no_candidate_terms",
                    elapsed_ms=self._elapsed_ms(started_at),
                )
            )

        candidate_columns = self.candidate_column_selector.select_candidate_columns(
            catalog_tables=catalog_tables,
            selected_column_names_by_table_fqn=selected_column_names_by_table_fqn,
            relationships=relationships,
            question_tokens=tokenize_search_text(question),
        )
        if not candidate_columns:
            return ValueGroundingResult(
                diagnostics=ValueGroundingDiagnostics(
                    term_count=len(terms),
                    skipped_reason="no_candidate_columns",
                    elapsed_ms=self._elapsed_ms(started_at),
                )
            )

        match_terms = build_match_variants(terms)
        bindings: list[ValueBindingCandidate] = []
        error_messages: list[str] = []
        probe_count = 0
        probed_column_count = 0

        for candidate_column in candidate_columns:
            probe_request = ValueProbeRequest(
                column=candidate_column,
                match_terms=match_terms,
                max_values=self.budget.max_value_candidates_per_column,
                timeout_ms=self.budget.value_lookup_timeout_ms,
            )
            targeted_outcome = self._run_probe(
                self.value_probe.probe_matching_values, probe_request, error_messages
            )
            probe_count += targeted_outcome.probe_count
            probed_column_count += 1
            column_bindings = self._build_targeted_bindings(
                candidate_column, terms, targeted_outcome
            )

            if not column_bindings and self.budget.enumerate_low_cardinality_domains:
                domain_outcome = self._run_probe(
                    self.value_probe.probe_column_domain,
                    probe_request.model_copy(
                        update={"max_values": self.budget.max_enumerated_domain_values}
                    ),
                    error_messages,
                )
                probe_count += domain_outcome.probe_count
                column_bindings = self._build_lexical_bindings(
                    candidate_column, terms, domain_outcome
                )

            bindings.extend(column_bindings)

        ranked_bindings = self._rank_bindings(bindings)
        diagnostics = ValueGroundingDiagnostics(
            candidate_column_count=len(candidate_columns),
            probed_column_count=probed_column_count,
            probe_count=probe_count,
            binding_count=len(ranked_bindings),
            term_count=len(terms),
            elapsed_ms=self._elapsed_ms(started_at),
            error_messages=error_messages,
        )
        logger.debug(
            "value_grounding_completed",
            value_grounding_candidate_columns=len(candidate_columns),
            value_grounding_binding_count=len(ranked_bindings),
            value_grounding_probe_count=probe_count,
            value_grounding_duration_ms=diagnostics.elapsed_ms,
        )
        return ValueGroundingResult(bindings=ranked_bindings, diagnostics=diagnostics)

    def _run_probe(
        self,
        probe_callable: Callable[[ValueProbeRequest], ValueProbeOutcome],
        probe_request: ValueProbeRequest,
        error_messages: list[str],
    ) -> ValueProbeOutcome:
        """Invoke one probe, converting any adapter failure into an empty outcome."""
        try:
            outcome = probe_callable(probe_request)
        except Exception as exc:  # noqa: BLE001 - value evidence is always optional
            # Only the exception type is recorded: a database message can quote the
            # offending literal, which would leak column values into logs.
            error_messages.append(f"{probe_request.column.column_name}: {type(exc).__name__}")
            return ValueProbeOutcome(column=probe_request.column, probe_count=1)
        if outcome.error_message:
            error_messages.append(f"{probe_request.column.column_name}: {outcome.error_message}")
        return outcome

    def _build_targeted_bindings(
        self,
        candidate_column: ValueProbeColumn,
        terms: Sequence[QuestionTerm],
        outcome: ValueProbeOutcome,
    ) -> list[ValueBindingCandidate]:
        """Pair each returned literal with the term that produced it."""
        terms_by_normalized = {term.normalized: term for term in terms}
        bindings: list[ValueBindingCandidate] = []
        for observed_value in outcome.observed_values:
            matched_term = terms_by_normalized.get(normalize_term(observed_value))
            if matched_term is None:
                continue
            match_type = (
                ValueMatchType.EXACT
                if observed_value == matched_term.phrase
                else ValueMatchType.CASE_INSENSITIVE
            )
            bindings.append(
                ValueBindingCandidate(
                    table_fqn=candidate_column.table_fqn,
                    column_name=candidate_column.column_name,
                    phrase=matched_term.phrase,
                    # The database spelling is preserved verbatim so the solver can
                    # emit a literal that actually compares equal.
                    candidate_value=observed_value,
                    match_type=match_type,
                    evidence_score=_MATCH_TYPE_SCORES[match_type],
                )
            )
        return bindings

    def _build_lexical_bindings(
        self,
        candidate_column: ValueProbeColumn,
        terms: Sequence[QuestionTerm],
        outcome: ValueProbeOutcome,
    ) -> list[ValueBindingCandidate]:
        """Match terms against an enum-like domain by normalized similarity.

        A truncated domain means the column is high-cardinality, so its partial
        values are discarded rather than surfaced.
        """
        if outcome.domain_truncated or not outcome.observed_values:
            return []
        bindings: list[ValueBindingCandidate] = []
        for observed_value in outcome.observed_values:
            normalized_value = normalize_term(observed_value)
            best_term: QuestionTerm | None = None
            best_similarity = 0.0
            for term in terms:
                similarity = difflib.SequenceMatcher(
                    None, term.normalized, normalized_value
                ).ratio()
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_term = term
            if best_term is None or best_similarity < LEXICAL_SIMILARITY_THRESHOLD:
                continue
            bindings.append(
                ValueBindingCandidate(
                    table_fqn=candidate_column.table_fqn,
                    column_name=candidate_column.column_name,
                    phrase=best_term.phrase,
                    candidate_value=observed_value,
                    match_type=ValueMatchType.LEXICAL,
                    evidence_score=round(
                        _MATCH_TYPE_SCORES[ValueMatchType.LEXICAL] * best_similarity, 4
                    ),
                )
            )
        return bindings

    def _rank_bindings(
        self, bindings: Sequence[ValueBindingCandidate]
    ) -> list[ValueBindingCandidate]:
        """Deduplicate and order deterministically by strength, then by identity."""
        unique_bindings: dict[tuple[str, str, str], ValueBindingCandidate] = {}
        for binding in bindings:
            key = (binding.table_fqn, binding.column_name, binding.candidate_value)
            existing = unique_bindings.get(key)
            if existing is None or binding.evidence_score > existing.evidence_score:
                unique_bindings[key] = binding
        ordered = sorted(
            unique_bindings.values(),
            key=lambda binding: (
                -binding.evidence_score,
                binding.table_fqn,
                binding.column_name,
                binding.candidate_value,
            ),
        )
        return ordered[: self.budget.max_bindings]

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 3)
