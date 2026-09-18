# 07 — Evaluation and Decision Protocol

## 1. Purpose

Evaluation exists primarily to choose production mechanisms and prevent regressions. It is not an obligation to produce research novelty.

## 2. Development set

Use the planned 100–200 curated cases, stratified by complexity, for rapid diagnosis. Keep a locked holdout. Periodically validate on larger public benchmarks to catch overfitting and compare with literature.

Suggested slices:

- simple lookup / single table;
- aggregate;
- one-join;
- multi-join;
- nested/CTE/window/set operations;
- value-sensitive;
- business-semantic;
- ambiguous/out-of-scope/security;
- Vietnamese vs English where possible.

## 3. Baseline bake-off before deep customization

Run comparable workloads through:

- raw grounded `gpt-oss-120b`;
- simple custom retrieval + direct SQL;
- Wren semantic branch;
- Vanna/DB-GPT only where they can be fairly configured for the same task;
- later T2S improvements.

The goal is fit-gap analysis: identify what is already solved and what remains an error-budget bottleneck.

## 4. Keep/reject decision

Every proposed component must answer:

1. Which requirement/failure mode does it address?
2. How large is that failure mode in current data?
3. Is there a simpler solution?
4. Does the experiment improve production utility?

Production utility includes precision, coverage, critical-case errors, generalization, latency/warehouse load, maintainability and dependency risk.

## 5. Causal hygiene

Retain the strong scientific discipline from the previous project:

- gold isolation;
- pin model/prompts/code/data and environment;
- one causal change per comparison where possible;
- locked holdout;
- artifact for every run;
- paired confidence intervals/tests;
- report fixed and broke cases, not only aggregate score;
- zero-call/offline checks before expensive model experiments.

The previous hard `+8pp` oracle threshold should not be treated as a universal production rule. A +2–3pp precision gain may be very valuable in a high-risk slice if cost is acceptable.

## 6. Mechanism-specific experiments

### Grounding
Static hybrid vs hierarchical vs bounded agentic exploration; measure complete schema recall and noise.

### Probing
No probe vs safe targeted probe; measure value/schema corrections and DB load.

### Generation
Single direct SQL vs genuinely different reasoning strategies; measure pass@k, selected accuracy and effective diversity.

### Verification
Deterministic only vs + independent reasoning verifier vs cross-paradigm checks; measure selection AUROC/calibration, precision/coverage and false blocks.

### Semantic
Raw context vs semantic context vs semantic runtime; focus on metric/grain/business errors and maintenance burden.

### Orchestration
Fixed workflow vs adaptive escalation; compare quality under matched or reported compute budgets.

## 7. Production rollout evidence

Before user-visible rollout:

1. offline holdout;
2. shadow traffic;
3. operator review of failures/abstentions;
4. selected-domain pilot;
5. staged expansion with regression monitoring.
