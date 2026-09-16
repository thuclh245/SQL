# Architecture & Implementation Report: MetadataProvider Abstraction + Controlled Metadata Scope

**Document ID**: `T2S-ARCH-METADATA-PROVIDER-2026-09`  
**System**: T2S / CHATSQL Text-to-SQL System  
**Status**: COMPLETE  
**Primary Repository**: `/home/thuclh245/MyCode/SQL`  
**Quality Gates**: Pytest: 364 passed, Ruff: Clean, Mypy: 120 files clean, Architecture Guards: 10/10 passed  

---

## 1. Current-State Audit

### Pre-Existing Architecture & Deficiencies
Prior to this implementation:
1. **Direct Manifest Loading**: `RuntimeFactory` directly invoked `_load_catalog_tables`, which parsed JSON manifests via `load_catalog_tables_from_manifest` or validated JSON lists.
2. **Coupling to Static Files**: Catalog metadata ingestion assumed static local JSON files as the sole acquisition mechanism.
3. **No Ingestion Boundary**: No provider-neutral contract existed between external data systems (such as relational databases, data warehouses, or external catalogs) and T2S canonical domain entities.
4. **No Controlled Onboarding Scope**: There was no mechanism to ingest a targeted pilot subset (e.g. 5–20 tables or selected business domains) without manually preparing separate static JSON files.
5. **Absence of Live Introspection**: There was no production PostgreSQL metadata provider capable of introspecting schema catalogs while guaranteeing zero N+1 database round trips.

---

## 2. Architectural Decisions

### Provider Boundary Architecture
```
                         External Metadata Sources
                 ┌───────────────────┴───────────────────┐
                 ↓                                       ↓
       PostgreSQL Introspection                     Static JSON
                 ↓                                       ↓
      PostgresMetadataProvider                StaticMetadataProvider
                 └───────────────────┬───────────────────┘
                                     ↓
                            MetadataProviderPort
                                     ↓
                               MetadataScope
                                     ↓
                         Canonical Validation Gate
                                     ↓
                           list[CatalogTable]
                                     ↓
                      InMemoryCatalog / Grounding
```

### Key Decisions: Observation → Constraint → Reasoning → Decision → Tradeoff

#### Decision 1: Single Provider Boundary (`MetadataProviderPort`)
* **Observation**: `RuntimeFactory` previously read static catalog files directly while `CatalogPort` acted as the storage/query repository.
* **Constraint**: Grounding and downstream retrieval must not care whether metadata came from static files, PostgreSQL, or a future external catalog.
* **Reasoning**: Ingestion/acquisition must be strictly separated from query/retrieval storage. `CatalogPort` answers *"Which metadata is relevant to this query?"* while `MetadataProviderPort` answers *"What metadata facts does this source expose?"*
* **Decision**: Establish `MetadataProviderPort` with a single acquisition contract: `fetch_metadata(scope: MetadataScope | None = None) -> list[CatalogTable]`.
* **Tradeoff**: Adding the provider boundary requires routing existing static loads through an adapter (`StaticMetadataProvider`), but unifies all acquisition pathways.

#### Decision 2: Synchronous Provider Protocol
* **Observation**: Application bootstrap, CLI tools, offline sync tasks, and database query executors in T2S are synchronous (with async execution offloaded via threads when called from FastAPI).
* **Constraint**: Metadata sync and bootstrap must operate reliably in CLI, batch pipelines, and test fixtures without requiring a running asyncio event loop.
* **Reasoning**: Forcing `async` onto `MetadataProviderPort` complicates offline batch sync, unit test harnesses, and CLI ingestion commands without providing concurrency benefits during bootstrap.
* **Decision**: Define `fetch_metadata` synchronously. Future asynchronous network providers (e.g. REST calls) can run synchronous HTTP clients or wrap async calls via thread pools.
* **Tradeoff**: Network I/O in providers is synchronous, but matches the existing synchronous database execution layer (`PostgresReadOnlyQueryExecutor`).

#### Decision 3: Provider-Neutral `MetadataScope` Separate from ACL
* **Observation**: Future onboarding of enterprise catalogs (~9,000 tables) requires incremental pilot rollouts (10–20 tables -> 50–200 tables -> full catalog).
* **Constraint**: `MetadataScope` must control catalog ingestion/acquisition only. It must NOT act as a runtime user access control list (ACL) or security policy.
* **Reasoning**: Conflating catalog ingestion with query-time user authorization violates the principle of separation of concerns. Ingestion filters what facts enter T2S; authorization policies filter what a specific user may query.
* **Decision**: Implement `MetadataScope` as a frozen Pydantic model with explicit database, schema, asset type, and include/exclude table matching semantics where **exclude always wins on conflict**.
* **Tradeoff**: Two distinct concepts (`MetadataScope` for ingestion vs `AuthorizationService` for query execution) exist, but architectural purity and security boundaries remain uncompromised.

---

## 3. Provider Contract

Defined in [`src/t2s/catalog/metadata_provider.py`](file:///home/thuclh245/MyCode/SQL/src/t2s/catalog/metadata_provider.py):

```python
class MetadataProviderPort(Protocol):
    """Provider boundary protocol for acquiring and canonicalizing metadata."""

    @property
    def source_system(self) -> str:
        """Identifier for the external source system (e.g. 'postgresql', 'static')."""
        ...

    def fetch_metadata(self, scope: MetadataScope | None = None) -> list[CatalogTable]:
        """Acquire, filter, normalize, and validate canonical table metadata."""
        ...
```

### Invariants:
1. **Pure Domain Entities**: Providers always return canonical `CatalogTable` domain objects, never provider-specific DTOs or raw database rows.
2. **Fail-Closed on Defect**: If source queries fail or canonical validation fails, the provider raises `MetadataCatalogError` or `MetadataMappingError`. Partial metadata is never silently returned.
3. **Deterministic Ordering**: Returned tables are sorted deterministically by canonical `table_fqn`.

---

## 4. MetadataScope Contract

Defined in [`src/t2s/catalog/metadata_scope.py`](file:///home/thuclh245/MyCode/SQL/src/t2s/catalog/metadata_scope.py):

### Fields:
* `database_names: frozenset[str] | set[str] | None = None`
* `schema_names: frozenset[str] | set[str] | None = None`
* `exclude_schemas: frozenset[str] | set[str] | None = None`
* `include_tables: frozenset[str] | set[str] | None = None`
* `exclude_tables: frozenset[str] | set[str] | None = None`
* `include_asset_types: frozenset[AssetType] | set[AssetType] | None = None`

### Evaluation Semantics:
1. **Default / None Semantics**: Any dimension left as `None` imposes no restriction (matches all business assets).
2. **Empty Set Semantics**: An inclusion filter explicitly provided as an empty set (`frozenset()`) matches zero assets.
3. **Deterministic Precedence**: **EXCLUDE WINS ON CONFLICT**. If a table matches both `include_tables` and `exclude_tables`, it is rejected.
4. **Pattern & FQN Support**: `include_tables` and `exclude_tables` support exact table names (`orders`), schema-qualified names (`sales.orders`), and standard glob patterns (`stg_*`, `tmp_*`, `dim_*`).
5. **Case & Unicode Fidelity**: Character case is strictly preserved, and full Unicode identifiers are supported.

---

## 5. PostgreSQL Metadata Provider

Implemented in [`src/t2s/catalog/postgres_metadata_provider.py`](file:///home/thuclh245/MyCode/SQL/src/t2s/catalog/postgres_metadata_provider.py):

### Metadata Capabilities:
* **Assets**: Discovers regular tables (`'r'`), views (`'v'`), materialized views (`'m'`), and partitioned tables (`'p'`).
* **Columns**: Captures exact declared ordinal positions, nullability (`True`, `False`, or `None`), native data types (via `format_type(atttypid, atttypmod)`), and normalized general types.
* **Constraints**:
  * **Primary Keys**: Single-column and composite PKs in exact declared key ordinal order.
  * **Foreign Keys**: Single-column, composite, and cross-schema FKs with exact local-to-remote column pairing in declared ordinal order.
* **Comments & Descriptions**: Table and column comments introspected from `pg_description` and mapped to `CatalogTable.description` and `CatalogColumn.description`.
* **System Schema Filtering**: Automatically excludes `pg_catalog`, `information_schema`, `pg_toast`, and temporary schemas (`pg_temp_%`, `pg_toast_temp_%`).

---

## 6. Query Strategy: Zero N+1 Queries

```text
metadata SQL queries per full fetch = 4
```

### Why Query Count is Invariant to Scale
Traditional naive metadata introspectors execute per-table queries:
$$1 \text{ (list tables)} + N \text{ (get columns)} + N \text{ (get PKs)} + N \text{ (get FKs)} = 1 + 3N \text{ queries}$$
For 9,000 tables, that amounts to **27,001 SQL round trips**, causing timeout failure and database thrashing.

`PostgresMetadataProvider` solves this through **4 bounded bulk SQL queries**:
1. **Query 1 (`SQL_RELATIONS`)**: Bulk query against `pg_class`, `pg_namespace`, and `pg_description` for all tables, views, and comments.
2. **Query 2 (`SQL_COLUMNS`)**: Bulk query against `pg_attribute`, `pg_class`, `pg_namespace`, `pg_type`, and `pg_description` for all active columns and comments.
3. **Query 3 (`SQL_PRIMARY_KEYS`)**: Bulk query against `pg_constraint` unnesting `conkey WITH ORDINALITY` to extract all primary keys in declared order.
4. **Query 4 (`SQL_FOREIGN_KEYS`)**: Bulk query against `pg_constraint` unnesting `(conkey, confkey) WITH ORDINALITY` to pair foreign key columns in declared order.

### Linear Memory Assembly: $O(\text{records})$
The provider indexes result rows in memory using hash tables (`(schema_name, table_name) -> list[...]`), avoiding quadratic scans. In synthetic testing with **9,000 tables and 50,000+ columns**, total assembly completed in **0.29 seconds** with exactly 4 metadata queries executed.

---

## 7. Static Provider & Backward Compatibility

Implemented in [`src/t2s/catalog/static_metadata_provider.py`](file:///home/thuclh245/MyCode/SQL/src/t2s/catalog/static_metadata_provider.py):
* Wraps existing `load_catalog_tables_from_manifest` and direct JSON file parsers.
* Applies `MetadataScope` filtering.
* Enforces canonical domain invariants via `CatalogTable.model_validate`.
* Preserves 100% backward compatibility for all existing configuration flags (`RUNTIME_CATALOG_TABLES_PATH`, `RUNTIME_CATALOG_DATABASE_ID`).

---

## 8. Runtime Integration

### Before:
```python
# runtime_factory.py directly parsed files:
catalog_tables = _load_catalog_tables(settings, catalog_tables_path)
catalog = InMemoryCatalog()
catalog.upsert_tables(catalog_tables)
```

### After:
```python
# runtime_factory.py uses provider abstraction:
provider = MetadataProviderFactory.create_provider(settings)
catalog_tables = provider.fetch_metadata()
catalog = InMemoryCatalog()
catalog.upsert_tables(catalog_tables)

# Compatibility helper also routes through the provider:
def _load_catalog_tables(settings: Settings, catalog_tables_path: Path) -> list[CatalogTable]:
    provider = StaticMetadataProvider(
        catalog_tables_path=catalog_tables_path,
        database_id=settings.runtime_catalog_database_id,
    )
    return provider.fetch_metadata()
```

---

## 9. Security & Read-Only Invariants

1. **Read-Only Transactions**: `PostgresMetadataProvider` executes:
   ```sql
   SET TRANSACTION READ ONLY;
   SET LOCAL statement_timeout = 30000;
   ```
   Ensuring metadata acquisition can never execute DDL or DML mutations.
2. **Automatic Rollback & Cleanup**: All sessions are rolled back and connections closed in `finally` blocks.
3. **No Secret Leakage**: Database URLs and credentials are never logged or stored in canonical metadata models.

---

## 10. Controlled Pilot Readiness

The architecture enables seamless staged onboarding for large catalogs (e.g. 9,000 tables) without altering provider interfaces or downstream Grounding contracts:

```python
# Stage A: 5-20 Representative Tables Pilot
pilot_scope = MetadataScope(
    schema_names={"analytics"},
    include_tables={"dim_customers", "fct_orders", "dim_products"},
)
tables = provider.fetch_metadata(scope=pilot_scope)

# Stage B: Domain Expansion (50-200 Tables)
domain_scope = MetadataScope(
    schema_names={"analytics", "finance"},
    exclude_tables={"*_stg", "tmp_*"},
)
tables = provider.fetch_metadata(scope=domain_scope)

# Stage C: Full Production Catalog
full_scope = MetadataScope()
tables = provider.fetch_metadata(scope=full_scope)
```

---

## 11. Verification Results & Quality Gates

### Automated Test Suite
* **`tests/unit/catalog/test_metadata_scope.py`** (10 passed): Default scope, schema inclusion/exclusion, exclude-precedence, glob patterns, case sensitivity, Unicode support, empty sets, and fail-fast validation.
* **`tests/unit/catalog/test_static_metadata_provider.py`** (8 passed): Manifest loading, JSON loading, scope filtering, preloaded tables, error propagation, deterministic sorting, and structural validation.
* **`tests/unit/catalog/test_postgres_metadata_provider.py`** (8 passed): Multi-schema discovery, system schema exclusion, views/materialized views, column order, native vs normalized types, nullability tri-state, composite PK/FK, cross-schema FK, descriptions, read-only transaction enforcement, and semantic hash stability.
* **`tests/unit/catalog/test_postgres_metadata_scale.py`** (1 passed): 9,000 synthetic tables scale verification proving strictly bounded query count ($N=4$) and linear in-memory assembly under 0.3s.
* **`tests/unit/catalog/test_metadata_provider_factory.py`** (7 passed): Explicit provider selection, backward compatibility fallback, missing configuration errors, unsupported provider rejection.
* **`tests/unit/bootstrap/test_runtime_factory.py`** (9 passed): All runtime factory bootstrap tests continue to pass without regression.
* **Total Project Tests**: **364 passed, 1 skipped** in 11.23s.

### Static Analysis
* **Ruff**: `All checks passed!`
* **Mypy**: `Success: no issues found in 120 source files`
* **Architecture Hygiene Guards**: `10 passed in 0.20s` (Guards 1–10 pass cleanly with 0 phase names, 0 benchmark tokens, and 0 boundary violations).

### External API Invocations
* **Paid LLM Calls**: Exactly 0.

---

## 12. Recommended Next Capability

```text
METADATA_SYNC_AND_VALIDATION_LAYER
```
This next capability will establish scheduled incremental synchronization, drift detection between source catalogs and stored canonical models, and automated health checks over canonical metadata graphs.
