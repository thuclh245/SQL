# E05 — Scoring, Grading & Semantic Audit Framework Certification

**Phase:** E05 (scorer certification — *not* the frozen baseline; that is E06).
**Branch:** `eval/e05-scoring`
**Source commit (base):** `4a4cc44`
**Scorer version:** `e05.scorer.v1` · **Taxonomy:** `e05.taxonomy.v1` ·
**Equivalence rules:** `e05.equivalence.v1` · **Metrics:** `e05.metrics.v1` ·
**Aggregation:** `e05.aggregation.v1`

---

## 1. Purpose and non-goals

This phase redesigns **how results are graded**. It does **not** change model
behaviour, prompts, grounding, the solver, retries, validation, or benchmark
fixtures. The framework is strictly downstream of stored/governed case evidence.

Strict Execution Accuracy (EX) remains available and unchanged. It is no longer
the *only* truth source: the framework additionally distinguishes output-contract
variance, semantic correctness, defensible ambiguity, true error, lucky matches,
and insufficient evidence.

The most important rule is honoured throughout: **the scorer is not allowed to
make the system look better; its job is to tell the truth** and to preserve
uncertainty rather than hide it.

## 2. Where the code lives

| Concern | Location |
| --- | --- |
| E05 framework (evaluation tooling) | `src/t2s/evaluation/scoring/` |
| Synthetic + falsification + mutation + integration tests | `tests/unit/scoring/` |
| Artifact / old-vs-new audit builder | `scripts/e05/build_e05_artifacts.py` |
| Manifests + certification evidence | `results/e05/` |

The package sits under the `t2s.evaluation` namespace deliberately: it consumes
gold and imports `t2s.benchmark.scoring`, which the architecture and security
governance guards forbid for *production* modules. Placing it in the evaluation
namespace both passes those guards and states the architectural truth — this is
evaluation tooling, never runtime.

## 3. Architecture (three layers, never one number)

* **Layer 1 — deterministic / mechanical** (`deterministic.py`, `equivalence.py`).
  Execution status, strict EX (tri-state), result equivalence with recorded
  relaxations, fingerprint match, shape checks, and determination blockers.
* **Layer 2 — structured semantic audit** (`semantic_audit.py`, `taxonomy.py`,
  `lucky_match.py`). The A–F grade with B1–B5 subtypes, root-cause (kept separate
  from grade), two-independent-reviewer support, and an advisory-only LLM contract.
* **Layer 3 — aggregation** (`aggregation.py`). Case-clustered, replicate-aware,
  uncertainty-aware metrics with explicit numerators and denominators.

The three layers are surfaced as three record types — `ScoringRecord`,
`SemanticAuditRecord`, and `AggregateMetrics` — and are never collapsed.

## 4. E04 boundary (parallel track)

E04 owns `CaseRunRecord` / evidence capture. E05 consumes it through a **minimal
stable protocol**, `CaseRunEvidence` (version `e05.case_evidence.v1`), plus a
concrete fallback (`CaseEvidence`) and an adapter for the current runner dict.
E05 does **not** duplicate or redefine the case schema.

E04's in-progress `CaseRunRecord` already declares that it structurally satisfies
this protocol and pins the same `e05.case_evidence.v1` version string. The
integration is verified by `tests/unit/scoring/test_e04_integration.py`, which
scores a real `CaseRunRecord` directly (skipping cleanly when the E04 package is
absent). No E04 file was modified by this phase.

## 5. Canonical taxonomy (unchanged, versioned)

`A` exact-correct · `B` correct with harmless contract variance
(`B1` extra columns, `B2` column order, `B3` explicit label/id equivalence,
`B4` row order when not required, `B5` equivalent SQL form) · `C` defensible
ambiguity · `D` true semantic error · `E` lucky match · `F` insufficient
evidence.

Grade and **root cause** are independent: a `D` may carry `root_cause = UNKNOWN`.

## 6. Historical failures explicitly guarded against

1. **Missing candidate SQL → silent exclusion.** Now `determination_blockers`
   forces grade **F** (a first-class, in-denominator outcome), never a drop.
2. **Pooled replicate statistics (300 = 100×3).** `assert_not_pooled` refuses to
   treat replicates as independent; the primary unit is the **case**; uncertainty
   uses a **case-cluster bootstrap**; arm comparison is **paired by case**, and
   unclustered replicate-level McNemar is explicitly prohibited.
3. **Invalid oracle / substring matching.** No substring "oracle ceiling" exists;
   equivalence is value- and contract-based with explicit, tested rules.
4. **Execution equivalence rewarding wrong SQL.** Grade **E** with evidence-gated
   lucky-match detection (counterexample on a governed alternate fixture).
5. **Strict scorer penalizing harmless presentation.** Grade **B** subtypes.
6/7/8. Execution success ≠ semantic correctness; no ungrounded LLM judge; missing
   evidence never leaves the denominator — all enforced and tested.

## 7. Strict EX semantics (preserved, documented)

Strict EX delegates to the unchanged
`t2s.benchmark.scoring.score_execution_accuracy`: ordered iff the gold SQL has an
`ORDER BY`, else multiset comparison; NULL sentinel; `Decimal.normalize` numeric
handling; boolean `1/0`; duplicates significant; empty result compares equal to
empty; non-executing candidate ⇒ strict EX **undefined (None)**, never silently
`False`. Full contract in `results/e05/scorer_contract.json`.

## 8. Result equivalence (separate from strict EX)

Every relaxation is gated by an `OutputContract` and carries an explicit rule
(`results/e05/equivalence_rules_manifest.json`). Column mapping search is bounded
(≤ 8 candidate columns) and falls back safely. Label/id equivalence (B3) is
**never inferred** — it requires an explicit value-equivalence map.

## 9. Lucky-match detection (grade E)

`E` requires **both** a match on the primary fixture **and** proof of wrong logic
via counterexample divergence on a governed alternate fixture. A mere structural
difference is **insufficient** and yields `INSUFFICIENT` (auditor then picks F or
D), never E. Generic, evaluation-only mutation operators
(`mutation.py`) support counterexample testing.

## 10. Aggregate metrics (numerator/denominator, F retained)

`Strict EX`, `Audited Coverage = (A+B+C+D+E)/Total`,
`Production Semantic Safe = (A+B)/Total`,
`Conditional Safe = (A+B)/(A+B+C+D+E)`, `Ambiguity = C/Total`,
`True Error = D/Total`, `Lucky Match = E/Total`, `Unknown = F/Total`.
Every metric reports numerator and denominator; F is never removed from the
denominator (`results/e05/metric_definitions_manifest.json`).

Comparability between two arms is gated by `check_comparability`: any
non-treatment config difference marks the comparison **CONFOUNDED** and forbids a
causal claim (`results/e05/replicate_aggregation_manifest.json`).

## 11. Old-vs-new disagreement audit (governed sample)

Run on the governed, non-holdout `synthetic_solver_ceiling` benchmark (18 cases +
54 logic mutants over 4 real SQLite fixtures) plus generic lucky-match probes.
Disagreement matrix (`results/e05/old_vs_new_disagreement_manifest.json`):

| | new A | new B | new D | new E |
| --- | --- | --- | --- | --- |
| **old pass (strict)** | 18 | — | — | **1** |
| **old fail (strict)** | — | **18** | 54 | — |

The two valuable quadrants both appear:

* **old fail → new B (18):** harmless extra-column variance the strict scorer
  over-penalized.
* **old pass → new E (1):** a lucky match the strict scorer *rewarded*; the wrong
  logic is exposed on a governed alternate fixture.

The new scorer is **not** declared "better" for raising a score — it is declared
more truthful because these disagreements are inspected and explained.

## 12. Tests

`tests/unit/scoring/` (49 tests, all passing) certifies scorer *semantics*, not
benchmark accuracy: A, each of B1–B5, C-vs-F distinction, D, E (proven via
alternate fixture), F; generic SQL mutations caught; replicate-clustering and the
pooling guard; confounded-comparison detection; the full §25 falsification
checklist; and the E04 integration path. The full repository suite passes with no
regressions, including all architecture-hygiene and security-audit guards.

## 13. Independent self-review (E05 §25)

Each falsification attempt is encoded as a test and fails to break the scorer:
wrong-SQL-hidden-by-fixture → E; correct-with-harmless-columns → B not D; F cannot
leave the denominator; ambiguity ≠ missing evidence; order-sensitive not treated
insensitive; NULL/type coercion no false equivalence; replicates cannot be pooled;
structural difference alone never becomes E; advisory LLM never overrides
deterministic.

## 14. Verdict

**PASS_WITH_CONDITIONS.**

Conditions (both non-blocking, tracked in `results/e05/closure_manifest.json`):

1. E04's `CaseRunRecord` is not yet finalized; E05 consumes a minimal stable
   protocol + adapter and is verified against E04's current WIP record.
2. No stored *production* run currently persists candidate SQL + results, so the
   old-vs-new audit runs on the governed synthetic ceiling benchmark rather than a
   production replay. When E04 evidence capture lands in production runs, the same
   scorer applies unchanged.

Ready for E06 frozen baseline: **YES** (after E04 evidence capture is frozen).
