# T2S / CHATSQL Documentation Package — Version 2

**Version:** 2.0  
**Date:** 2026-09-17  
**Status:** Evidence-aligned deployment documentation  
**Primary architecture state:** MG0 current runtime, MG* evidence-gated target

This package is the authoritative Version 2 documentation set for the T2S / CHATSQL project.

## Reading order

1. `02_CANONICAL_PROJECT_STATE_AND_EVIDENCE.md`
2. `03_SYSTEM_ARCHITECTURE.md`
3. `04_GROUNDING_ENGINE_MG0_TO_MGSTAR.md`
4. `05_EVALUATION_EXPERIMENT_AND_CERTIFICATION_PROTOCOL.md`
5. `06_SECURITY_AUTHORIZATION_AND_RUNTIME_GOVERNANCE.md`
6. `07_OPENMETADATA_KNOWLEDGE_ARCHITECTURE.md`
7. `08_N8N_DEPLOYMENT_AND_INTEGRATION.md`
8. `09_EVIDENCE_GATED_ROADMAP.md`
9. `10_RISK_LIMITATIONS_AND_UNKNOWN_UNKNOWNS.md`
10. `11_PRODUCTION_READINESS_GATES.md`
11. `12_GLOSSARY_ADR_AND_DECISION_LOG.md`
12. `01_VISION_SCOPE_REQUIREMENTS.md`
13. `00_EXECUTIVE_SUMMARY.md`

## Core rule

> Evidence chooses the architecture. Architecture does not choose the evidence.

## Canonical terminology

- **MG0:** current deployable grounding implementation.
- **MG\*:** certified composition of grounding capabilities that have independently passed controlled evaluation.
- **OR\*:** non-deployable oracle diagnostic with the same evidence types as MG\*, but oracle-perfect relevance selection.
- **Production Semantic Safe Rate:** `(A + B) / Total` under the canonical A–F audit taxonomy.

## Current deployment direction

`n8n orchestration` below is the **intended** caller — no n8n integration code exists in the repository today (see `08`). The verified current runtime starts at `POST /v1/query`.

```text
User / Internal UI
        ↓
n8n orchestration                          [intended — NOT implemented]
        ↓
POST /v1/query                             [current, verified]
        ↓
T2S FastAPI Runtime
        ↓
Security / Authorization
        ↓
MG0 Grounding
        ↓
Final Grounded Context
        ↓
gpt-oss-120b Direct SQL Solver
        ↓
Deterministic Validation
        ↓
Authorization Re-check
        ↓
SqlRiskController / ValidatorMode
        ↓
Controlled Read-only DB Execution
        ↓
ResultVerifier
        ↓
Decision Policy
        ↓
Accept / Caveat / Clarify / Abstain
```

## Version 2 changes

Version 2 explicitly separates:

- current runtime vs target architecture,
- strict benchmark score vs semantic safety,
- MG0 vs MG\*,
- ResultVerifier vs SqlRiskController vs ValidatorMode,
- OpenMetadata ownership vs T2S ownership,
- n8n orchestration vs T2S intelligence,
- verified evidence vs supported hypotheses.

