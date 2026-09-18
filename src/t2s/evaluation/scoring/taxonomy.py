"""Canonical A-F semantic-audit taxonomy (E05 §5).

The taxonomy is *versioned* (:data:`t2s.evaluation.scoring.versions.TAXONOMY_VERSION`) and
must not be casually redefined. Categories:

======  =====================================================================
Grade   Meaning
======  =====================================================================
A       Exact, semantically correct.
B       Semantically correct with harmless output-contract variance.
C       Defensible ambiguity (question supports >1 reasonable reading).
D       True semantic error.
E       Lucky match: logically wrong SQL that matches the current fixture by
        accident.
F       Insufficient evidence to make a semantic determination.
======  =====================================================================

``F`` is a first-class outcome and always stays in the denominator (E05 §6).
Ambiguity (``C``) is *not* a synonym for uncertainty; uncertainty caused by
missing evidence is ``F`` (E05 §10).
"""

from __future__ import annotations

from enum import StrEnum


class Grade(StrEnum):
    """Top-level semantic grade. See module docstring."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class BSubtype(StrEnum):
    """Harmless-variance subtypes for grade B (E05 §5)."""

    B1_EXTRA_COLUMNS = "B1"  # harmless extra output columns
    B2_COLUMN_ORDER = "B2"  # harmless column-order variance
    B3_LABEL_EQUIVALENT = "B3"  # equivalent identifier / label representation
    B4_ROW_ORDER = "B4"  # row-ordering variance when order was not required
    B5_EQUIVALENT_FORM = "B5"  # equivalent SQL formulation / presentation


class RootCause(StrEnum):
    """Root-cause hypothesis, kept SEPARATE from the semantic grade (E05 §16).

    A ``D`` case is not automatically a grounding failure; a grade may legally
    carry ``root_cause = UNKNOWN``.
    """

    GROUNDING = "grounding"
    TEMPORAL = "temporal"
    VALUE = "value"
    GRAIN = "grain"
    JOIN = "join"
    SOLVER_REASONING = "solver_reasoning"
    SYNTAX = "syntax"
    OUTPUT_CONTRACT = "output_contract"
    AMBIGUITY = "ambiguity"
    EVALUATOR_DEFECT = "evaluator_defect"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


#: Grades that count as "production semantic safe" (A+B) — E05 §6.
SEMANTIC_SAFE_GRADES: frozenset[Grade] = frozenset({Grade.A, Grade.B})

#: Grades that constitute an "audited" determination (A-E). F is explicitly
#: excluded because it is *not* a determination — it is absence of evidence.
AUDITED_GRADES: frozenset[Grade] = frozenset(
    {Grade.A, Grade.B, Grade.C, Grade.D, Grade.E}
)


def is_semantic_safe(grade: Grade) -> bool:
    """True for A/B (correct or harmlessly different)."""

    return grade in SEMANTIC_SAFE_GRADES
