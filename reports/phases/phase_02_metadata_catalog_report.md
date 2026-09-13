# Phase Exit Report — P2 Metadata Catalog & Indexing

## 1. Objective
Establish canonical metadata models, OpenMetadata mapping, searchable metadata documents, and reproducible indexing flow for later P3 grounding.

## 2. Scope Implemented
- Project-owned canonical catalog models for tables, columns, foreign keys, and metadata snapshots.
- `CatalogPort` with hydrate/list/upsert/delete/snapshot operations.
- Search document builder for table and column documents.
- Search index port and OpenSearch adapter with mapping, bulk upsert, delete-by-table, and snapshot writes.
- OpenMetadata adapter boundary and mappers for tables, columns, tags, glossary terms, owner, primary keys, and foreign keys.
- Full metadata indexing worker with idempotent snapshot/version computation and deletion handling.
- Incremental change synchronizer for changed/deleted table batches.
- In-memory catalog and search index implementations for deterministic local tests.
- `py.typed` package marker so worker modules can type-check against `t2s`.

## 3. Audit Classification
| Area | Classification | Notes |
|---|---|---|
| OpenMetadata code | Missing | Added client boundary and explicit table/column/relationship mappers. |
| Catalog models | Missing | Added canonical models under `src/t2s/catalog`. |
| Metadata fixtures | Missing | Added focused unit fixtures inside tests. |
| OpenSearch code | Missing | Added metadata index adapter and index mapping builder. |
| Index workers | Missing | Added full sync, search document build, and change sync modules. |
| Config URLs | Already correct | `openmetadata_url` and `opensearch_url` existed from stabilization. |
| FQN vs SQL identifier | Already correct | Preserved `table_fqn` as catalog identity and `sql_identifier` as separate physical relation identity. |
| Conflicting abstractions | None found | No previous catalog/OpenMetadata/index abstractions existed. |

## 4. Files Added / Changed
- `pyproject.toml` — added `py.typed` package data.
- `src/t2s/py.typed` — typed package marker.
- `src/t2s/errors/application_errors.py` and `src/t2s/errors/__init__.py` — metadata catalog errors.
- `src/t2s/catalog/` — canonical models, ports, document builder, relationship graph, in-memory stores.
- `src/t2s/integrations/openmetadata/` — OpenMetadata client and mappers.
- `src/t2s/integrations/opensearch/` — OpenSearch metadata index adapter.
- `workers/metadata_indexer/` — full sync, document build, and change sync worker flow.
- `tests/unit/catalog/` — search document and FQN disambiguation tests.
- `tests/unit/integrations/openmetadata/` — mapper and key/relationship tests.
- `tests/unit/workers/` — idempotent sync, update, delete, and hydrate tests.

## 5. Commands Executed
```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest tests/unit/catalog tests/unit/integrations/openmetadata tests/unit/workers -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src workers
```

## 6. Test Results
| Test group | Passed | Failed | Notes |
|---|---:|---:|---|
| P2 unit subset | 7 | 0 | Catalog documents, OpenMetadata mapper, worker sync. |
| Full test suite | 58 | 0 | Existing P0/P1/P4 tests still pass. |
| Ruff | 1 | 0 | `All checks passed!` |
| Mypy | 1 | 0 | `Success: no issues found in 65 source files` |

## 7. Metrics
| Metric | Before | After | Target | Status |
|---|---:|---:|---:|---|
| Source entity count vs indexed entity count | 0/0 | 1/1 table docs in sync tests | Reproducible | PASS |
| Sync error count | n/a | 0 in tested path | 0 | PASS |
| Deleted entity count | n/a | 1 recorded in delete test | Tracked | PASS |
| Hydrate success rate | 0% | 100% in tested FQN path | 100% | PASS |
| Full suite pass count | 51 | 58 | No regressions | PASS |

## 8. Failures Found
- Initial `workers/` mypy run treated installed `t2s` imports as untyped; added `src/t2s/py.typed` and package data.
- OpenSearch adapter initially used an Elasticsearch SDK-style `client.index`; corrected to `httpx.Client.put`.
- OpenMetadata mapper needed explicit typing for optional `extension` metadata.

## 9. Improvements Made During Self-Review
- Added duplicate short-name test to prove canonical FQN disambiguates `orders` tables across namespaces.
- Kept search documents separate from canonical catalog models.
- Preserved composite primary/foreign key evidence without inferring relationships from column names.
- Documented `sql_identifier` derivation instead of pretending OpenMetadata FQN is executable SQL.

## 10. Known Limitations
- Live OpenMetadata server compatibility is an environment gate; no server/version was available locally.
- Live OpenSearch indexing smoke is an environment gate; adapter code is present but not exercised against a running cluster.
- `sql_identifier` is read from `sqlIdentifier`/`extension.sqlIdentifier` when available, otherwise built from database/schema/table names. This is explicit and separable, but datasource-specific correctness must be verified per adapter/environment.
- Durable canonical storage is represented by `CatalogPort`; the current concrete store is in-memory for deterministic P2 tests.

## 11. Evidence / Artifacts
- `src/t2s/catalog/`
- `src/t2s/integrations/openmetadata/`
- `src/t2s/integrations/opensearch/`
- `workers/metadata_indexer/`
- `tests/unit/catalog/`
- `tests/unit/integrations/openmetadata/`
- `tests/unit/workers/`

## 12. Exit Criteria Checklist
- [x] OpenMetadata raw table payloads map to canonical models.
- [x] Canonical models build table and column search documents.
- [x] Search index build flow is reproducible in the full sync worker.
- [x] Hydrate by FQN works through `CatalogPort`.
- [x] PK/FK evidence is preserved, including composite relationships.
- [x] Metadata snapshot/version is recorded.

## 13. Exit Decision
`PASS_WITH_ENVIRONMENT_GATES`

## 14. Reason
P2-owned code paths are implemented and verified locally. Live OpenMetadata/OpenSearch compatibility cannot be honestly marked complete without configured services.

## 15. Handoff to Next Phase
P3 can use `CatalogPort` for FQN hydration and `CatalogSearchDocument` as the searchable representation. P3 should retrieve search documents, then hydrate canonical `CatalogTable` objects by stable `table_fqn`; it should not treat search documents as source of truth.
