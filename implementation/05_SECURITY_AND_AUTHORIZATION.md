# 05 — Security and Authorization

## 1. Trust boundaries

```text
Browser/User -> corporate SSO/reverse proxy -> T2S -> OpenMetadata/vLLM/DB Gateway
```

The LLM is never a security boundary.

## 2. Identity flow

1. Reverse proxy/SSO authenticates user.
2. T2S verifies JWT/signature/issuer/audience according to company standard.
3. `IdentityResolver` maps claims to `UserContext`.
4. `AuthorizationPort` resolves effective catalog/data scope.
5. Scope is applied to metadata retrieval.
6. DB gateway selects a corresponding read-only DB identity/role and rechecks referenced objects.

Never accept `user_id`, `role` or allowed tables from the query JSON as authoritative.

## 3. Metadata leakage prevention

Apply authorization before search when the index supports it, then **post-filter every hit** through `AuthorizationPort` before exposing it to the LLM. Search indexes are an optimization layer; they are not the source of truth for ACL.

Do not log unauthorized FQNs in user-visible error messages.

## 4. SQL safety policy

AST gate allows only a single read query expression (`SELECT`, `WITH`, set operations as configured). Block at minimum:

- `INSERT`, `UPDATE`, `DELETE`, `MERGE`;
- `CREATE`, `ALTER`, `DROP`, `TRUNCATE`;
- `GRANT`, `REVOKE`, session/admin commands;
- multi-statement SQL;
- `SELECT ... INTO` or dialect equivalents that write;
- disallowed system catalogs/functions/table functions;
- any referenced table outside authorized scope.

Because `SELECT` can still invoke dangerous/external functions in some engines, maintain **dialect-specific deny/allow lists** and rely on least-privilege DB accounts. The parser is defense-in-depth, not the final barrier.

## 5. Database enforcement

### PostgreSQL
Use a dedicated role and begin each request transaction as `READ ONLY`; set `statement_timeout` per session/request. PostgreSQL documents both `transaction_read_only`/`default_transaction_read_only` and `statement_timeout`. [R15–R16]

### StarRocks
Use a dedicated role with `SELECT`/required `USAGE` privileges only. StarRocks provides RBAC/IBAC and recommends roles for privilege management. [R20]

### ClickHouse
Use a dedicated read-only user/profile/role according to the deployed ClickHouse version and restrict allowed databases/tables/functions. Apply query settings such as execution/result limits through the official driver. [R17–R18]

## 6. vLLM hardening

Do not expose vLLM directly to users. Place it behind the internal network/reverse proxy. Current vLLM documentation warns that its API-key option does not protect every endpoint, so network and proxy controls are required. [R2]

## 7. Secrets

- credentials in secret manager/environment injection, never repository/config files;
- DB credential scope per environment/domain;
- rotate independently;
- never send credentials to prompts/logs/traces.

## 8. Security tests

Required regression cases:

- user asks for an unauthorized table by exact FQN;
- schema search could retrieve a hidden table by semantic similarity;
- prompt injection asks model to reveal hidden metadata;
- generated SQL references a hidden table despite grounded scope;
- multi-statement and DDL payloads;
- SELECT using dangerous external/table functions;
- DB role cannot mutate even if AST guard is bypassed.
