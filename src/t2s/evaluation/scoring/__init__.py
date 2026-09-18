"""E05 scoring, grading & semantic-audit framework.

A trustworthy, layered scorer that distinguishes deterministic execution
correctness from output-contract variance, semantic correctness, ambiguity,
true error, lucky matches and insufficient evidence. Strict execution accuracy
is preserved and remains available; it is no longer the only truth source.

Three layers, never collapsed into a single number (E05 §4):

* Layer 1 - :mod:`t2s.evaluation.scoring.deterministic` (mechanical, reproducible).
* Layer 2 - :mod:`t2s.evaluation.scoring.semantic_audit` (A-F structured audit).
* Layer 3 - :mod:`t2s.evaluation.scoring.aggregation` (case-clustered, uncertainty-aware).

This package is strictly downstream of stored case evidence and changes no
runtime behaviour (E05 §3).
"""

from __future__ import annotations

from t2s.evaluation.scoring.aggregation import (
    AggregateMetrics,
    aggregate,
    case_level_metrics,
    check_comparability,
    paired_case_comparison,
    replicate_level_metrics,
)
from t2s.evaluation.scoring.deterministic import compute_strict_ex, score_case_deterministic
from t2s.evaluation.scoring.equivalence import (
    OutputContract,
    compute_result_equivalence,
    equivalence_rules_manifest,
)
from t2s.evaluation.scoring.protocols import (
    CaseEvidence,
    CaseRunEvidence,
    ResultTable,
    case_evidence_from_runner_record,
)
from t2s.evaluation.scoring.records import ScoringRecord, SemanticAuditRecord
from t2s.evaluation.scoring.semantic_audit import (
    compute_disagreement,
    deterministic_semantic_audit,
    merge_reviews,
)
from t2s.evaluation.scoring.taxonomy import BSubtype, Grade, RootCause
from t2s.evaluation.scoring.versions import version_manifest

__all__ = [
    "AggregateMetrics",
    "BSubtype",
    "CaseEvidence",
    "CaseRunEvidence",
    "Grade",
    "OutputContract",
    "ResultTable",
    "RootCause",
    "ScoringRecord",
    "SemanticAuditRecord",
    "aggregate",
    "case_evidence_from_runner_record",
    "case_level_metrics",
    "check_comparability",
    "compute_disagreement",
    "compute_result_equivalence",
    "compute_strict_ex",
    "deterministic_semantic_audit",
    "equivalence_rules_manifest",
    "merge_reviews",
    "paired_case_comparison",
    "replicate_level_metrics",
    "score_case_deterministic",
    "version_manifest",
]
