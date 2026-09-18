# 02 — Canonical Project State and Evidence

**Document role:** single scientific source of truth for project status, evidence, invalidated claims, and unknowns.  
**Version:** 2.0

---

## 1. Current project framing

T2S / CHATSQL is an **enterprise evidence-grounded Text-to-SQL system with bounded adaptive grounding and controlled SQL execution**.

The central engineering objective is:

> Given a natural-language question, automatically construct the highest-quality legitimate database context possible, then allow a fixed 120B-class solver to independently derive the SQL.

Grounding is responsible for **what is true about the data**. The solver is responsible for **what SQL should be written**.

---

## 2. Current deployable grounding state

Current deployable state is named **MG0**.

```text
MG0 =
SchemaRetriever
+ RelationshipExpander
+ GroundingBudget
+ S0 Serializer
```

The following are **not yet certified deployable capabilities**:

- Value Grounding
- Grain / Cardinality Grounding
- Temporal Grounding
- Business Semantic Grounding
- Intent / Output Contract Grounding
- Adaptive Evidence Probes
- Query-history-driven grounding

Some of these exist only in synthetic experimental contexts.

---

## 3. Canonical belief-state vocabulary

Every important project claim must have one state:

- **VERIFIED** — directly supported by code, runtime artifact, or completed audit.
- **SUPPORTED** — evidence is directionally meaningful but incomplete.
- **HYPOTHESIS** — technically plausible and testable, but not yet demonstrated.
- **UNKNOWN** — insufficient evidence.
- **INVALIDATED** — prior claim contradicted or made non-canonical by stronger evidence.

---

## 4. Evidence baseline

### 4.1 P0 — Runtime / Benchmark Parity

P0 established the governance principle that API and benchmark execution should use a common semantic runtime assembly and a machine-readable runtime profile.

What P0 supports:

- runtime parity is necessary for trustworthy evaluation,
- provider/model/prompt/runtime configuration must be frozen and inspectable,
- architecture guards are part of evaluation validity.

What P0 does **not** establish:

- solver accuracy,
- production semantic correctness,
- MG capability benefit.

### 4.2 P1 — Context and Serialization

Historical P1 experiment:

```text
100 cases
× 3 replicates
× 7 arms
= 2,100 runs
```

Strict execution observations:

| Arm | Strict EX |
|---|---:|
| C0 | 11.67% |
| C1 | 9.00% |
| C2 | 19.00% |
| S0 | 11.67% |
| S1 | 14.00% |
| S2 | 12.33% |
| S3 | 14.00% |

Canonical interpretation:

- These results are **directional strict-execution observations only**.
- Raw candidate SQL was not persisted.
- Therefore historical semantic reclassification is **BLOCKED**.
- The original pooled-replicate McNemar significance claim is invalid because three replicates of the same 100 cases are not 300 independent cases.

Current P1 evidence status:

- Context expansion: **SUPPORTED / UNVERIFIED SEMANTICALLY**.
- Serialization cleanup: **SUPPORTED / UNVERIFIED SEMANTICALLY**.

### 4.3 P2-R2 — Canonical Semantic Audit

P2-R2 audited all 162 runs using the canonical A–F taxonomy.

#### Canonical taxonomy

- **A** — exact semantically correct.
- **B** — semantically correct with harmless contract variance.
- **C** — defensible ambiguity.
- **D** — true semantic error.
- **E** — lucky match / logically wrong but current fixture matches.
- **F** — insufficient evidence.

#### P2-R2 canonical results

| Arm | A | B | C | D | E | F | Semantic Safe A+B |
|---|---:|---:|---:|---:|---:|---:|---:|
| FS | 5 | 6 | 0 | 42 | 1 | 0 | 20.37% |
| MG | 21 | 25 | 0 | 8 | 0 | 0 | 85.19% |
| OR | 15 | 20 | 0 | 19 | 0 | 0 | 64.81% |

The only approved wording for MG is:

> MG achieved **85.19% Production Semantic Safe Rate on the fully audited 18-case synthetic hard-query cohort**.

This is **not** enterprise production accuracy.

### 4.4 Current MG remaining error mass

Across 54 MG runs:

| Error class | Count | Share of MG errors |
|---|---:|---:|
| D_TEMPORAL_LOGIC | 3 | 37.5% |
| D_FILTER_LITERAL | 2 | 25.0% |
| D_SQL_SYNTAX | 1 | 12.5% |
| D_DENOMINATOR | 1 | 12.5% |
| D_RELATIONAL_LOGIC | 1 | 12.5% |

Temporal Grounding is therefore the **leading next experiment candidate**, not a certified capability.

---

## 5. Current OR status

Current OR is **INVALID as a solver ceiling** because it:

1. removed `time_semantics` that MG had,
2. selected tables using naive substring matching against gold SQL,
3. therefore changed more than relevance selection.

Future **OR\*** must be:

```text
same evidence types as MG*
+
oracle-perfect relevance selection
```

No additional solution hint is permitted.

---

## 6. Current belief state

### VERIFIED

- MG0 current deployable composition.
- P1 candidate-SQL persistence failure.
- P1 semantic re-audit blockage.
- P2-R2 A–F counts.
- Current OR defect.
- Candidate SQL persistence is a mandatory evaluation invariant.
- ResultVerifier, SqlRiskController, and ValidatorMode are distinct governance concepts.
- Only PostgreSQL and SQLite have implemented read-only query executors; ClickHouse and StarRocks have no executor implementation and fail closed at configuration time.
- OpenMetadataProvider exists as implemented code but is **not** the default metadata provider; it requires explicit `metadata_provider=openmetadata` configuration (default is `static`/`postgres`). See `07`.
- No n8n integration code exists in the repository. n8n is currently an assumed external caller only, not an implemented component. See `08`.

### SUPPORTED

- MG is a strong direction for further development.
- Better legitimate grounding may materially improve a fixed 120B solver.
- Temporal Grounding is the next capability worth isolating experimentally.

### HYPOTHESIS

- Temporal Grounding will reduce temporal semantic errors.
- Value Grounding will reduce literal/value failures.
- Grain/Cardinality evidence will reduce fan-out and denominator errors.
- Intent/Output Contract Grounding will reduce projection/contract mismatches.
- Adaptive probes can improve evidence completeness without uncontrolled agent loops.

### UNKNOWN

- True company-production semantic accuracy.
- Generalization to unseen enterprise domains.
- Large-catalog behavior.
- Correctness/behavior of a future ClickHouse or StarRocks executor once implemented (their non-existence today is VERIFIED, not unknown).
- Real OpenMetadata metadata quality and freshness.
- Conditional solver ceiling of gpt-oss-120b.
- Final MG* → OR* gap.

### INVALIDATED

- Pre-P2-R2 informal 83.3% / 85.2% estimates as canonical metrics.
- Current OR as solver ceiling.
- Pooled-replicate P1 significance.
- Claims that P1 semantically proved C2/S1/S3.
- Any wording that treats 85.19% as production accuracy.

---

## 7. Tier-1 project invariants

1. No benchmark-specific runtime logic.
2. No gold SQL in production prompts or metadata.
3. No semantic conclusion without candidate SQL persistence.
4. No architecture promotion from one metric.
5. No capability becomes production by architectural plausibility alone.
6. No duplicate Text-to-SQL stack inside n8n.
7. OpenMetadata remains metadata source of truth.
8. Metadata visibility does not imply DB authorization.
9. Unknown remains unknown.
10. Replicates are clustered by case for statistical interpretation.

---

## 8. Immediate project state

```text
CURRENT:
MG0 + canonical P2-R2 evidence

NEXT:
Temporal Grounding isolated certification experiment

THEN:
Recompute A–F error mass
→ select next capability
→ certify or reject

FUTURE:
MG*
→ OR*
→ solver ceiling
→ scale/generalization
→ enterprise pilot
```

