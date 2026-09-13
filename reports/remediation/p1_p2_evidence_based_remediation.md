# P1/P2 Evidence-Based Remediation

## Remediation Status
`READY_FOR_INDEPENDENT_REREVIEW`

This remediation implemented the prompt-required P1 and P2 fixes only. It does not mark P1 or P2 as PASS.

## P1 Findings

### P1-R1 CTE/base-table authorization collision
- Decision: `FIXED_NOW`
- Evidence: SQLGlot scope traversal showed `main.secret_payroll` resolves to a physical table even when a CTE named `secret_payroll` exists.
- Change: `ParsedSql.referenced_table_identifiers()` now uses `sqlglot.optimizer.scope.traverse_scope` and only ignores scoped CTE/subquery sources.
- Test: `test_cte_short_name_collision_does_not_bypass_authorization`, plus parser tests for schema-qualified, nested CTE, nested subquery, and quoted identifiers.

### P1-R2 SELECT INTO read-only bypass
- Decision: `FIXED_NOW`
- Evidence: SQLGlot parses `SELECT * INTO new_table FROM customers` with an `Into` node under `Select`.
- Change: `SqlSafetyValidator` treats `Into` as mutation-oriented.
- Test: `test_validator_blocks_mutation_oriented_sql[SELECT * INTO new_table FROM customers]`.

### P1-R3 SELECT FOR UPDATE / locking reads
- Decision: `FIXED_NOW`
- Evidence: SQLGlot parses `FOR UPDATE`, `FOR SHARE`, and `FOR NO KEY UPDATE` as `Lock` nodes.
- Change: `SqlSafetyValidator` treats `Lock` as mutation/concurrency-oriented.
- Test: regression cases for `FOR UPDATE`, `FOR SHARE`, and `FOR NO KEY UPDATE`.

### P1-R4 Database driver error normalization
- Decision: `FIXED_NOW`
- Evidence: SQLite `DatabaseError` previously escaped raw.
- Change: `SqliteReadOnlyQueryExecutor` raises `SqlExplainError` for explain failures, `QueryExecutionError` for execution failures, and preserves timeout as `QueryExecutionTimeoutError`.
- Test: `test_driver_execution_error_is_normalized_and_audited_as_failed`, `test_driver_explain_error_is_normalized`.

### P1-R5 Deterministic SQLite connection closing
- Decision: `FIXED_NOW`
- Evidence: `sqlite3.Connection` context management does not close the handle.
- Change: wrapped read-only connections with `contextlib.closing(...)`.
- Test: `test_sqlite_connection_closes_after_success_and_driver_error`.

### P1-R6 Audit correlation and outcome semantics
- Decision: `FIXED_NOW`
- Evidence: audit events lacked `run_id`, `request_id`, `trace_id`, and runtime DB failures were labeled `blocked`.
- Change: `QueryAuditEvent` now includes correlation fields and outcome `failed`; validation rejections remain `blocked`, DB attempted failures are `failed`.
- Test: `test_audit_event_preserves_correlation_identifiers`, `test_driver_execution_error_is_normalized_and_audited_as_failed`.

## P2 Findings

### P2-R1 Ghost/orphan search documents after column mutation
- Decision: `FIXED_NOW`
- Evidence: search documents for existing changed tables were upserted without clearing stale table/column documents.
- Change: full sync and incremental sync delete search documents for changed/upserted table FQNs before writing the current documents.
- Test: dropped-column cleanup, column rename cleanup, and incremental changed-table cleanup.

### P2-R2 OpenSearch bulk request chunking
- Decision: `FIXED_NOW`
- Evidence: all documents were serialized into one `_bulk` payload.
- Change: `OpenSearchMetadataIndex` now accepts `bulk_batch_size` and posts bounded batches while checking partial errors per batch.
- Test: `test_opensearch_bulk_indexing_is_chunked`, plus NDJSON and partial-error tests.

### P2-R3 Targeted adapter/indexer regression tests
- Decision: `FIXED_NOW`
- Evidence: adapter/worker boundary behavior was previously thinly covered.
- Change: added focused tests for OpenMetadata pagination/error handling, OpenSearch bulk/delete behavior, metadata sync cleanup, and relationship lookup.
- Test: full suite now includes 84 tests.

### P2-R4 Unsafe/uncertain sql_identifier fallback
- Decision: `FIXED_NOW`
- Evidence: fallback `database.schema.table` was a guess, not a reliable executable identity.
- Change: `CatalogTable.sql_identifier` is now `str | None`; `sql_identifier_source` records `explicit`, `resolved`, or `unresolved`. OpenMetadata mapper only sets it when `sqlIdentifier` is explicitly provided.
- Test: `test_openmetadata_mapper_marks_missing_sql_identifier_as_unresolved`.

### P2-R5 Incoming + outgoing relationship lookup
- Decision: `FIXED_NOW`
- Evidence: `InMemoryCatalog.get_relationships()` returned only outgoing FKs.
- Change: integrated `RelationshipGraph` into `InMemoryCatalog`; one canonical FK is indexed under both endpoints without duplication.
- Test: outgoing lookup, incoming lookup, no duplicate relationship, and multiple relationships.

### P2-R6 Robust handling of incomplete OpenMetadata table payloads
- Decision: `FIXED_NOW`
- Evidence: missing `databaseSchema` caused a generic Pydantic validation failure.
- Change: OpenMetadata mapper now validates required identity fields and raises typed `MetadataMappingError`; `schema_name` remains required because no project evidence proved schema-less OpenMetadata tables are canonical here.
- Test: `test_openmetadata_mapper_rejects_incomplete_table_identity`.

## Findings Explicitly Deferred
- OpenSearch authentication/TLS/AWS SigV4/API-key framework: `DEFERRED_WITH_REASON`; deployment security model is not selected.
- HTTP client pooling optimization: `DEFERRED_WITH_REASON`; not a correctness defect for this remediation.
- QueryExecutionPolicy hard maximums: `DEFERRED_WITH_REASON`; no existing requirement defines exact production ceilings.
- Composite-FK GroundingContext redesign: `DEFERRED_WITH_REASON`; P2 preserves composite FK evidence, P3 must decide grounding representation.
- Production database read-only roles for non-SQLite adapters: `ENVIRONMENT_GATE`; required when those adapters are introduced.
- Live OpenMetadata/OpenSearch compatibility: `ENVIRONMENT_GATE`; no live services are configured locally.

## Findings Rejected
- Make `CatalogTable.schema_name` optional because of the synthetic missing-schema fixture: `REJECTED_WITH_REASON`; OpenMetadata Table identity is schema-owned in the project contract. Missing schema is treated as invalid/incomplete payload evidence, not canonical schema-less support.
- Generic SQL dangerous-function denylist: `REJECTED_WITH_REASON`; this remediation preserves the intended defense-in-depth model and does not add broad brittle function policy.
- Invent arbitrary timeout/row-limit maximums: `REJECTED_WITH_REASON`; no source requirement defines concrete maximums.

## Files Changed
- `src/t2s/verification/sql_ast_parser.py`
- `src/t2s/verification/sql_safety_validator.py`
- `src/t2s/database/sqlite_read_only_query_executor.py`
- `src/t2s/database/secure_query_executor.py`
- `src/t2s/catalog/catalog_models.py`
- `src/t2s/catalog/in_memory_catalog.py`
- `src/t2s/catalog/relationship_graph.py`
- `src/t2s/integrations/openmetadata/openmetadata_client.py`
- `src/t2s/integrations/openmetadata/table_mapper.py`
- `src/t2s/integrations/opensearch/opensearch_metadata_index.py`
- `src/t2s/errors/application_errors.py`
- `src/t2s/errors/__init__.py`
- `workers/metadata_indexer/index_metadata.py`
- `workers/metadata_indexer/sync_metadata_changes.py`
- P1/P2 regression tests under `tests/`.

## Regression Tests Added
- P1: CTE collision exploit, schema-qualified/quoted/nested SQL table extraction, `SELECT INTO`, locking reads, typed DB error normalization, connection closure, audit correlation/outcome.
- P2: OpenMetadata pagination/HTTP/non-JSON, mapper unresolved SQL identifier and missing identity, OpenSearch NDJSON/chunking/partial error/delete, dropped/renamed column cleanup, incremental cleanup, bidirectional relationships.

## Exact Commands and Results

```bash
.venv/bin/python -m pytest -vv
# 84 passed in 0.78s

.venv/bin/python -m ruff check .
# All checks passed!

.venv/bin/python -m mypy src workers
# Success: no issues found in 65 source files
```

Focused reproduction output:

```text
CTE exploit after fix: blocked as UnauthorizedDataAccessError
SELECT * INTO new_table FROM customers: blocked as UnsafeSqlError
SELECT * FROM customers FOR UPDATE: blocked as UnsafeSqlError
ghost column present after sync: False
incoming FK lookup count: 1
bulk request count for 3 docs with batch size 2: 2
```

## Security Exploit Reproduction After Fix
The exact CTE short-name collision pattern no longer returns unauthorized rows. It is blocked by authorization because `main.secret_payroll` remains in the scope-aware physical table reference set and is not in the user's authorized SQL resources.

## Remaining Environment Gates
- `LIVE_OPENMETADATA_INTEGRATION = PENDING`
- `LIVE_OPENSEARCH_INTEGRATION = PENDING`
- `LIVE_OPENSEARCH_SECURITY_INTEGRATION = PENDING`
- Future non-SQLite database adapters must enforce least-privilege read-only database roles.

## P3 Contract Implications
- `sql_identifier` semantics: `table_fqn` is canonical catalog identity; `sql_identifier` is executable only when reliably resolved. P3 must not construct executable `TableContext` objects from `sql_identifier=None`.
- Relationship semantics: `get_relationships(table_fqn)` returns canonical FK objects where `table_fqn` is either the source or target endpoint.
- Composite FK: still preserved in P2 as list fields; representation in `RelationshipEvidence` remains deferred to P3.

## Final Status
`READY_FOR_INDEPENDENT_REREVIEW`
