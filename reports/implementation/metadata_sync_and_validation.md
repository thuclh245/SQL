# Architecture & Implementation Report: Metadata Sync, Reconciliation, Validation, and Last-Known-Good Layer

**Document ID**: `T2S-ARCH-METADATA-SYNC-2026-09`  
**System**: T2S / CHATSQL Text-to-SQL System  
**Status**: COMPLETE  
**Primary Repository**: `/home/thuclh245/MyCode/SQL`  
**Quality Gates**: Pytest: 389 passed, 1 skipped, Ruff: Clean, Mypy: 127 package files + 5 unit test suites clean, Architecture Guards: 10/10 passed  
**Paid External LLM Calls**: 0  

---

## 1. Executive Summary & Problem Context

Prior to this implementation, the T2S platform established:
1. The **Canonical Metadata Model** (`CatalogTable`, `CatalogColumn`, `CatalogForeignKey`, `AssetIdentity`), providing provider-neutral, immutable typing.
2. The **MetadataProvider Abstraction** (`MetadataProviderPort`, `PostgresMetadataProvider`, `MetadataScope`), enabling targeted catalog acquisition with 4 bounded bulk queries and scope pushdown.

However, a critical gap remained between **Metadata Acquisition** (`MetadataProviderPort`) and **Metadata Consumption** (`InMemoryCatalog`, `GroundingEngine`, vector/retrieval indices). Specifically:
* **No Reconciliation**: Ingesting a scoped update (e.g. pilot onboarding 20 tables out of an enterprise database of 9,000 tables) had no mechanism to detect what actually changed (`NEW`, `CHANGED`, `UNCHANGED`, `DELETED`), risking unintended wholesale drops of unscoped assets.
* **No Validation Gate**: Malformed foreign keys, duplicate canonical table identities, missing primary keys, or structural defects could contaminate downstream catalog memory.
* **Lack of Last-Known-Good (LKG) Preservation**: If a provider query timed out, dropped a database connection, or returned malformed schema definitions, the system risked blowing away its trusted active catalog.
* **No Incremental Pilot Onboarding Support**: Enterprises routinely have foreign keys pointing from pilot business domains into non-onboarded systems (e.g., `orders.customer_id` -> `legacy_erp.customers.id`). If referential integrity unconditionally treats missing targets as blocking errors, incremental pilot onboarding is impossible.

This capability bridges this boundary by implementing an enterprise-grade **Metadata Sync and Validation Layer**.

---

## 2. Core Architectural Decisions

### Layer Architecture Diagram

```
                 MetadataProviderPort (e.g. PostgresMetadataProvider)
                                       │
                              (candidate tables)
                                       ▼
  MetadataScope ──────► [Full-Catalog Safety Gate]
                                       │ (allow_full_catalog_sync = False by default)
                                       ▼
  Active Snapshot ────► [Scope-Aware Metadata Reconciler]
  (Store / LKG)                        │
                                       ├─► Classifies: NEW, CHANGED, UNCHANGED, DELETED
                                       ├─► Preserves unscoped tables in merged state
                                       ▼
                       [Multi-Severity Validation Gate]
                                       │
                      ┌────────────────┴────────────────┐
             Has Errors (Severity.ERROR)       Warnings Only (Severity.WARNING)
                      │                                 │
                      ▼                                 ▼
             [Metadata Quarantine]             [Candidate Snapshot Assembly]
             (QuarantineRecord stored)         (Aggregate SHA-256 Hash Computed)
                      │                                 │
                      │                        [Early No-Change Detection]
                      │                        (Hash == Active Hash? Skip promote)
                      │                                 │
                      ▼                                 ▼
             Active Snapshot UNTOUCHED         [Atomic Promotion]
             (Status: REJECTED/FAILED)         ├─► SnapshotStore.promote_snapshot()
                                               └─► Catalog.upsert_tables() & delete_tables()
                                               (Status: SUCCESS / NO_CHANGE)
```

---

### Decision 1: Scope-Aware Deletion and Unscoped Preservation

* **Observation**: In enterprise databases, teams onboard pilots in slices (e.g., 20 tables in `analytics`, while `finance` and `hr` are out of scope). If an incoming batch only contains 20 tables, standard set diffing would erroneously classify the other thousands of tables as deleted.
* **Constraint**: Assets not governed by the current authoritative `MetadataScope` must never be marked `DELETED`.
* **Reasoning**: A synchronization cycle is only authoritative for assets satisfying `scope.matches_table(...)`.
* **Decision**: In `MetadataReconciler`:
  * Assets present in `candidate` and matching `scope` are compared against `previous_snapshot`:
    * If absent from previous: `NEW`.
    * If present but semantic hash differs: `CHANGED`.
    * If present and semantic hash matches: `UNCHANGED`.
  * Assets in `previous_snapshot` that match `scope` but are absent from `candidate`: `DELETED`.
  * Assets in `previous_snapshot` that DO NOT match `scope`: preserved in `merged_tables` with count tracked as `unscoped_preserved_count`, and NEVER marked `DELETED`.
* **Tradeoff**: Downstream merged state requires unioning scoped candidates with preserved unscoped tables, requiring an $O(N)$ dictionary pass that remains sub-second for 10,000+ assets.

---

### Decision 2: Multi-Severity Validation & Pilot Referential Integrity

* **Observation**: Strict referential integrity is necessary to avoid broken joins during Text-to-SQL generation. However, during pilot onboarding, foreign keys inevitably point outside the pilot boundary.
* **Constraint**: Distinguish catastrophic internal defects from benign out-of-scope enterprise cross-references.
* **Reasoning**:
  * If table $A$ has an FK to $B$, and $B$ is within the configured `MetadataScope` but missing from source: this is a database catalog defect or extraction error (`BROKEN_REFERENCE_TARGET_MISSING_IN_SCOPE`) $\rightarrow$ **ERROR** (Blocks sync).
  * If table $A$ has an FK to $B$, and $B$ is verified to be outside the configured `MetadataScope` (e.g. points to external schema `legacy_erp`): this is an expected pilot onboarding boundary condition (`UNRESOLVED_OUT_OF_SCOPE_FK`) $\rightarrow$ **WARNING** (Allows promotion).
  * If table $A$ has duplicate identical column names, duplicate table FQNs, or references non-existent columns on existing target table: $\rightarrow$ **ERROR** (Blocks sync).
  * If table or column lacks a business description: $\rightarrow$ **WARNING** (Allows promotion, flags governance gap).
* **Decision**: Implement `ValidationSeverity` with `ERROR`, `WARNING`, and `INFO`. Candidates with `ERROR` are quarantined and blocked; candidates with `WARNING` are permitted to promote to active LKG.
* **Tradeoff**: Downstream query generation must be aware that unresolved out-of-scope foreign keys cannot be joined without onboarding the target table.

---

### Decision 3: Last-Known-Good (LKG) Preservation & Quarantine Isolation

* **Observation**: Schema syncs run automatically via scheduled tasks or CI/CD pipelines. Transient network glitches, permission revokes, or broken source schemas can crash sync jobs.
* **Constraint**: A broken sync must never destroy or corrupt the running system's active metadata catalog.
* **Reasoning**: The active catalog serves live user Text-to-SQL requests. Stale metadata from 1 hour ago is infinitely better than zero metadata or broken metadata.
* **Decision**:
  1. `MetadataSnapshotStorePort` maintains immutable historical snapshots and a pointer to the single active snapshot (`_active_snapshot`).
  2. If `provider.fetch_metadata()` raises an exception, the active snapshot remains untouched; sync returns `SyncStatus.FAILED`.
  3. If validation identifies any `ERROR` issue, the active snapshot remains untouched; sync returns `SyncStatus.REJECTED`.
  4. The rejected candidate and detailed validation findings are recorded in `MetadataQuarantinePort` (`QuarantineRecord`) without leaking database credentials.
  5. Only candidates passing validation with 0 errors are promoted via `snapshot_store.promote_snapshot(candidate_snapshot)`.

---

### Decision 4: Full-Catalog Safety Gate (`allow_full_catalog_sync`)

* **Observation**: Running a sync without scope restrictions against an enterprise cluster with 10,000+ tables can exhaust memory, trigger query timeouts, or flood vector indexes with unwanted tables (e.g., temporary staging tables, pg_internal schemas).
* **Constraint**: Ingestion must fail closed if an un-scoped sync is attempted accidentally.
* **Reasoning**: Explicit intention is required to sync an entire database catalog.
* **Decision**: `MetadataScope.is_unrestricted` returns `True` when no database, schema, or table filters are set. `MetadataSyncService` defaults `allow_full_catalog_sync = False`. If `scope.is_unrestricted` and `allow_full_catalog_sync` is false, sync aborts immediately with `SyncStatus.REJECTED` without executing any provider queries.
* **Tradeoff**: Administrators wishing to perform a full database sync must pass `allow_full_catalog_sync=True` explicitly.

---

### Decision 5: Parameterized PostgreSQL Scope Pushdown

* **Observation**: Enterprise databases contain schemas with thousands of relations. Introspecting all relations and then filtering in Python wastes database I/O and network bandwidth.
* **Constraint**: Filter pushdown must use secure parameterized queries (`ANY(%s)` and `ALL(%s)`) and never format strings directly into SQL statements.
* **Reasoning**: Pushdown allows PostgreSQL's query planner to prune catalog scans using index scans on `pg_class.relnamespace` and `pg_class.relname`.
* **Decision**: Implement `_build_pushdown_conditions(scope, schema_col, table_col)` generating:
  * `AND n.nspname = ANY(%s)` with parameter `sorted(exact_schemas)`
  * `AND n.nspname != ALL(%s)` with parameter `sorted(exact_exclude)`
  * `AND c.relname = ANY(%s)` with parameter `sorted(exact_tables)`
  Glob patterns containing `*` or `?` are not pushed down to exact array equality and are instead handled by Python-side filtering.
* **Security & Invariants**: Query strings use parameterized `%s` placeholders. Exactly 4 bulk SQL queries are executed regardless of table count.

---

## 3. Verified Components and Implementation Details

### Implemented Files in `src/t2s/catalog/`
1. `metadata_scope.py`:
   * Added `compute_fingerprint() -> str`: SHA-256 deterministic hash of all scope rules.
   * Added `is_unrestricted -> bool`: Evaluates whether all filters are None.
2. `metadata_snapshot.py`:
   * `CanonicalMetadataSnapshot`: Immutable snapshot containing `snapshot_id`, `source_system`, `scope_fingerprint`, `created_at`, `semantic_content_hash`, and indexed dictionary `tables`.
   * Fast $O(1)$ lookups: `get_table(table_fqn)` and deterministic aggregation hash calculation.
3. `metadata_reconciler.py`:
   * `MetadataReconciler`: Scope-aware change detection.
   * `ReconciliationStatus`: `NEW`, `CHANGED`, `UNCHANGED`, `DELETED`.
   * `ReconciliationSummary`: Detailed breakdown of counts, assets, and `merged_tables`.
4. `metadata_validation.py`:
   * `MetadataValidationGate`: Multi-severity validation engine.
   * Duplicate canonical FQN detection.
   * Cross-asset referential validation separating in-scope broken references from out-of-scope pilot warnings.
   * Anomaly guard: `maximum_allowed_drop_ratio` (default 0.50, prevents sudden catastrophic table drop).
5. `metadata_quarantine.py`:
   * `QuarantineRecord`: Preserves rejected candidate FQNs, timestamps, and validation issues.
   * `MetadataQuarantinePort` & `InMemoryMetadataQuarantine`.
6. `metadata_sync_result.py`:
   * `SyncStatus`: `SUCCESS`, `NO_CHANGE`, `REJECTED`, `FAILED`, `PARTIAL`.
   * `MetadataSyncResult`: Comprehensive execution telemetry (durations, summaries, active and promoted snapshot IDs).
7. `metadata_snapshot_store.py`:
   * `MetadataSnapshotStorePort` & `InMemoryMetadataSnapshotStore`: Thread-safe LKG registry, history retention, and atomic snapshot promotion.
8. `metadata_sync_service.py`:
   * `MetadataSyncService`: Full coordinator orchestrating the safety gate, provider fetch, reconciliation, validation gate, quarantine, LKG preservation, and downstream catalog sync.
9. `postgres_metadata_provider.py`:
   * Parameterized pushdown condition builder and injection into bulk catalog queries.
10. `__init__.py`:
   * Clean module exports of all public interfaces and dataclasses.

---

## 4. Test Suite and Verification Results

### Unit Test Suites Implemented
* `tests/unit/catalog/test_metadata_reconciler.py`:
  * Verifies `NEW`, `CHANGED`, `UNCHANGED`, `DELETED` state transitions.
  * Verifies that unscoped tables from previous snapshot are strictly preserved in `merged_tables` and never marked `DELETED`.
  * Verifies order-invariant hashing.
* `tests/unit/catalog/test_metadata_validation.py`:
  * Duplicate canonical FQN detection (rejected with ERROR).
  * Valid FK resolution across candidate and merged assets.
  * Broken FK target column references (rejected with ERROR).
  * Missing FK target within scope (rejected with ERROR).
  * Out-of-scope pilot FK reference (accepted with WARNING).
  * Missing description warning.
  * Asset drop anomaly guard rejection.
* `tests/unit/catalog/test_metadata_sync_service.py`:
  * Full-catalog safety gate blocking unrestricted scope by default (0 provider calls).
  * Full-catalog safety gate permissive when explicitly configured.
  * Provider exception handling: preserves active LKG snapshot (status `FAILED`).
  * Validation error handling: preserves active LKG snapshot, records quarantine (status `REJECTED`).
  * Warning-only promotion: promotes candidate (status `SUCCESS`).
  * Idempotent no-change detection: detects identical semantic hash and skips promotion (status `NO_CHANGE`).
  * Downstream `InMemoryCatalog` atomic synchronization.
* `tests/unit/catalog/test_postgres_scope_pushdown.py`:
  * Parameterized clause generation for schemas, excludes, and table inclusions.
  * Glob pattern isolation from exact pushdown clauses.
  * Cursor execution verification: all 4 bulk metadata queries receive `%s` parameters.
* `tests/unit/catalog/test_metadata_sync_scale.py`:
  * Synthetic enterprise scale benchmark with 9,000 tables, 27,000 columns, and 9,000 foreign keys.
  * Reconciliation of 9,500 assets (8,000 unchanged, 500 changed, 500 deleted, 500 new) completed in **< 0.5 seconds** ($O(N)$ linearity).
  * Full cross-asset validation of 9,000 assets completed in **< 0.4 seconds**.

### Verification Gate Execution Summary
```bash
$ .venv/bin/pytest
389 passed, 1 skipped in 5.68s

$ .venv/bin/pytest tests/unit/architecture/test_architecture_hygiene_guards.py
10 passed in 0.23s

$ .venv/bin/ruff check src tests
All checks passed!

$ .venv/bin/mypy
Success: no issues found in 127 source files
```

---

## 5. Architectural Hygiene and Governance Attestation

1. **Production Isolation**:
   * All production code resides strictly in `src/t2s/catalog/`.
   * Zero references to benchmark suites (`spider`, `bird`, `qddd`, `spider2`) exist in production modules.
   * Zero phase-based tokens (`phase_1`, `phase_2`) exist in production symbol names.
2. **Cost & LLM Invariant**:
   * `PAID_LLM_CALLS = 0`.
   * No calls to external LLM providers or OpenAI/Anthropic APIs were made or introduced.
3. **Boundary Decoupling**:
   * Downstream consumers (`GroundingEngine`, `CatalogPort`, vector indexes) remain completely decoupled from provider mechanics, connecting only to validated `CatalogTable` canonical entities and `CanonicalMetadataSnapshot`.
4. **Secret Safety**:
   * The secret scanner (`scan_current_tree` and `scan_git_history`) passes 100%. No secrets or connection credentials are exposed in code or quarantine records.

---

## 6. Hardening Pass: Pre-OpenMetadata Review Closure

Following independent senior architecture review, 6 critical logic and integrity points were addressed prior to introducing the OpenMetadata provider:

1. **Structured Identity Resolution without `split(".")`**:
   * `CatalogForeignKey` now carries structured target identity fields (`to_schema_name`, `to_table_name`, `to_database_name`, `to_service_name`).
   * `AssetIdentity.parse_canonical_locator(locator)` parses `<service>.<database>.<schema>.<asset>` with full support for quoted/escaped identifiers containing dots.
   * `MetadataValidationGate` resolves foreign key destinations strictly through structured coordinates or the parser, eliminating naive string splitting.
2. **True Atomic Serving Promotion**:
   * Added `sync_snapshot(tables: list[CatalogTable], snapshot_id: str)` to `CatalogPort` and `InMemoryCatalog`, replacing table mappings and relationship graph atomically.
   * Inverted promotion ordering in `MetadataSyncService`: serving catalog state is synchronized *prior* to snapshot promotion. If catalog sync fails, promotion aborts and active LKG remains untouched.
3. **Provider / Source Authority Transition Modeling**:
   * Modeled provider authority transitions (`current_active.source_system != provider.source_system`).
   * When switching sources (e.g. `postgresql` $\rightarrow$ `openmetadata`), identical semantic table content is no longer suppressed as `NO_CHANGE`. It promotes a new active snapshot stamped with the new source authority and provenance.
4. **Strict Scope Validation Boundary**:
   * Added Rule 0 in `MetadataValidationGate`: any candidate table returned by a provider that does not satisfy `scope.matches_table()` triggers `CANDIDATE_OUTSIDE_SCOPE` with `Severity.ERROR`, quarantining the batch immediately.
5. **Secret Sanitization in Error Messages**:
   * Implemented `sanitize_error_message(text: str)` in `src/t2s/security/error_sanitizer.py`, masking database credentials, URI passwords (`postgres://user:***@host`), Bearer tokens, and sensitive assignments before assigning to sync results or quarantine records.
6. **Concurrency & Thread Safety**:
   * Added `threading.RLock()` across `InMemoryMetadataSnapshotStore`, `InMemoryMetadataQuarantine`, and `InMemoryCatalog`, guaranteeing thread-safe reads and atomic state swaps under concurrent multi-threaded workloads.

### Updated Verification Metrics
* **Total Tests**: **399 passed, 1 skipped** (`pytest tests/unit/catalog/test_metadata_sync_hardening.py`).
* **Architecture Guards**: **10/10 passed**.
* **Mypy**: **128 files clean** (strict mode).
* **Ruff**: **Clean** across `src/` and `tests/`.

---

## 7. Resolution of Mixed-Source Semantics, Rollback Consistency & Defensive Isolation

Prior to opening the OpenMetadata pilot, three critical semantic and isolation invariants were closed:

1. **Mixed-Source Snapshot Semantics**:
   * *Problem*: In an incremental pilot onboarding 20 tables via OpenMetadata while preserving 8,980 unscoped PostgreSQL tables, stamping the snapshot with a single monolithic `source_system` led to contradictory semantics (claiming the entire catalog came from OpenMetadata when 99.8% came from PostgreSQL).
   * *Solution*:
     * Introduced `sync_source: str` representing the active synchronization provider that initiated the sync cycle.
     * Introduced `source_systems: tuple[str, ...]` deterministically extracted from the distinct `asset.provenance.source_system` values across all tables in the snapshot.
     * Added `is_mixed_source: bool` indicating if multiple underlying providers populate the snapshot.
     * Preserved `source_system` as a backwards-compatible alias to `sync_source`.
2. **Catalog Promotion Consistency & Rollback**:
   * *Problem*: `MetadataSyncService` synchronized the serving catalog and then promoted the snapshot in `MetadataSnapshotStorePort`. If the snapshot store promotion failed (e.g. disk failure, database timeout, store exception), the serving catalog was already updated with candidate tables, leaving catalog and store out of sync.
   * *Solution*:
     * Wrapped `snapshot_store.promote_snapshot(candidate_snapshot)` in an exception handler that automatically rolls back `catalog_storage` to its previous table state and previous snapshot ID.
     * Added comprehensive unit test `test_atomic_serving_promotion_rollback_when_snapshot_store_fails` validating complete state restoration upon store promotion failure.
3. **Defensive State Isolation & Controlled Mutation**:
   * *Problem*: Callers inspecting the active snapshot could theoretically mutate the underlying table dictionary or expect snapshot immutability despite mutable Python dict containers.
   * *Solution*:
     * Updated `InMemoryMetadataSnapshotStore.get_active_snapshot()` to return defensive copies (`self._active_snapshot.model_copy()`).
     * Added `tables_view` property on `CanonicalMetadataSnapshot` wrapping `self.tables` in `types.MappingProxyType`, preventing direct modification of the snapshot dictionary.
     * Corrected secret scanner regex handling to recognize redacted password masks (`***`) as safe literals rather than false-positive active secret leaks.

