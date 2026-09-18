# 05 — Evaluation, Experiment and Certification Protocol

**Version:** 2.0

---

## 1. Why evaluation is a subsystem

Text-to-SQL can produce executable SQL that is semantically wrong. Therefore evaluation must preserve enough evidence to reconstruct every decision.

---

## 2. Canonical A–F taxonomy

- **A — Exact semantically correct**
- **B — Semantically correct, harmless contract variance**
- **C — Defensible ambiguity**
- **D — True semantic error**
- **E — Lucky match / false positive**
- **F — Insufficient evidence**

Suggested B subtypes:

- B1 extra harmless columns
- B2 column order only
- B3 equivalent identifier/label
- B4 row order only when order not requested
- B5 equivalent SQL formulation

---

## 3. Canonical metrics

```text
Strict EX

Audited Coverage
= (A+B+C+D+E) / Total

Production Semantic Safe Rate
= (A+B) / Total

Conditional Semantic Safe Rate
= (A+B) / (A+B+C+D+E)

Ambiguity Rate
= C / Total

True Error Rate
= D / Total

Lucky Match Rate
= E / Total

Unknown Rate
= F / Total
```

Never silently drop F from the primary denominator.

---

## 4. Mandatory persisted artifacts

Every evaluation run must persist:

- case/question,
- final grounding context,
- context provenance,
- candidate SQL,
- provider/model/config,
- solver assumptions if available,
- unresolved information if available,
- AST summary,
- candidate result fingerprint,
- gold result fingerprint,
- execution status,
- strict score,
- semantic classification,
- latency,
- verifier/risk outputs.

If candidate SQL is missing:

```text
SEMANTIC_AUDIT = GOVERNANCE_INVALID
```

---

## 5. Statistical governance

Replicates of the same case are correlated.

Do not treat:

```text
100 cases × 3 replicates
```

as 300 independent samples.

Use one or more of:

- case-level majority/aggregation,
- clustered bootstrap by case,
- justified repeated-measure models.

Pooled-replicate McNemar must not be the primary proof.

---

## 6. Lucky-match testing

A strict-positive run can still be logically wrong.

Where suspicion exists, perform controlled counterexample testing using temporary cloned fixtures.

Mutation examples:

- add cancelled/status-negative rows,
- add boundary-date rows,
- introduce 1:N multiplicity,
- add tied ranks,
- add NULLs,
- add overlapping/gapped temporal intervals.

Mutations must never modify canonical benchmark DBs.

---

## 7. Capability experiment pattern

For each new capability:

```text
CONTROL = certified baseline without capability
TREATMENT = same baseline + exactly one capability
```

Freeze:

- model,
- provider,
- temperature,
- prompt contract,
- dataset,
- DB fixture,
- retrieval baseline,
- serializer,
- execution policy,
- scorer.

Only one causal variable changes.

---

## 8. Certification decision

A capability can advance only if:

1. semantic-safe performance improves or reliability materially improves,
2. no unacceptable regression occurs,
3. lucky-match rate does not increase unacceptably,
4. security and governance are unchanged or improved,
5. behavior is stable across replicates/cases,
6. artifacts are complete.

Possible outcomes:

- CERTIFY
- KEEP_SHADOW
- REJECT
- INCONCLUSIVE

---

## 9. Holdout governance

- Holdout remains immutable.
- No holdout-specific metadata enrichment.
- No benchmark-specific runtime rules.
- Any defect in holdout/gold is handled via versioned exclusion/quarantine manifest, not silent mutation.

---

## 10. Current next experiment

Temporal Grounding is the next supported candidate.

It remains OFF in production until isolated certification succeeds.

