"""Extracts candidate literal terms from a question.

Deliberately language-neutral: no stopword list, no capitalisation rule and no
vocabulary. A term earns a binding only when the database actually stores it, so
precision comes from the probe rather than from filtering the question first.
"""

import re
import unicodedata
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from t2s.grounding.value_grounding.value_grounding_budget import ValueGroundingBudget

# Unicode-aware: \w covers non-Latin scripts, and the separator class keeps
# hyphenated and underscored labels together.
_WORD_PATTERN = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)
_QUOTED_PATTERN = re.compile(r"[\"'‘’“”]([^\"'‘’“”]{1,64})")


class QuestionTerm(BaseModel):
    """A phrase from the question and the form used for comparison."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    normalized: str


def normalize_term(value: str) -> str:
    """Casefold and collapse whitespace so comparison ignores case and spacing.

    Applied identically to question terms and to database literals, so a match is
    symmetric. The database's own spelling is always preserved separately.
    """
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


class QuestionTermExtractor:
    """Produces deduplicated candidate terms within the configured budget."""

    def __init__(self, budget: ValueGroundingBudget | None = None) -> None:
        self.budget = budget or ValueGroundingBudget()

    def extract_terms(self, question: str) -> list[QuestionTerm]:
        """Return quoted spans, single words and adjacent word pairs, in that order."""
        ordered_phrases: list[str] = []
        ordered_phrases.extend(match.strip() for match in _QUOTED_PATTERN.findall(question))

        words = _WORD_PATTERN.findall(question)
        ordered_phrases.extend(words)
        # Adjacent pairs let multi-word labels bind without a vocabulary.
        ordered_phrases.extend(
            f"{first} {second}" for first, second in zip(words, words[1:], strict=False)
        )

        terms: list[QuestionTerm] = []
        seen_normalized: set[str] = set()
        for phrase in ordered_phrases:
            if len(terms) >= self.budget.max_question_terms:
                break
            normalized = normalize_term(phrase)
            if not self._is_acceptable(normalized) or normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            terms.append(QuestionTerm(phrase=phrase.strip(), normalized=normalized))
        return terms

    def _is_acceptable(self, normalized_term: str) -> bool:
        return self.budget.min_term_length <= len(normalized_term) <= self.budget.max_term_length


def build_match_variants(terms: Sequence[QuestionTerm]) -> tuple[str, ...]:
    """Expand terms into the spellings an equality probe should test.

    Case folding happens here, in Python, rather than in SQL: it stays correct for
    non-Latin scripts regardless of database collation, and it leaves the probe as
    a plain equality predicate that an index can serve.
    """
    variants: list[str] = []
    seen: set[str] = set()
    for term in terms:
        for variant in (
            term.phrase,
            term.normalized,
            term.phrase.lower(),
            term.phrase.upper(),
            term.phrase.title(),
        ):
            if variant and variant not in seen:
                seen.add(variant)
                variants.append(variant)
    return tuple(variants)
