"""Layer 3 - replicate-aware aggregate metrics (E05 §6, §17, §18).

Two hard rules shape this module:

1. **F stays in the denominator** (E05 §6). Every metric reports an explicit
   numerator and denominator; "accuracy after silently dropping F" is not
   expressible here.
2. **Replicates are never pooled as independent observations** (E05 §2, §17).
   The primary unit is the CASE. Per-replicate figures are computed but labelled
   as such and carry a warning; case-level figures cluster replicates within a
   case. A deliberately-named guard, :func:`assert_not_pooled`, exists so callers
   cannot accidentally treat ``replicates x cases`` as one flat sample.

Comparisons between two experiment arms are gated by a comparability contract
(E05 §18); when configs differ on anything but the declared treatment the
comparison is marked ``CONFOUNDED`` and no causal claim is produced.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from t2s.evaluation.scoring.records import SemanticAuditRecord
from t2s.evaluation.scoring.taxonomy import Grade
from t2s.evaluation.scoring.versions import AGGREGATION_VERSION, METRIC_DEFINITIONS_VERSION

#: Tie-break order for a case's dominant grade: least-optimistic first, so a
#: tie never inflates the safe rate.
_PESSIMISM_ORDER = [Grade.D, Grade.E, Grade.F, Grade.C, Grade.B, Grade.A]


@dataclass(frozen=True)
class Ratio:
    """A metric as an explicit numerator/denominator pair (E05 §6)."""

    numerator: float
    denominator: int

    @property
    def value(self) -> float | None:
        if self.denominator == 0:
            return None
        return round(self.numerator / self.denominator, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
        }


@dataclass
class GradeMetrics:
    """The E05 §6 metric family over a flat list of grades (one per unit)."""

    unit: str  # "replicate" or "case"
    total: int
    counts: dict[str, int]
    strict_ex: Ratio
    audited_coverage: Ratio
    production_semantic_safe: Ratio
    conditional_safe: Ratio
    ambiguity: Ratio
    true_error: Ratio
    lucky_match: Ratio
    unknown: Ratio
    warnings: tuple[str, ...] = ()
    metric_definitions_version: str = METRIC_DEFINITIONS_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "total": self.total,
            "counts": self.counts,
            "metric_definitions_version": self.metric_definitions_version,
            "warnings": list(self.warnings),
            "metrics": {
                "strict_ex": self.strict_ex.to_dict(),
                "audited_coverage": self.audited_coverage.to_dict(),
                "production_semantic_safe": self.production_semantic_safe.to_dict(),
                "conditional_safe": self.conditional_safe.to_dict(),
                "ambiguity": self.ambiguity.to_dict(),
                "true_error": self.true_error.to_dict(),
                "lucky_match": self.lucky_match.to_dict(),
                "unknown": self.unknown.to_dict(),
            },
        }


def _grade_metrics_from_grades(
    grades: list[Grade],
    strict_ex_flags: list[bool | None],
    *,
    unit: str,
    warnings: tuple[str, ...] = (),
) -> GradeMetrics:
    total = len(grades)
    counts = Counter(g.value for g in grades)
    a = counts.get("A", 0)
    b = counts.get("B", 0)
    c = counts.get("C", 0)
    d = counts.get("D", 0)
    e = counts.get("E", 0)
    f = counts.get("F", 0)
    audited = a + b + c + d + e
    strict_correct = sum(1 for flag in strict_ex_flags if flag is True)
    strict_denom = sum(1 for flag in strict_ex_flags if flag is not None)
    return GradeMetrics(
        unit=unit,
        total=total,
        counts={g: counts.get(g, 0) for g in ("A", "B", "C", "D", "E", "F")},
        strict_ex=Ratio(strict_correct, strict_denom),
        audited_coverage=Ratio(audited, total),
        production_semantic_safe=Ratio(a + b, total),
        conditional_safe=Ratio(a + b, audited),
        ambiguity=Ratio(c, total),
        true_error=Ratio(d, total),
        lucky_match=Ratio(e, total),
        unknown=Ratio(f, total),
        warnings=warnings,
    )


def replicate_level_metrics(records: list[SemanticAuditRecord]) -> GradeMetrics:
    """Metrics treating each replicate as one unit.

    WARNING (E05 §17): these figures must NOT be fed into any test that assumes
    independent observations; replicates of the same case are correlated. Use
    :func:`case_level_metrics` for the primary reporting unit.
    """

    grades = [r.classification for r in records]
    strict = [r.strict_ex for r in records]
    return _grade_metrics_from_grades(
        grades,
        strict,
        unit="replicate",
        warnings=(
            "replicate-level: NOT independent observations; do not pool for "
            "significance testing (E05 §2, §17).",
        ),
    )


@dataclass(frozen=True)
class CaseOutcome:
    """One case's grades across its replicates (the clustering unit)."""

    case_id: str
    replicate_grades: tuple[Grade, ...]
    replicate_strict_ex: tuple[bool | None, ...]

    @property
    def dominant_grade(self) -> Grade:
        counts = Counter(self.replicate_grades)
        best = max(counts.values())
        tied = [g for g, n in counts.items() if n == best]
        for grade in _PESSIMISM_ORDER:
            if grade in tied:
                return grade
        return tied[0]

    @property
    def stable(self) -> bool:
        return len(set(self.replicate_grades)) == 1


def build_case_outcomes(records: list[SemanticAuditRecord]) -> list[CaseOutcome]:
    """Cluster replicate records by case (E05 §17)."""

    by_case: dict[str, list[SemanticAuditRecord]] = {}
    for record in records:
        by_case.setdefault(record.case_id, []).append(record)
    outcomes: list[CaseOutcome] = []
    for case_id in sorted(by_case):
        case_records = by_case[case_id]
        outcomes.append(
            CaseOutcome(
                case_id=case_id,
                replicate_grades=tuple(r.classification for r in case_records),
                replicate_strict_ex=tuple(r.strict_ex for r in case_records),
            )
        )
    return outcomes


def case_level_metrics(records: list[SemanticAuditRecord]) -> GradeMetrics:
    """Primary metrics: one dominant grade per case (E05 §17).

    Each case contributes exactly one grade (its dominant grade across
    replicates, tie-broken pessimistically), so the denominator is the number of
    CASES, never replicates x cases.
    """

    outcomes = build_case_outcomes(records)
    grades = [o.dominant_grade for o in outcomes]
    # A case's strict_ex flag: True only if the majority of replicates strictly
    # pass; None if none are determinable.
    strict: list[bool | None] = []
    for outcome in outcomes:
        determinable = [f for f in outcome.replicate_strict_ex if f is not None]
        if not determinable:
            strict.append(None)
        else:
            strict.append(sum(determinable) * 2 >= len(determinable))
    return _grade_metrics_from_grades(grades, strict, unit="case")


def case_outcome_distribution(records: list[SemanticAuditRecord]) -> dict[str, Any]:
    """Per-case grade distribution and stability (E05 §17 'outcome distribution')."""

    outcomes = build_case_outcomes(records)
    stable = sum(1 for o in outcomes if o.stable)
    return {
        "case_count": len(outcomes),
        "stable_cases": stable,
        "unstable_cases": len(outcomes) - stable,
        "stability_rate": round(stable / len(outcomes), 4) if outcomes else 0.0,
        "per_case": [
            {
                "case_id": o.case_id,
                "grades": [g.value for g in o.replicate_grades],
                "dominant": o.dominant_grade.value,
                "stable": o.stable,
            }
            for o in outcomes
        ],
    }


def assert_not_pooled(records: list[SemanticAuditRecord]) -> None:
    """Guard: refuse to proceed if replicates would be pooled as independent.

    Raises when the same (case_id) appears under multiple replicate_ids and the
    caller has not clustered — a tripwire so historical failure #2 (300 trials
    treated as independent, E05 §2) cannot silently recur. Callers doing legit
    replicate-level reporting call :func:`replicate_level_metrics` directly, which
    documents the non-independence in its warnings.
    """

    seen: dict[str, set[str]] = {}
    for record in records:
        seen.setdefault(record.case_id, set()).add(record.replicate_id)
    multi = {cid: reps for cid, reps in seen.items() if len(reps) > 1}
    if multi:
        raise ValueError(
            "Refusing to pool replicates as independent observations "
            f"({len(multi)} cases have multiple replicates). Cluster by case via "
            "case_level_metrics() or explicitly use replicate_level_metrics()."
        )


# ---------------------------------------------------------------------------
# Clustered uncertainty (case cluster bootstrap) - E05 §17
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapCI:
    metric: str
    point: float | None
    ci_low: float | None
    ci_high: float | None
    resamples: int
    method: str = "case-cluster-bootstrap"


def _semantic_safe_rate_over_cases(outcomes: list[CaseOutcome]) -> float | None:
    if not outcomes:
        return None
    safe = sum(1 for o in outcomes if o.dominant_grade in (Grade.A, Grade.B))
    return safe / len(outcomes)


def case_cluster_bootstrap_safe_rate(
    records: list[SemanticAuditRecord],
    *,
    resamples: int = 2000,
    seed: int = 12345,
) -> BootstrapCI:
    """95% CI for the case-level semantic-safe rate via a case cluster bootstrap.

    Cases (not replicates) are the resampling unit, so correlated replicates
    within a case never inflate precision (E05 §17). Deterministic given the seed.
    """

    outcomes = build_case_outcomes(records)
    point = _semantic_safe_rate_over_cases(outcomes)
    if not outcomes or point is None:
        return BootstrapCI("production_semantic_safe", point, None, None, 0)
    rng = random.Random(seed)
    n = len(outcomes)
    estimates: list[float] = []
    for _ in range(resamples):
        sample = [outcomes[rng.randrange(n)] for _ in range(n)]
        rate = _semantic_safe_rate_over_cases(sample)
        if rate is not None:
            estimates.append(rate)
    estimates.sort()
    lo = estimates[int(0.025 * len(estimates))]
    hi = estimates[min(len(estimates) - 1, int(0.975 * len(estimates)))]
    return BootstrapCI(
        metric="production_semantic_safe",
        point=round(point, 4),
        ci_low=round(lo, 4),
        ci_high=round(hi, 4),
        resamples=len(estimates),
    )


# ---------------------------------------------------------------------------
# Paired case-level comparison of two arms (E05 §17, §18)
# ---------------------------------------------------------------------------


@dataclass
class PairedCaseComparison:
    """Case-clustered paired comparison of two arms on a semantic-safe outcome."""

    paired_cases: int
    both_safe: int
    only_a_safe: int
    only_b_safe: int
    neither_safe: int
    #: Discordant pairs (b, c) as in a paired 2x2 table, at the CASE level.
    discordant_a_only: int
    discordant_b_only: int
    note: str = (
        "Case-level discordances. Do NOT apply an unclustered McNemar test to "
        "replicate rows; that pools correlated replicates and inflates "
        "significance (E05 §2)."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "paired_cases": self.paired_cases,
            "both_safe": self.both_safe,
            "only_a_safe": self.only_a_safe,
            "only_b_safe": self.only_b_safe,
            "neither_safe": self.neither_safe,
            "discordant_a_only": self.discordant_a_only,
            "discordant_b_only": self.discordant_b_only,
            "note": self.note,
        }


def paired_case_comparison(
    arm_a: list[SemanticAuditRecord],
    arm_b: list[SemanticAuditRecord],
) -> PairedCaseComparison:
    """Pair two arms BY CASE (not by replicate) on the A/B-safe outcome."""

    a_outcomes = {o.case_id: o for o in build_case_outcomes(arm_a)}
    b_outcomes = {o.case_id: o for o in build_case_outcomes(arm_b)}
    shared = sorted(set(a_outcomes) & set(b_outcomes))

    def _safe(outcome: CaseOutcome) -> bool:
        return outcome.dominant_grade in (Grade.A, Grade.B)

    both = only_a = only_b = neither = 0
    for case_id in shared:
        sa = _safe(a_outcomes[case_id])
        sb = _safe(b_outcomes[case_id])
        if sa and sb:
            both += 1
        elif sa and not sb:
            only_a += 1
        elif sb and not sa:
            only_b += 1
        else:
            neither += 1
    return PairedCaseComparison(
        paired_cases=len(shared),
        both_safe=both,
        only_a_safe=only_a,
        only_b_safe=only_b,
        neither_safe=neither,
        discordant_a_only=only_a,
        discordant_b_only=only_b,
    )


# ---------------------------------------------------------------------------
# Comparability / confounding contract (E05 §18)
# ---------------------------------------------------------------------------

COMPARABILITY_KEYS = (
    "dataset_cases",
    "split",
    "db_fixture",
    "model",
    "temperature",
    "retry_policy",
    "prompt_base",
    "grounding_base",
    "scorer_version",
    "execution_environment",
)


@dataclass
class ComparabilityResult:
    comparable: bool
    status: str  # "COMPARABLE" or "CONFOUNDED"
    treatment_vars: tuple[str, ...]
    differing_keys: tuple[str, ...]
    unexpected_differences: tuple[str, ...]
    causal_claim_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparable": self.comparable,
            "status": self.status,
            "treatment_vars": list(self.treatment_vars),
            "differing_keys": list(self.differing_keys),
            "unexpected_differences": list(self.unexpected_differences),
            "causal_claim_allowed": self.causal_claim_allowed,
        }


def check_comparability(
    config_a: dict[str, Any],
    config_b: dict[str, Any],
    *,
    treatment_vars: tuple[str, ...] = (),
) -> ComparabilityResult:
    """Decide whether two arms are directly comparable (E05 §18).

    Any key in :data:`COMPARABILITY_KEYS` that differs AND is not a declared
    treatment variable makes the comparison ``CONFOUNDED`` and forbids a causal
    claim. Declared treatments are allowed to differ (that is the point).
    """

    differing: list[str] = []
    for key in COMPARABILITY_KEYS:
        if config_a.get(key) != config_b.get(key):
            differing.append(key)
    unexpected = tuple(k for k in differing if k not in treatment_vars)
    confounded = len(unexpected) > 0
    return ComparabilityResult(
        comparable=not confounded,
        status="CONFOUNDED" if confounded else "COMPARABLE",
        treatment_vars=treatment_vars,
        differing_keys=tuple(differing),
        unexpected_differences=unexpected,
        causal_claim_allowed=not confounded,
    )


@dataclass
class AggregateMetrics:
    """Bundle of all Layer-3 outputs for one arm (E05 §4 Layer 3)."""

    aggregation_version: str
    replicate: GradeMetrics
    case: GradeMetrics
    distribution: dict[str, Any]
    safe_rate_ci: BootstrapCI
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregation_version": self.aggregation_version,
            "replicate_level": self.replicate.to_dict(),
            "case_level": self.case.to_dict(),
            "case_outcome_distribution": self.distribution,
            "production_semantic_safe_ci": {
                "metric": self.safe_rate_ci.metric,
                "point": self.safe_rate_ci.point,
                "ci_low": self.safe_rate_ci.ci_low,
                "ci_high": self.safe_rate_ci.ci_high,
                "resamples": self.safe_rate_ci.resamples,
                "method": self.safe_rate_ci.method,
            },
            "warnings": self.warnings,
        }


def aggregate(records: list[SemanticAuditRecord]) -> AggregateMetrics:
    """Compute the full Layer-3 aggregate for one arm's records."""

    return AggregateMetrics(
        aggregation_version=AGGREGATION_VERSION,
        replicate=replicate_level_metrics(records),
        case=case_level_metrics(records),
        distribution=case_outcome_distribution(records),
        safe_rate_ci=case_cluster_bootstrap_safe_rate(records),
        warnings=[
            "Primary unit is the CASE. Replicate-level figures are correlated and "
            "must not be pooled as independent observations (E05 §2, §17).",
        ],
    )
