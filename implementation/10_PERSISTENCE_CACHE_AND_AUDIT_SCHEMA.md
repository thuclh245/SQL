# 10 — Persistence, Cache and Audit Schema

## 1. PostgreSQL control-plane tables

Minimum schema:

```text
query_run
- id UUID PK
- created_at
- subject_hash / actor_id according to privacy policy
- question_hash + optionally encrypted/redacted question text
- locale
- scope_id
- status
- config_version
- model_version
- index_version
- prompt_version
- final_sql
- final_decision
- final_score nullable
- latency_ms

candidate
- id UUID PK
- run_id FK
- strategy
- sql
- dialect
- canonical_sql
- solver_latency_ms
- token_usage JSONB

verification_finding
- id
- candidate_id
- code
- severity
- message
- evidence_refs JSONB

operation_event
- id
- run_id
- kind (search/probe/explain/execute/llm/etc.)
- started_at / elapsed_ms
- success
- details JSONB

feedback
- run_id
- actor
- correctness_label nullable
- usefulness_label nullable
- corrected_sql nullable
- comment nullable
```

If storing raw questions/results is sensitive, store hashes/redacted summaries and keep full payload in an approved secure store with retention rules.

## 2. Metadata snapshot registry

```text
metadata_snapshot
- id
- openmetadata_server_version
- indexed_at
- index_alias
- entity_count
- document_count
- source_watermark
```

Every query points to a snapshot/index version for reproducibility.

## 3. Cache policy

Possible caches:

- hydrated table metadata;
- glossary lookups;
- retrieval results;
- LLM prompt prefixes (vLLM side);
- safe profile/query-log summaries.

Never cache final query results across users unless the cache key includes effective authorization scope and data freshness/version. Start with metadata caches, not result caches.

## 4. Cache keys

At minimum include:

```text
scope_id + metadata_version + query_normalized + retrieval_config_version
```

For any user-data result cache include DB/data-version policy or short TTL plus effective role/scope.

## 5. Retention

Define explicit retention tiers for:

- audit/security events;
- prompts/questions;
- generated SQL;
- query results;
- user feedback.

Do not let observability accidentally become a new sensitive-data warehouse.
