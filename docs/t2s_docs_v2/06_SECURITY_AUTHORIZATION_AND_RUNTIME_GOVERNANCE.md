# 06 — Security, Authorization and Runtime Governance

**Version:** 2.0

---

## 1. Security principle

Metadata visibility is not database authorization.

Effective access must satisfy:

```text
metadata visibility
AND
T2S authorization
AND
database role/RLS
```

**Deny wins.**

---

## 2. Security layers

### Request identity

- authenticate user/service identity,
- propagate correlation IDs,
- resolve role/group context.

### Grounding authorization

Unauthorized schemas/tables/columns must not appear in grounding context.

### SQL authorization

Generated SQL must be independently checked against the allowed table/schema set.

### Database authorization

Warehouse-native RBAC/RLS remains authoritative for data access.

---

## 3. SQL safety

Minimum policies:

- SELECT/read-only only,
- deny DDL/DML,
- AST parsing required,
- dialect-aware validation,
- block forbidden functions/patterns if policy requires,
- timeout enforced,
- row limits enforced,
- query count bounded.

---

## 4. Validator governance

`ValidatorMode` states:

- `DISABLED`
- `SHADOW`
- `ENFORCE`

A validator must not move to ENFORCE without certification evidence and governance approval.

---

## 5. ResultVerifier boundary

ResultVerifier is post-execution and advisory by default.

It must not silently rewrite SQL or override authorization.

---

## 6. Secrets

Never hardcode:

- API keys,
- DB passwords,
- OpenMetadata tokens,
- n8n credentials.

Use environment/secret-management configuration.

Recommended variables:

```text
T2S_LLM_BASE_URL
T2S_LLM_API_KEY
T2S_LLM_MODEL
OPENMETADATA_URL
OPENMETADATA_TOKEN
DATABASE_URL
OPENSEARCH_URL
```

---

## 7. Audit trail

Persist:

- request ID,
- user/service identity reference,
- grounded entities,
- candidate SQL,
- authorization decision,
- validator outputs,
- execution status,
- release decision.

Do not log raw secrets.

