# 09 — Roadmap and Delivery Plan

The roadmap is production-driven. Architecture should emerge from evidence rather than being frozen before baseline measurements.

## P0 — Product contract

- confirm users/workflows, critical error types, initial precision/coverage gate;
- confirm allowed latency/warehouse probe budget;
- confirm security/identity integration.

**Exit:** signed product acceptance criteria.

## P1 — Environment audit

Measure the target estate:

- domains/databases/schemas/table distribution;
- description/display-name/glossary coverage;
- query-history coverage by storage technology x domain and whether logs live inside/outside OpenMetadata;
- profiler/sample/lineage/join coverage;
- warehouse EXPLAIN/probe capabilities and cost;
- ACL/RLS model.

**Exit:** environment report; no architectural assumptions hidden as facts.

## P2 — Evaluation and simple baseline

- port/retain harness;
- direct-SQL `gpt-oss-120b` with minimal grounded context;
- deterministic safe execution;
- initial error budget and risk–coverage baseline.

**Exit:** reproducible baseline numbers.

## P3 — Public-system fit-gap bake-off

Evaluate Wren and relevant Vanna/DB-GPT capabilities without deep customization. Decide which commodity components to reuse/wrap.

**Exit:** build-vs-reuse decisions.

## P4 — Reliable core improvements

Invest according to measured error budget, typically candidates such as:

- stronger hierarchical grounding;
- value/time/evidence grounding;
- deterministic verification;
- safe probes/EXPLAIN;
- calibrated answer/abstain decision.

**Exit:** production-capable non-agentic or lightly agentic core.

## P5 — Adaptive escalation

Only if residual errors/headroom justify it:

- bounded schema exploration;
- genuinely diverse alternative solver;
- independent semantic verifier;
- targeted evidence-based repair.

Compare against the fixed core under reported compute.

**Exit:** keep only mechanisms with positive production utility.

## P6 — Optional semantic/IR branch

Compare raw direct SQL, semantic context/runtime (e.g., Wren) and optional custom IR. Do not allocate major early budget here unless error analysis shows business-semantic failures are material.

## P7 — Production hardening

- load/concurrency tests;
- security red-team cases;
- observability dashboards;
- rollback/fallback policy;
- runbooks and SLO alerts.

## P8 — Shadow -> pilot -> controlled rollout

Expand domain/user scope only after regression and risk–coverage gates hold on shadow traffic.

## Guiding rule

At every phase: **a technically elegant mechanism that does not materially improve the production job is rejected or deferred.**
