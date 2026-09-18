# 01 — Vision, Scope and Requirements

**Version:** 2.0

---

## 1. Vision

Enable enterprise users to ask natural-language questions over governed company data and receive safe, traceable SQL-backed answers without requiring users to understand physical warehouse schemas.

---

## 2. Primary goals

- high SQL correctness,
- useful coverage,
- calibrated abstention,
- generalization across schemas/domains/dialects,
- security and authorization,
- maintainability,
- observability,
- evidence-driven evolution.

---

## 3. Current scope

### CURRENT

- FastAPI T2S service,
- fixed direct 120B-class solver,
- MG0 grounding,
- read-only SQL safety validation,
- authorization checks,
- SqlRiskController / ValidatorMode governance,
- controlled DB execution,
- ResultVerifier,
- n8n integration pattern designed; not yet implemented or verified (see `08`),
- OpenMetadata as intended metadata truth source; provider code exists but is not the default catalog source today (see `07`).

### NEXT

- Temporal Grounding isolated experiment,
- OpenMetadata integration hardening,
- production observability completion,
- evidence-gated MG capability certification.

### FUTURE

- MG*,
- OR*,
- solver ceiling diagnosis,
- multi-dialect generalization,
- scale stress testing,
- enterprise pilot.

---

## 4. Functional requirements

1. Accept natural-language question.
2. Resolve effective user/data authorization.
3. Retrieve relevant schema/relationship context.
4. Construct bounded grounded context.
5. Generate one candidate read-only SQL query.
6. Validate SQL safety and authorization.
7. Execute in controlled read-only environment.
8. Verify result/risk signals.
9. Return answer, caveat, clarification request, or abstention.
10. Persist full evaluation/observability artifacts.

---

## 5. Non-functional requirements

### Reliability

- no silent retry loops,
- bounded execution,
- clear failure modes,
- traceable decisions.

### Security

- deny-by-default for unauthorized entities,
- independent metadata and DB authorization,
- no secrets in code/workflow JSON.

### Maintainability

- capability modularity,
- provider-agnostic LLM interface,
- architecture guards,
- versioned metadata projection.

### Evaluation

- canonical A–F semantic audit,
- reproducible configuration,
- candidate SQL persistence.

---

## 6. Explicit non-goals for current mainline

- unrestricted agentic loops,
- planner-first architecture,
- multi-solver debate by default,
- semantic layer as mandatory runtime,
- benchmark-specific heuristics,
- automatic production promotion of experimental grounding modules.

