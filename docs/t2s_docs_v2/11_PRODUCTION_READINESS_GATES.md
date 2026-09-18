# 11 — Production Readiness Gates

**Version:** 2.0

The project is not production-ready because of one benchmark number. Production readiness requires all mandatory gates below.

---

## 1. Architecture

- [ ] current runtime diagram matches actual code
- [ ] MG0/MG* states documented
- [ ] ResultVerifier / SqlRiskController / ValidatorMode remain separate
- [ ] no duplicate SQL-generation stack in n8n

## 2. Security

- [ ] identity path verified
- [ ] metadata ACL behavior verified
- [ ] independent SQL authorization verified
- [ ] DB RBAC/RLS verified
- [ ] read-only enforcement tested
- [ ] secrets externalized

## 3. Metadata / OpenMetadata

- [ ] OpenMetadata connected
- [ ] schema/column sync verified
- [ ] PK/FK sync verified
- [ ] freshness/version handling verified
- [ ] stale metadata behavior defined

## 4. Grounding

- [ ] MG0 deterministic regression suite passes
- [ ] certified capabilities clearly identified
- [ ] uncertified capabilities OFF/SHADOW
- [ ] context provenance persisted

## 5. Solver

- [ ] provider/model config frozen per deployment
- [ ] timeout/retry policy defined
- [ ] no hidden benchmark-specific prompt logic

## 6. Verification / execution

- [ ] AST safety checks active
- [ ] authorization re-check active
- [ ] ValidatorMode governance verified
- [ ] DB timeout tested
- [ ] row limit tested
- [ ] ResultVerifier behavior tested

## 7. Evaluation

- [ ] candidate SQL persisted
- [ ] context persisted
- [ ] canonical A–F audit available
- [ ] lucky-match checks included where needed
- [ ] holdout governance documented

## 8. n8n

- [ ] `/health/ready` works from n8n environment
- [ ] `/v1/query` works end-to-end
- [ ] request ID propagates
- [ ] no second SQL Agent path
- [ ] error/status mapping tested

## 9. Operations

- [ ] logs centralized
- [ ] alerts defined
- [ ] rollback procedure defined
- [ ] incident owner identified
- [ ] deployment versioning in place
- [ ] schema/metadata drift runbook available

## 10. Readiness verdict

Allowed verdicts:

- `NOT_READY`
- `LAB_READY`
- `PILOT_READY`
- `PRODUCTION_READY`

A benchmark score alone cannot change this verdict.

