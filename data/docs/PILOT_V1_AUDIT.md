# T2S Pilot v1 — Audit

## Verdict

**REVISE-BEFORE-FREEZE**, not because the 85 BIRD cases are unusable, but because the file currently mixes an executable benchmark with unfinished robustness slots and contains a curated-gold layer that needs an explicit provenance/review policy.

## Observed file state

The uploaded `t2s_pilot_v1.jsonl` contains exactly 100 records:

| Slice | Count | Current state |
|---|---:|---|
| S1 | 20 | executable BIRD cases |
| S2 | 25 | executable BIRD cases |
| S3 | 25 | executable BIRD cases |
| S4 | 15 | executable BIRD cases |
| S5 | 15 | hand-written `stub_pending`, missing question/evidence/SQL |

Therefore the current file is **85 executable BIRD cases + 15 planned robustness cases**, not yet a 100-case executable SQL benchmark.

### Database coverage

The 85 BIRD cases cover the 11 Mini-Dev databases. Across all 100 slots (including S5 placeholders), the current DB allocation is:

```text
formula_1                 16
student_club              13
toxicology                11
european_football_2       10
superhero                  10
card_games                  9
codebase_community          8
thrombosis_prediction      7
debit_card_specializing    7
california_schools          6
financial                   3
```

Coverage exists, but it is intentionally not uniform. Report per-database results so a database-heavy slice cannot hide failures elsewhere.

## Structural coverage

For the 85 executable cases:

```text
S1: 20 — all 0 JOIN, single SELECT
S2: 25 — all exactly 1 JOIN, single SELECT
S3: 25 — mostly multi-join and/or subquery
S4: 15 — CTE / window / set-op / deep-subquery focused
```

Observed SQL feature counts across all executable cases include:

```text
CTE        6
window     5
set_op     3
subquery  20
sub_deep   6
HAVING     4
```

The taxonomy is useful for diagnosis, but should be named **T2S structural strata**, not BIRD difficulty. Official BIRD difficulty should be stored as a separate field.

## Gold-SQL correction risk

Among 85 BIRD cases:

```text
51  sql_corrected == sql_original
34  sql_corrected != sql_original
```

Of those 34 changed cases, the stored execution comparison reports:

```text
7   corrected/original results match
27  corrected/original results differ
```

A different result is not automatically wrong — a correction may intentionally fix a faulty gold query — but it means the correction materially changes benchmark semantics. These cases require an auditable correction ledger before `sql_corrected` can be treated as authoritative gold.

Static risk flags found in changed SQL include projection changes, join-count changes, SELECT-count changes, comparison-boundary changes, set-operation changes, and one time-reference change. These are review signals, not automatic judgments of correctness.

### High-priority manual review example

`bird_1242` changes the age reference from examination year to `CURRENT_TIMESTAMP`. The natural-language question refers to laboratory examinations in 1984 and patients below 50 years old. This semantic change is material and should be independently checked against the intended benchmark interpretation before the corrected SQL is used as gold.

## Recommended freeze policy

1. **Never overwrite official BIRD gold silently.** Preserve `sql_original` forever.
2. Every correction must have a ledger record:
   - `case_id`
   - reviewer
   - rationale
   - correction timestamp/version
   - semantic category
   - original execution result hash
   - corrected execution result hash
   - approval status
3. Until all 34 changed cases are reviewed, report two metrics when needed:
   - `EX_official` against official BIRD SQL/results.
   - `EX_curated` only against approved corrected gold.
4. Do not count the 15 S5 stubs in EX.
5. S5 should have its own metrics: correct abstention, correct clarification, unsafe overreach.

## Final assessment of the current 100 slots

The **sampling idea is strong** and suitable as a development/pilot set. The file is not yet ready to be called a frozen 100-case benchmark because:

- 15 S5 cases are unfinished;
- official BIRD difficulty is not retained;
- corrected-gold provenance/approval is not explicit;
- 27 corrections materially change execution results.

The recommended path is to keep this file as an **opened development pilot**, finish/review S5 separately, and create a second 100-case BIRD-only evaluation set from unseen Mini-Dev rows.
