# 02 — Requirements and Success Metrics

## 1. Functional requirements

| ID | Requirement | Acceptance concept |
|---|---|---|
| FR1 | Ask business questions in VI/EN | Question -> result/SQL/explanation or safe non-answer |
| FR2 | Schema/context discovery at enterprise scale | Required tables/columns are discoverable without full-schema prompts |
| FR3 | Resolve values/time/business terms when evidence exists | Grounded values are traceable to metadata/DB evidence |
| FR4 | Generate read-only SQL | Candidate SQL can be parsed/validated for target dialect |
| FR5 | Verify before exposure | Deterministic and optional semantic checks run before final answer |
| FR6 | Safe execution | User role, RLS, timeout, result limits, audit |
| FR7 | Selective answering | System can answer, identify a specific ambiguity, or abstain |
| FR8 | Explainability/traceability | Operators can inspect metadata, evidence, SQL and decisions used |

## 2. Primary product metrics

### 2.1 Precision and coverage

For threshold `t`:

- `coverage(t)`: fraction of questions answered.
- `precision(t)`: fraction correct among answered questions.
- `selective_risk(t) = 1 - precision(t)`.

The main report is the **risk–coverage curve**, not one hand-picked threshold.

### 2.2 Initial business gate

- Provisional minimum: `precision >= 85% at coverage >= 55%` on the curated target-domain evaluation.
- The exact production operating point must be agreed with business owners after shadow traffic.
- Higher precision with unusably low coverage is not considered success.

## 3. Mandatory secondary metrics

- Raw execution accuracy on the entire evaluation set.
- Table/column recall at grounding stage.
- Error budget by category: schema, value, join, metric, grain, time, output shape, dialect/runtime.
- Calibration: reliability diagram and ECE/Brier score where sample size is sufficient.
- Security: zero unauthorized table/row access in adversarial tests.
- Latency p50/p95 and GPU-seconds per answered question, tracked but initially secondary to accuracy.
- Abstention quality: correctness of answered set and reasons for non-answer.
- Generalization slices: unseen database/domain, schema scale, language, dialect, metadata richness.

## 4. Production quality gates

A mechanism is not accepted merely because aggregate EX rises. At minimum, inspect:

1. fixed vs broke cases;
2. precision/coverage movement;
3. critical error classes;
4. latency/warehouse load;
5. new operational dependencies;
6. behavior on unseen schemas.

## 5. Benchmarking scope

A curated 100–200-case working set stratified by difficulty is appropriate for development/error analysis, but it must not be the only evidence. Keep a locked holdout and periodically sanity-check on larger public benchmarks such as BIRD/Spider 2.0 where relevant. Dataset construction is supporting infrastructure, not the product objective.
