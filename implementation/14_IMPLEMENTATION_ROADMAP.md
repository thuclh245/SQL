# 14 — Implementation Roadmap

This roadmap is ordered by dependency and production value, not by research novelty.

## Stage A — Bootstrap and contracts

Deliver:

- repository/module structure;
- configuration and dependency injection;
- FastAPI `/v1/query` skeleton;
- request trace/audit skeleton;
- Pydantic domain models/ports;
- PostgreSQL migrations.

**Exit:** API receives trusted identity, persists a run and returns a typed stub response.

## Stage B — Security + simple DB gateway

Deliver:

- SSO/JWT identity resolver;
- authorization adapter stub backed by real company source;
- SQLGlot read-query guard;
- one warehouse adapter first (choose the easiest production-relevant engine);
- EXPLAIN + read-only execution + timeout;
- security regression tests.

**Exit:** hand-written safe SELECT can be validated/executed through the gateway; writes remain impossible even if app checks are bypassed.

## Stage C — OpenMetadata + retrieval

Deliver:

- OpenMetadata adapter;
- indexer/full sync;
- OpenSearch table/column index;
- lexical retrieval;
- hydration/context serializer;
- metadata snapshot versioning.

**Exit:** question -> authorized compact schema context with reproducible index version.

## Stage D — 120B direct-SQL baseline

Deliver:

- vLLM adapter with structured output;
- solver prompt/version registry;
- direct-SQL candidate;
- AST verification + EXPLAIN + execute;
- basic Answer/Abstain policy.

**Exit:** end-to-end baseline runs on benchmark/test DB and produces complete artifacts.

## Stage E — Evaluation + observability

Deliver:

- existing benchmark harness integration;
- OpenTelemetry/metrics/logging;
- fixed/broke/error taxonomy reports;
- precision/coverage report;
- dashboards for latency, abstain, DB/LLM errors.

**Exit:** every change can be judged quantitatively and debugged per request.

## Stage F — Grounding reliability

Driven by baseline error budget:

- query-history examples;
- value/time grounding;
- profiles/sample evidence;
- relationship priors;
- safe typed DB probes.

**Exit:** measured improvement or documented negative result; only retained mechanisms stay enabled.

## Stage G — Adaptive escalation

Only if residual failures justify it:

- schema expansion;
- one alternate solver strategy;
- targeted repair;
- optional independent semantic verifier;
- bounded state machine budgets.

**Exit:** compare fixed core vs adaptive core under matched workload and compute reporting.

## Stage H — Optional semantic/IR branch

Only after core is stable. Add `SemanticRuntimePort` and compare direct-SQL with Wren/semantic context/custom IR. Keep only if accuracy/coverage/maintainability improves enough.

## Stage I — Shadow/pilot hardening

- concurrency/load tests;
- failover/fallback drills;
- security red team;
- cost controls;
- operator runbooks;
- shadow traffic labels and risk calibration;
- controlled user/domain rollout.
