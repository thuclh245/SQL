# 16 — Implementation Acceptance Checklist

## Before first end-to-end baseline

- [ ] `/v1/query` accepts question but identity is trusted middleware only.
- [ ] Authorization failure is fail-closed.
- [ ] OpenMetadata adapter works against pinned server version.
- [ ] Metadata index build is versioned and switchable by alias.
- [ ] Grounding returns only authorized tables.
- [ ] vLLM returns structured `SolverOutput`.
- [ ] SQLGlot parses using explicit target dialect.
- [ ] AST guard rejects write/admin/multi-statement SQL.
- [ ] DB role is read-only even if guard is bypassed.
- [ ] EXPLAIN/dry-run uses timeout/cost limits.
- [ ] Every request has a trace/run record.
- [ ] No answer is fabricated after dependency failure.

## Before enabling adaptive loops

- [ ] Baseline error budget exists.
- [ ] Each loop action maps to a measured failure class.
- [ ] Maximum rounds/calls/probes are configured.
- [ ] Generic self-reflection is disabled by default.
- [ ] Fixed/broke comparison exists for the proposed loop.
- [ ] Warehouse load of probes/execution is measured.

## Before pilot

- [ ] Security adversarial suite passes.
- [ ] Precision/coverage operating point chosen on tune data and checked on locked holdout/shadow labels.
- [ ] Rollback for code/config/index/prompt exists.
- [ ] Optional features can be independently disabled.
- [ ] Operator dashboard and runbook exist.
- [ ] Data retention/logging policy reviewed.
- [ ] DB roles and resource limits reviewed by platform/security owners.
- [ ] No single public OSS framework is a hidden load-bearing dependency without ownership/maintenance plan.

## Production definition of done

A production candidate is not “the model generated SQL”. It is a system that can demonstrate: authorized grounding, read-only execution, reproducible context/model versions, observable verification, controlled recovery, measurable precision/coverage and safe abstention.
