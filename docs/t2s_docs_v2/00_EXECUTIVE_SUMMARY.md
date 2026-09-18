# 00 — Executive Summary

**Version:** 2.0

T2S / CHATSQL is an **enterprise evidence-grounded Text-to-SQL system** designed to let business users ask questions in natural language while keeping SQL generation governed, observable, and safe.

The project does not treat Text-to-SQL as only a prompt-generation problem. The central engineering problem is to construct a high-quality, legitimate, question-specific context from enterprise metadata and then let a fixed 120B-class solver independently derive SQL.

## Current architecture

The entry point (`User/UI → n8n`) is the **intended caller path**, not yet implemented — no n8n integration code exists in the repository today. See `08_N8N_DEPLOYMENT_AND_INTEGRATION.md`. The verified current runtime begins at T2S FastAPI.

```text
User / UI
→ n8n                              [intended caller — NOT yet implemented]
→ T2S FastAPI                      [current, verified]
→ Security / Authorization
→ MG0 Grounding
→ Final Grounded Context
→ gpt-oss-120b Direct SQL Solver
→ AST / Safety Validation
→ Authorization Re-check
→ SqlRiskController / ValidatorMode
→ Controlled Read-only DB Execution
→ ResultVerifier
→ Decision Policy
→ Accept / Caveat / Clarify / Abstain
```

## Current Grounding status

Current deployable baseline is **MG0**:

```text
SchemaRetriever
+ RelationshipExpander
+ GroundingBudget
+ S0 Serializer
```

Target **MG\*** is not a larger feature bundle. It is MG0 plus only grounding capabilities that have independently passed controlled experiments and certification.

## What has been demonstrated

- P1 showed directional strict-score differences across context/serialization arms, but historical candidate SQL was not persisted, so semantic re-audit is blocked.
- P2-R2 established a canonical A–F semantic audit.
- On the fully audited 18-case synthetic hard-query cohort, MG achieved **85.19% Production Semantic Safe Rate**, compared with **20.37% for FS**.
- This does **not** mean production accuracy is 85.19%.
- Current OR is invalid as an oracle ceiling because its context construction differed incorrectly from MG.

## Immediate next step

Temporal logic is the largest remaining MG true-error class in P2-R2. Therefore the next evidence-gated experiment is an isolated **Temporal Grounding** test on a frozen unseen temporal challenge set.

Production defaults remain unchanged until certification.

## Deployment direction

- OpenMetadata: intended metadata source of truth. Provider code exists but is not the default catalog source today (see `07`).
- T2S: grounding, SQL generation, verification, execution policy.
- n8n: intended transport/business workflow orchestration. No implementation exists yet (see `08`).
- Databases: authoritative data and native access control. Only PostgreSQL and SQLite have implemented executors today; ClickHouse and StarRocks are not implemented.

## Project rule

> Evidence chooses the architecture. Architecture does not choose the evidence.

