# 04 — Grounding Engine: MG0 → MG*

**Version:** 2.0

---

## 1. Objective

The Grounding Engine exists to construct the best legitimate context for the solver without encoding the answer plan.

Allowed grounding facts include:

- table/column schema,
- descriptions,
- PK/FK,
- relationship evidence,
- legitimate value evidence,
- grain/cardinality,
- temporal semantics,
- business definitions,
- provenance/confidence.

Forbidden grounding includes:

- gold SQL,
- expected result,
- question-specific operation sequence,
- “use CTE”, “use AVG”, “join A to B”,
- benchmark-specific hints.

---

## 2. MG0

Current deployable MG0:

```text
SchemaRetriever
→ RelationshipExpander
→ GroundingBudget
→ S0 Serializer
```

MG0 is the baseline against which future capabilities should be tested.

---

## 3. MG*

MG* is **not** “maximum amount of context”.

MG* means:

> Maximum Deployable Grounding composed only of capabilities that have passed controlled evaluation and certification.

Desired qualities:

- high relevant-fact recall,
- low redundancy,
- correct semantics,
- explicit provenance,
- bounded prompt size,
- stable behavior,
- compatible with security policy.

---

## 4. Capability registry

| Capability | Current state | Default | Evidence | Certification gate |
|---|---|---:|---|---|
| SchemaRetriever | implemented | ON | VERIFIED existence | regression tests |
| RelationshipExpander | implemented | ON | VERIFIED existence | baseline retention |
| GroundingBudget | implemented | ON | VERIFIED existence | budget regression tests |
| S0 Serializer | implemented | ON | VERIFIED | baseline |
| Temporal Grounding | EXPERIMENTAL candidate | OFF | HYPOTHESIS based on P2-R2 error mass | unseen temporal challenge set + A–F audit |
| Value Grounding | not certified | OFF/SHADOW | HYPOTHESIS | isolated causal test |
| Grain/Cardinality | not certified | OFF | HYPOTHESIS | isolated causal test |
| Business Semantics | not certified | OFF | HYPOTHESIS | authoritative-source ablation |
| Intent/Output Contract | not certified | OFF | HYPOTHESIS | isolated test |
| Adaptive Probe | not certified | OFF | HYPOTHESIS | bounded-policy experiment |
| Query-history prior | optional | OFF | UNKNOWN | evidence of net benefit |

---

## 5. Capability lifecycle

```text
OFF
 ↓
EXPERIMENTAL
 ↓
SHADOW
 ↓
CERTIFIED
 ↓
PRODUCTION
```

No capability may skip the experimental evidence gate.

---

## 6. Temporal Grounding experiment candidate

Current P2-R2 MG error mass shows temporal logic as the largest remaining class.

Temporal Grounding must not be implemented as benchmark-specific logic.

### Legitimate temporal metadata

Examples:

```yaml
valid_from:
  meaning: start of business validity interval

valid_to:
  meaning: end of business validity interval
  boundary: inclusive

business_timestamp:
  meaning: event time used for reporting
```

A rule such as “intervals are guaranteed contiguous” may be supplied only if it is an authoritative database/business invariant.

### Unseen temporal challenge set

Before implementation, freeze an unseen set covering:

- effective-dated joins,
- inclusive/exclusive bounds,
- NULL open-ended validity,
- contiguous intervals,
- gapped intervals,
- overlapping intervals,
- latest-as-of semantics,
- event time vs business time,
- fiscal vs calendar semantics.

---

## 7. Future Value Grounding shape

Potential evidence hierarchy:

```text
1. authoritative dictionary
2. OpenMetadata/glossary mapping
3. profile/sample evidence
4. indexed distinct values
5. bounded read-only lookup
6. unresolved
```

Value Grounding must not silently convert benchmark evidence into production metadata.

---

## 8. Adaptive grounding

Adaptive grounding is allowed only when the system can identify a concrete evidence gap.

Examples:

```text
missing literal → value lookup
missing relationship → relationship expansion
ambiguous business term → glossary lookup
still unresolved → clarify / abstain
```

Not allowed:

```text
uncertain → generic LLM retry → generic LLM retry
```

---

## 9. MG* certification rule

MG* at any point is:

```text
MG* = MG0 + all CERTIFIED capabilities
```

Not:

```text
MG* = every plausible grounding feature
```

