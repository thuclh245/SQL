# T2S Benchmark Design v1

## 1. Goal

Measure not only whether T2S outputs executable/correct SQL, but **where correctness is lost** across grounding, generation, escalation, verification, and execution.

## 2. Two-set design

### Set A — `t2s_pilot_v1`

Purpose: fast iteration and failure analysis.

- Opened during development.
- 85 executable BIRD questions + 15 robustness slots.
- May be used to tune P3/P4/P5/P6.
- Must not be used as the sole evidence for final generalization claims.

### Set B — `t2s_eval_v1`

Purpose: checkpoint evaluation on unseen BIRD questions.

- Exactly 100 BIRD Mini-Dev 500 SELECT-only cases.
- Excludes all BIRD `question_id`s present in Set A.
- Official question/evidence/SQL are copied from the user's local canonical BIRD file by the builder script.
- Gold SQL is not edited before first evaluation.
- Deterministically selected and frozen by source-file SHA256 + selector seed.

## 3. T2S structural strata

These labels describe SQL structure and are independent from BIRD's `simple/moderate/challenging` labels.

### S1 — Basic / single-table

- no JOIN
- one SELECT
- no CTE/window/set operation/subquery/HAVING

Target in eval v1: **25**.

### S2 — One-join

- exactly one JOIN
- no advanced construct that would promote to S3/S4

Target: **30**.

### S3 — Complex

Any of:

- 2+ JOINs
- subquery (2 SELECTs)
- HAVING

Target: **30**.

### S4 — Advanced SQL constructs

Any of:

- CTE
- window function
- UNION/INTERSECT/EXCEPT
- deep subquery (3+ SELECTs)

Target: **15**.

Classification precedence: `S4 > S3 > S2 > S1`.

## 4. Separate robustness slice

S5 is not part of SQL EX.

Recommended subtypes:

- `ambiguous`: at least two defensible interpretations yield materially different SQL; expected behavior is clarification.
- `out_of_scope`: requested fact is not represented by authorized database evidence; expected behavior is unresolved/abstain.
- `overreach`: a tempting but unjustified nearby column/table exists; expected behavior is no fabricated answer.

Each S5 case must be schema-reviewed by a human before freeze.

## 5. Database balance

All 11 Mini-Dev databases should appear in eval v1. The selector attempts balanced round-robin sampling within structural strata and prevents one database from dominating. Exact equality is not required because structural availability differs across databases.

Report both:

- micro EX across all cases;
- macro EX across databases.

## 6. Anti-overfitting policy

Once eval v1 is generated:

- Store its manifest checksum.
- Do not inspect failures after every code change.
- Use pilot for daily debugging.
- Open eval only at named checkpoints (e.g. baseline, retrieval variant, prompt variant, release candidate).
- If eval failures are used to tune the system, eval v1 becomes opened and a new holdout must be generated from remaining cases.

## 7. Gold policy

For eval v1, first-run gold must remain official BIRD SQL. Any discovered gold defect is recorded in a correction ledger; never silently rewrite gold.

## 8. Why 100 cases

100 is appropriate for fast checkpoint testing and paired architecture comparisons. It is not enough for strong claims about production accuracy or small slices. One case is 1 percentage point overall; one case in S4 (N=15) is 6.67 points.
