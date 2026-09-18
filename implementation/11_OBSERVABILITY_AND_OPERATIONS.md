# 11 — Observability and Operations

## 1. One trace per question

Spans:

```text
query
├── auth.resolve
├── grounding.search
├── grounding.hydrate
├── llm.solve
├── verify.ast
├── db.explain
├── risk.decide
├── db.execute
└── response.build
```

Escalation rounds add child spans with `round` and `reason` attributes.

## 2. Structured log fields

- trace_id / request_id;
- actor/scope pseudonymous identifiers;
- component/action;
- metadata/index/config/model/prompt versions;
- candidate strategy/id;
- SQL hash plus SQL text according to policy;
- latency/token/DB cost signals;
- verification code;
- decision/reason.

## 3. Operational metrics

### API
- request rate, p50/p95/p99 latency, error rate.

### Grounding
- candidate tables/columns count;
- search latency;
- empty/noisy context rate;
- later, measured table/column recall on labeled traffic.

### LLM
- calls/question;
- input/output/reasoning tokens if provided;
- latency by reasoning effort;
- structured-output failure rate.

### Verification/DB
- AST block rate by reason;
- EXPLAIN failure rate;
- DB timeout/error rate;
- probes/question;
- execution duration/scanned bytes when available.

### Decision
- answer/ambiguous/abstain rate;
- escalation rate;
- budget exhaustion rate;
- delayed precision/coverage after labels arrive.

## 4. Alerts

Immediate alerts for:

- authorization failures above baseline;
- any confirmed unauthorized access;
- DB mutation permission discovered;
- sharp structured-output/parse failure spike;
- metadata index stale beyond policy;
- vLLM/DB dependency error spike;
- answer rate shifts after config/model/index deployment.

## 5. Runbooks

Each production release needs:

- rollback image/config;
- index alias rollback;
- disable optional verifier/agentic escalation flags;
- disable DB probes independently;
- force conservative abstain mode;
- restore previous prompt/model config.

Feature flags make optional mechanisms reversible.
