# 08 — Production Security, Observability and Operability

## 1. Security boundary

The LLM is not a security control.

- Resolve user identity and authorized scope before metadata retrieval.
- Use user/service mapping to DB roles and RLS where available.
- Enforce read-only at transaction/connection/database layer.
- Set statement timeout, row/byte limits and concurrency limits.
- Fail closed when identity/ACL resolution fails.
- Do not expose names/metadata from unauthorized scopes through routing messages.

## 2. Database Gateway

No agent or framework talks to the warehouse directly. All operations go through a controlled gateway exposing allow-listed capabilities:

- `dry_run(sql)`;
- `explain(sql)`;
- `probe(template, parameters)`;
- `execute_candidate(sql)` where policy permits;
- `execute_final(sql)`.

Every call records user, role, SQL hash/text according to policy, source candidate, elapsed time, scanned-cost signals when available and result-size metadata.

## 3. Agent budgets

Configurable limits prevent runaway autonomy:

- maximum orchestration rounds;
- schema exploration calls;
- probes/EXPLAIN calls;
- solver candidates;
- repairs;
- verifier calls;
- warehouse concurrency and cost ceilings.

Values are tuned from production/shadow traffic rather than assumed in architecture documents.

## 4. Observability

Per request, log a trace with:

`question -> authorized scope -> retrieved context -> evidence -> solver config -> candidate SQL -> verification -> DB diagnostics -> decision -> final outcome`.

This is required for debugging wrong-but-plausible answers.

## 5. Caching

Any data/result cache key must include authorization context (at least effective role/policy scope) and relevant metadata/semantic version. Prefix caching in vLLM can reduce shared prompt prefill, but does not reduce decoding cost; do not base capacity estimates on the assumption that reasoning tokens become free. [S4]

## 6. Versioning

Pin and log:

- metadata snapshot/index version;
- query-history snapshot;
- semantic-context version if used;
- model and reasoning effort;
- prompt/config hash;
- verifier/risk-model version;
- code/git revision.

## 7. Failure handling

- metadata/search unavailable -> safe degradation or abstain;
- ACL unavailable -> fail closed;
- DB timeout -> no fabricated answer;
- semantic runtime unavailable -> fall back only if raw path is independently safe/configured;
- verifier unavailable -> use the documented lower-assurance policy, not silent bypass.
