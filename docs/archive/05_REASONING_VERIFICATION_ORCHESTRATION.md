# 05 — Reasoning, Verification and Bounded Orchestration

## 1. Generation baseline

The first implementation should be `Grounded Context -> gpt-oss-120b (high reasoning where needed) -> Direct SQL`.

Why direct SQL first:

- minimal architectural assumptions;
- easy to compare with public systems;
- preserves SQL expressiveness;
- provides a clean error baseline before IR/semantic constraints are introduced.

`gpt-oss-120b` supports configurable reasoning effort and structured outputs; on vLLM use the current `structured_outputs` API rather than deprecated `guided_json`. [S1–S3]

## 2. Optional solver strategies

Only enable after measuring headroom:

- divide-and-conquer;
- relational/query-plan reasoning that still outputs SQL;
- metric/business-first reasoning when business context exists;
- semantic runtime branch;
- full typed IR/plan-first branch.

CHASE-SQL and Agentar-Scale-SQL provide evidence that diverse/test-time-scaled candidates can improve difficult Text-to-SQL, but internal [I4] warns that repeated sampling of essentially the same prompt has limited ceiling. [S5–S6]

## 3. Verification layers

### 3.1 Deterministic verification — default

Checks that can be validated without another LLM:

- SQL parseability and read-only form;
- referenced table/column existence;
- dialect support;
- type/value compatibility where evidence is available;
- authorized scope;
- join edge plausibility;
- output-shape/basic projection invariants;
- dry-run / `EXPLAIN` success and execution diagnostics.

Rules that are not true invariants should begin as **signals/flags**, not hard blockers, until false-positive cost is measured.

### 3.2 Independent semantic verifier — optional

Input: question, grounded evidence, candidate SQL, diagnostics. Do **not** provide the generator's private reasoning. Ask whether all user requirements are represented: metric, denominator, grain, filters, join semantics, time, output shape.

A 2026 selective-prediction preprint reports reasoning judges outperforming simple self-consistency/executability as correctness predictors, but DPC also shows shared blind spots and consensus-on-hallucination remain possible. Therefore an LLM verifier is a feature, not an oracle. [S10–S11]

## 4. Database interaction as verification evidence

PV-SQL and VET motivate using safe probes and observable intermediate results rather than purely textual self-reflection. [S8–S9]

Preferred evidence hierarchy:

`DB/observable evidence > deterministic invariants > independent/cross-paradigm verification > reasoning judge > raw candidate consensus`.

## 5. Orchestrator behavior

The orchestrator is a bounded policy/state machine, not a free-form autonomous agent.

### Allowed recovery examples

- missing schema -> targeted search/inspect;
- bad/unresolved value -> lookup/probe;
- dialect error -> diagnostic repair using the concrete error;
- candidate disagreement -> one independent strategy or verifier;
- business-semantic uncertainty -> optional semantic context branch.

### Disallowed default behavior

Repeated "review and improve" calls with no new evidence. Internal [I3] makes this a poor default.

## 6. Candidate diversity

Track both generated candidate count and *effective* diversity. Two SQL strings with equivalent semantics/results should not be treated as two independent votes. Raw self-consistency is only one signal.

## 7. Stop conditions

Stop with Answer only when policy gates are satisfied. Stop with Abstain when:

- security or execution safety fails;
- critical evidence is unresolved;
- budget is exhausted;
- uncertainty remains above the operating threshold.

The model does not decide "I am confident enough" by itself.
