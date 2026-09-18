"""Version constants for the E05 scoring framework.

A score without a scorer version is incomplete evidence (E05 §19). Every
:class:`ScoringRecord` / :class:`SemanticAuditRecord` / aggregate carries these
identifiers so a stored result can always be traced to the exact rules that
produced it. Changing any rule set requires bumping the matching constant and
either a full rescore or an explicit old/new side-by-side comparison.
"""

from __future__ import annotations

from typing import Final

#: Bump when the deterministic Layer-1 scoring behaviour changes.
SCORER_VERSION: Final[str] = "e05.scorer.v1"

#: Bump when the A-F / B1-B5 / root-cause taxonomy changes (E05 §5).
TAXONOMY_VERSION: Final[str] = "e05.taxonomy.v1"

#: Bump when a result-equivalence relaxation rule is added/changed (E05 §8).
EQUIVALENCE_RULES_VERSION: Final[str] = "e05.equivalence.v1"

#: Bump when an aggregate metric definition changes (E05 §6, §17).
METRIC_DEFINITIONS_VERSION: Final[str] = "e05.metrics.v1"

#: Bump when replicate-aware aggregation behaviour changes (E05 §17).
AGGREGATION_VERSION: Final[str] = "e05.aggregation.v1"

#: Minimal E04 CaseRunRecord contract this framework consumes (E05 §1).
#: Increment when the consumed protocol surface changes.
CONSUMED_CASE_RECORD_PROTOCOL_VERSION: Final[str] = "e05.case_evidence.v1"


def version_manifest() -> dict[str, str]:
    """Return every version identifier as a flat mapping for manifests."""

    return {
        "scorer_version": SCORER_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "equivalence_rules_version": EQUIVALENCE_RULES_VERSION,
        "metric_definitions_version": METRIC_DEFINITIONS_VERSION,
        "aggregation_version": AGGREGATION_VERSION,
        "consumed_case_record_protocol_version": CONSUMED_CASE_RECORD_PROTOCOL_VERSION,
    }
