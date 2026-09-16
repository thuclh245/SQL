# Architecture & Implementation Report: OpenMetadata Provider Controlled Pilot

**Document ID**: `T2S-ARCH-OPENMETADATA-PILOT-2026-09`  
**System**: T2S / CHATSQL Text-to-SQL System  
**Implementation Status**: COMPLETE  
**Live Pilot Status**: BLOCKED_NO_INSTANCE  
**Primary Repository**: `/home/thuclh245/MyCode/SQL`  
**Quality Gates**: Pytest: 415 passed, 2 skipped, Ruff: Clean, Mypy: 129 package files + 4 test suites clean, Architecture Guards: 10/10 passed, Security Audit: 12/12 passed  
**Paid External LLM Calls**: 0  

---

## 1. Current State

Prior to this pilot implementation, the T2S platform established:
1. **Canonical Metadata Model**: Immutable, provider-neutral domain representations (`CatalogTable`, `CatalogColumn`, `CatalogForeignKey`, `AssetIdentity`, `MetadataProvenance`).
2. **Metadata Provider Abstraction**: `MetadataProviderPort` with `StaticMetadataProvider` and `PostgresMetadataProvider`.
3. **Metadata Sync, Reconciliation, Validation & LKG Layer**: Controlled scope filtering, multi-severity validation, quarantine isolation, Last-Known-Good preservation, mixed-source snapshot provenance, and atomic catalog rollback.

However, external catalog ingestion was restricted to static JSON files and direct PostgreSQL catalog introspection. To onboard enterprise metadata catalogs without coupling downstream Text-to-SQL reasoning to external APIs, an OpenMetadata provider capability was required.

---

## 2. Architecture Decision: REST Client vs Official SDK

### Decision: Dedicated REST Client via `httpx`

* **Observation**: The official `openmetadata-ingestion` SDK is designed primarily for *pushing* metadata from databases into OpenMetadata. It pulls hundreds of transitive dependencies (SQLAlchemy dialects, Great Expectations, Confluent Kafka, PySpark, Airflow hooks), totaling hundreds of megabytes.
* **Dependency Cost & Attack Surface**: Installing `openmetadata-ingestion` would severely bloat the runtime environment and violate strict dependency boundaries.
* **Existing Runtime Stack**: The repository already includes `httpx>=0.27,<1.0` as a core runtime dependency.
* **Required API Surface**: T2S requires read-only ingestion (`GET` operations only) across 2 endpoints:
  - `GET /api/v1/tables` (paginated list with cursor)
  - `GET /api/v1/tables/name/{fqn}` (direct entity retrieval by FQN)
* **Decision**: Implement a lightweight, resilient REST client (`OpenMetadataClient`) using `httpx.Client`. It provides zero added dependencies, deterministic HTTP transport mocking (`httpx.MockTransport`), bounded timeouts, conservative retry with exponential backoff, and full error sanitization.

---

## 3. API Compatibility & Target Server Capabilities

* **Target Server Version**: `UNKNOWN` (no live enterprise instance reachable in current environment).
* **API Compatibility Baseline**: OpenMetadata REST API v1 entity specification.
* **Endpoints Used**:
  - `GET /api/v1/tables/name/{fqn}`
  - `GET /api/v1/tables`
* **Requested Entity Fields**:
  - `columns,tags,owner,domain,tableConstraints,database,databaseSchema,service,extension`
* **Defensive Schema Parsing**: Optional fields (e.g. `domain`, `owner`, `tags`, `glossaryTerms`, `extension`) are tolerated as absent without crashing ingestion.

---

## 4. Provider Contract

`OpenMetadataProvider` implements `MetadataProviderPort` directly without creating any provider-specific sub-interfaces:

```python
class OpenMetadataProvider(MetadataProviderPort):
    @property
    def source_system(self) -> str:
        return "openmetadata"

    def fetch_metadata(self, scope: MetadataScope | None = None) -> list[CatalogTable]:
        ...
```

Downstream consumers (`GroundingEngine`, `RelationshipGraph`, `InMemoryCatalog`, `Solver`, `Verification`) remain 100% agnostic to OpenMetadata.

---

## 5. Scope Translation & Acquisition Modes

`OpenMetadataProvider` supports two distinct acquisition modes:

1. **Exact Pilot FQN Mode (Target Pilot: 5–20 Assets)**:
   - When exact FQNs are configured via `Settings.openmetadata_pilot_fqns` or `scope.include_tables` containing dotted canonical locators, the provider issues direct `GET /api/v1/tables/name/{fqn}` requests.
   - **Completeness Invariant**: If 20 assets are requested and 1 fails due to transport or server error, the entire operation aborts. Partial metadata is never returned, preventing accidental false deletions during reconciliation.
2. **Scoped Paginated Mode (Broader Schemas)**:
   - When `scope.database_names` or `scope.schema_names` specifies exact names without wildcards, the provider pushes these down to `database` and `databaseSchema` query parameters on `GET /api/v1/tables`.
   - **Defense-in-Depth Post-Filtering**: All mapped canonical tables are validated through `scope.matches_table(...)` after acquisition to ensure zero out-of-scope assets leak through.

---

## 6. Pilot Safety & Cardinality Guards

* **Pilot Asset Limit**: Configured via `Settings.openmetadata_max_assets` (default `25` assets for pilot).
* **Fail-Closed Cardinality Enforcement**: If OpenMetadata returns more than `max_assets`, the provider raises `MetadataCardinalityLimitExceededError` immediately. **It never silently truncates results**, as truncation would cause reconciler to falsely mark missing assets as `DELETED`.
* **Pagination Page Cap**: `max_pages = 10` prevents infinite pagination loops on broken cursors.
* **Full-Catalog Protection**: The existing `allow_full_catalog_sync=False` gate in `MetadataSyncService` remains active and default. Unrestricted scopes without filters fail closed.

---

## 7. API Requests & Authentication

* **HTTP Operations**: Strictly `GET` requests. Zero write methods (`POST`, `PUT`, `PATCH`, `DELETE`).
* **Authentication**: Bearer token authentication via HTTP header `Authorization: Bearer <token>`.
* **Secret Protection**:
  - `openmetadata_auth_token` is excluded from string representations (`repr(client)` masks the token as `***`).
  - All exception messages from the transport layer pass through `sanitize_error_message()`, stripping credentials and tokens before reaching logs or results.
* **TLS Verification**: Default enabled (`verify=True`).

---

## 8. Pagination & Completeness

* **Mechanism**: OpenMetadata cursor pagination using `paging.after`.
* **Completeness Guarantee**:
  - Each page must succeed. If any intermediate page fails, the entire batch fails; no partial pages are merged.
  - Pagination halts when `paging.after` is absent or empty.

---

## 9. Canonical Mapping Matrix

| OpenMetadata Field | Canonical T2S Attribute | Mapping Behavior |
|---|---|---|
| `service.name` | `AssetIdentity.service_name` | Extracted from structured entity reference or fallback FQN. |
| `database.name` | `AssetIdentity.database_name` | Extracted from structured entity reference or fallback FQN. |
| `databaseSchema.name` | `AssetIdentity.schema_name` | Extracted from structured entity reference or fallback FQN. |
| `name` / `displayName` | `AssetIdentity.asset_name` | Cleaned table name. |
| Deterministic Locator | `CatalogTable.table_fqn` | Constructed via `AssetIdentity.from_parts()`. Source FQN is NOT blindly used as canonical FQN. |
| `id` (UUID) | `MetadataProvenance.source_entity_id` | Preserved for external traceability. |
| `version` | `MetadataProvenance.source_version` | Stringified version. |
| `updatedAt` | `MetadataProvenance.source_updated_at` | Converted from millisecond epoch to UTC datetime. |
| `tableType` | `CatalogTable.table_type` | `Regular` $\rightarrow$ `table`, `View` $\rightarrow$ `view`, `MaterializedView` $\rightarrow$ `materialized_view`, `External` $\rightarrow$ `external`, unknown $\rightarrow$ `unknown`. |
| `description` | `CatalogTable.description` | Preserved verbatim (including Markdown formatting). |
| `columns[].name` | `CatalogColumn.column_name` | Normalized column name. |
| `columns[].dataType` | `CatalogColumn.data_type` | Standard normalized data type string. |
| `columns[].dataTypeDisplay` | `CatalogColumn.native_type` | Source database native type fidelity. |
| `columns[].isNullable` / constraint | `CatalogColumn.is_nullable` | `False` if `NOT_NULL`/`PRIMARY_KEY`, `True` if `isNullable: True`, `None` if unknown. |
| `tableConstraints` (PK) | `CatalogTable.primary_key_column_names` | Declared PK columns (single or composite). |
| `tableConstraints` (FK) | `CatalogTable.foreign_keys` | Declared structural FKs with structured target coordinates (`to_schema_name`, `to_table_name`, etc.). |
| `tags` (source="Tag") | `CatalogTable.tags` | Deduplicated list of tag FQNs/names. |
| `tags` (source="Glossary") | `CatalogTable.glossary_terms` | Deduplicated list of glossary terms. |
| `owner` | `CatalogTable.owner` | Extracted owner name string. |
| `domain` | `CatalogTable.domain` | Extracted domain name string. |

---

## 10. Unsupported & Deferred Metadata

The pilot strictly avoids non-structural and high-risk metadata:
* **Lineage**: Deferred. Lineage represents data flow, NOT declared relational foreign keys.
* **Sample Data / Row Profiles**: Prohibited during pilot. Metadata ingestion must never pull customer row data or PII values.
* **Usage / Query History**: Deferred.
* **Join Suggestions**: Deferred.

---

## 11. Source Transition & Mixed-Source Snapshots

* **Source Transition**: When a table previously ingested via `postgresql` is synced via `openmetadata` with identical table content, `MetadataSyncService` recognizes the authority transition, promotes a new active snapshot, and updates asset provenance to `source_system = "openmetadata"`.
* **Mixed-Source Snapshot**: In an incremental pilot where 2 tables are onboarded from OpenMetadata while 3 existing PostgreSQL tables are outside the pilot scope, the reconciler preserves the PostgreSQL tables. The promoted snapshot sets `is_mixed_source = True`, with `source_systems = ("openmetadata", "postgresql")` and preserved per-asset provenance.
* **LKG Resilience**: If OpenMetadata returns an error (HTTP 401, 403, 500, or connection timeout), `MetadataSyncService` marks the sync as `FAILED` and leaves the active LKG snapshot 100% untouched.

---

## 12. Verification & Quality Gates

### Test Suites
1. `tests/unit/catalog/test_openmetadata_provider.py` (8 unit tests):
   - Exact pilot FQN direct retrieval.
   - Partial transport failure aborting acquisition.
   - Cardinality guard enforcement (`max_assets`).
   - Comprehensive canonical mapping fidelity (types, nullability, PK, composite FK, Markdown, Unicode).
   - Unknown table type graceful fallback.
   - Source authority transition in sync service.
   - Mixed-source snapshot provenance preservation.
   - Provider failure preserving active LKG.
2. `tests/unit/integrations/openmetadata/test_openmetadata_client.py` (10 unit tests):
   - Multi-page cursor pagination.
   - Bearer auth header injection and repr token masking.
   - 401 Unauthorized / 403 Forbidden / 404 Entity Not Found handling.
   - 429 Too Many Requests retry with exponential backoff.
   - Cardinality limit exceeded failure.
   - Page limit exceeded failure.
   - Non-JSON payload handling.
3. `tests/unit/integrations/openmetadata/test_table_mapper.py` (4 unit tests):
   - Canonical 4-segment FQN construction and SQL identifier preservation.
   - Composite foreign key mapping with structured coordinates.
   - Missing SQL identifier marked unresolved.
   - Incomplete table identity fail-closed rejection.
4. `tests/unit/catalog/test_metadata_provider_factory.py` (9 unit tests):
   - Explicit creation of `static`, `postgres`, and `openmetadata` providers.
   - Missing configuration validation.

### Quality Gate Results
```bash
$ .venv/bin/pytest
415 passed, 2 skipped in 6.06s

$ .venv/bin/pytest tests/unit/architecture/test_architecture_hygiene_guards.py -v
10 passed in 0.26s

$ .venv/bin/pytest tests/unit/security/test_audit_engine.py -v
12 passed in 0.88s

$ .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
All checks passed! 195 files already formatted.

$ .venv/bin/mypy
Success: no issues found in 129 source files
```

---

## 13. Live Pilot Status

```text
IMPLEMENTATION_STATUS = COMPLETE
CONTRACT_TESTS_STATUS = PASS
LIVE_PILOT_STATUS = BLOCKED_NO_INSTANCE
```

* **Reason**: Environment variables `OPENMETADATA_URL` and `OPENMETADATA_AUTH_TOKEN` are not configured in the execution environment. Per safety rules, no live server connectivity was fabricated.
* **Readiness**: As soon as a target OpenMetadata base URL and read-only service token are supplied, the provider is fully equipped to execute a 5–20 table controlled pilot immediately.

---

## 14. Remaining Risks & Recommended Next Capability

### Real Remaining Risks
1. **Target OpenMetadata Version Divergence**: Public OpenMetadata releases (v1.0 through v1.5+) have minor schema evolutions in how `tableConstraints` and custom tags are structured. While our mapper tolerates missing fields, live verification on the target corporate instance will confirm exact constraint representation.
2. **Complex / Quoted Identifiers**: Schemas with embedded dots or special characters rely on our structured coordinate parser.

### Recommended Next Capability

> **`METADATA_RETRIEVAL_FOUNDATION`**

* **Rationale**: The core metadata ingestion pipeline is now complete and proven across all three provider tiers (`static`, `postgres`, `openmetadata`), with robust reconciliation, validation, LKG preservation, and mixed-source handling. The natural next production capability is indexing these canonical metadata snapshots into the retrieval layer (BM25 / vector search) so that the Text-to-SQL grounder can dynamically discover relevant tables and columns for incoming queries. Once retrieval is established, expanding the OpenMetadata pilot from 20 to 100+ tables can be evaluated with full end-to-end Text-to-SQL grounding verification.
