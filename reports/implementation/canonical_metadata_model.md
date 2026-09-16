# Canonical Metadata Model Foundation — Implementation Report

## 1. Executive Summary

This report documents the architectural design, implementation, verification, and independent review of the **Canonical Metadata Model** for the T2S Text-to-SQL system.

The canonical metadata model serves as the provider-neutral, immutable domain contract defining catalog entities (tables, views, columns, keys, business semantics, and provenance). It completely decouples downstream components (Grounding, Retrieval, Relationship Expansion, Solvers, Verification) from external catalog products (OpenMetadata, PostgreSQL catalog introspection, static JSON manifests, or future platforms like DataHub and dbt).

---

## 2. Current-State Audit

Prior to this implementation, metadata concepts were centered on `src/t2s/catalog/catalog_models.py`, which defined `CatalogTable`, `CatalogColumn`, `CatalogForeignKey`, and `MetadataSnapshot`.

### Findings from Codebase Audit
1. **Core Domain Alignment**: Existing models were already domain-focused rather than benchmark- or retrieval-polluted (e.g. no BM25 scores, embedding vectors, or gold SQL leaked into `CatalogTable`).
2. **Provider Coupling**: `RelationshipProvenance` explicitly included `"openmetadata_relationship"`, violating provider neutrality in the core domain model.
3. **Lossy Type Modeling**: `CatalogColumn` modeled only `data_type: str`, destroying source fidelity by not separating native source types (e.g. `NUMERIC(18, 4)`) from canonical normalized types (e.g. `DECIMAL`).
4. **Missing Governance Semantics**: `CatalogTable` lacked a `domain` attribute for business domain categorization.
5. **Flattened Provenance**: Provenance was scattered as ad-hoc optional fields (`source_entity_id`, `metadata_version`, `updated_at`) rather than a structured, reusable provenance abstraction.
6. **Incomplete Validation Invariants**: Foreign keys permitted unequal column cardinality (`len(from) != len(to)`); tables permitted duplicate column names; declared primary keys were not validated against declared columns.
7. **Identity Structuring**: Data asset identity was flat without a structured `AssetIdentity` value object.
8. **Immutability**: Models were mutable Pydantic `BaseModel` instances without frozen configuration, risking accidental mutation during grounding passes.

---

## 3. Design Decision: Approach A — `EVOLVE_EXISTING_MODEL`

### Rationale
- **Observation**: `CatalogTable`, `CatalogColumn`, and `CatalogForeignKey` were already used as domain models across `CatalogPort`, `GroundingContextBuilder`, `RelationshipGraph`, `CatalogSearchDocumentBuilder`, `RuntimeFactory`, and `OpenMetadataTableMapper`.
- **Constraint**: Strict runtime compatibility must be maintained across all 307 existing unit and integration tests. Introducing a separate model hierarchy (e.g. `CanonicalTable` alongside `CatalogTable`) would create two competing concepts of table metadata and necessitate fragile, redundant mapping layers, violating Prompt Section 9 (*"Do NOT create a second parallel model hierarchy unnecessarily"*) and Section 10 (*"Do NOT maintain two competing concepts called 'table metadata' without a clearly documented boundary"*).
- **Decision**: Evolve the existing domain model into the canonical contract under `src/t2s/catalog/canonical_metadata.py`. Re-export these canonical models via `src/t2s/catalog/catalog_models.py` and `src/t2s/catalog/__init__.py` to provide 100% backward compatibility with zero duplicate abstractions.

---

## 4. Canonical Metadata Contract

The canonical foundation is implemented in `src/t2s/catalog/canonical_metadata.py`:

```text
               ┌──────────────────────────┐
               │      AssetIdentity       │
               │ (service, db, schema,    │
               │  asset_name, asset_type, │
               │  canonical_fqn)          │
               └─────────────▲────────────┘
                             │
               ┌─────────────┴────────────┐
               │       CatalogTable       │
               │ (table_fqn, description, │
               │  domain, owner, tags,    │
               │  glossary_terms,         │
               │  sql_identifier, ...)    │
               └──────┬──────┬─────┬──────┘
                      │      │     │
         ┌────────────┘      │     └────────────┐
         ▼                   ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌────────────────────┐
│  CatalogColumn  │ │CatalogForeignKey│ │ MetadataProvenance │
│ (native_type,   │ │ (from/to fqns,  │ │ (source_system,    │
│  data_type,     │ │  from/to cols,  │ │  source_entity_id, │
│  is_nullable,   │ │  equal card.)   │ │  source_version,   │
│  ordinal_pos)   │ └─────────────────┘ │  source_updated_at)│
└─────────────────┘                     └────────────────────┘
```

### Core Entities and Value Objects
1. **`AssetType` & `AssetIdentity`**:
   - Structured asset locator capturing `service_name`, `database_name`, `schema_name`, `asset_name`, `asset_type` (`table`, `view`, `materialized_view`, `external`, `unknown`), and `canonical_fqn`.
   - Never naively concatenates or splits strings with dots; preserves case and Unicode.
2. **`CatalogColumn`**:
   - Captures `column_name`, `data_type` (general/normalized), `native_type` (source dialect type), `description`, `is_nullable` (tri-state: `True`, `False`, or `None` for uncertainty), `is_primary_key`, `ordinal_position`, `tags`, and `glossary_terms`.
   - Preserves source fidelity without crashing on unknown/extension types (e.g. `GEOMETRY`, `JSONB`, `VECTOR`).
3. **`CatalogForeignKey`**:
   - Represents declared structural constraints: `from_table_fqn`, `from_column_names`, `to_table_fqn`, `to_column_names`, `relationship_name`, and provider-neutral `provenance` (`"declared_foreign_key"`).
   - Enforces strict equal cardinality: `len(from_column_names) == len(to_column_names) > 0`.
4. **`MetadataProvenance`**:
   - Fully provider-neutral source tracing: `source_system`, `source_entity_id`, `source_version`, `source_updated_at`, `snapshot_at`.
   - Contains zero operational secrets, credentials, or provider-specific IDs.
5. **`CatalogTable`**:
   - Root canonical entity composing `AssetIdentity`, `columns`, `primary_key_column_names`, `foreign_keys`, business metadata (`domain`, `owner`, `tags`, `glossary_terms`), `sql_identifier`, and `provenance`.
   - Frozen/immutable (`frozen=True`) with deterministic JSON serialization and content hashing via `compute_content_hash()`.

---

## 5. Explicitly Excluded Concepts

The canonical model strictly represents **known metadata facts**. The following concepts are explicitly excluded:
- **Retrieval Signals**: No `embedding`, `vector`, `bm25_score`, `dense_score`, or search index IDs.
- **Heuristic Relationships**: No semantic join inference, LLM guesses, query-history edges, or lineage graphs.
- **Provider Infrastructure**: No OpenMetadata REST payloads, Postgres OIDs, or HTTP hrefs.
- **Benchmark & Evaluation**: Zero benchmark tokens, gold SQL, candidate SQL, or execution scores.

---

## 6. Provider Independence

Future metadata sources integrate into T2S via dedicated adapters that output canonical metadata:

```text
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│  PostgreSQL Connection  │     │   OpenMetadata Client   │     │   JSON / Manifest File  │
└───────────┬─────────────┘     └───────────┬─────────────┘     └───────────┬─────────────┘
            │                               │                               │
            ▼                               ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│ PostgresCatalogAdapter  │     │ OpenMetadataTableMapper │     │ SchemaManifestLoader    │
└───────────┬─────────────┘     └───────────┬─────────────┘     └───────────┬─────────────┘
            │                               │                               │
            └───────────────────────────────┼───────────────────────────────┘
                                            ▼
                           ┌─────────────────────────────────┐
                           │    CANONICAL METADATA MODEL     │
                           │   (src/t2s/catalog/canonical)   │
                           └────────────────┬────────────────┘
                                            │
                                            ▼
                           ┌─────────────────────────────────┐
                           │    Grounding / Retrieval /      │
                           │    Relationship / Solvers       │
                           └─────────────────────────────────┘
```

Neither Grounding nor Solvers know which catalog provider supplied the metadata.

---

## 7. Compatibility & Preservation

1. **Backwards-Compatible Imports**: `src/t2s/catalog/catalog_models.py` re-exports all canonical classes. Any existing caller importing from `t2s.catalog.catalog_models` or `t2s.catalog` functions identically.
2. **Legacy Field Mapping**: `CatalogTable` accepts legacy flat fields (`source_entity_id`, `metadata_version`, `updated_at`) and harmonizes them into `provenance: MetadataProvenance`.
3. **Test Invariance**: All 307 existing unit and integration tests pass without modification.

---

## 8. Validation Invariants & Hardening Guarantees

The model prevents invalid states through strict domain validation:
- **Identifier Non-Emptiness**: Blank or whitespace-only names for services, databases, schemas, tables, and columns are rejected.
- **Duplicate Column Definitions**: Multiple columns with the same name within a single table raise a `ValueError`.
- **Foreign Key Cardinality**: Foreign keys with mismatched local vs remote column counts raise a `ValueError`.
- **Foreign Key Non-Emptiness**: Foreign keys with empty column lists raise a `ValueError`.
- **Referential Integrity on Declared Keys**: When columns are specified, declared primary keys and outgoing foreign keys must reference valid declared column names.
- **Unicode & Case Preservation**: Real-world identifiers containing Unicode characters (e.g. Vietnamese diacritics), mixed casing, spaces, or special characters are preserved without destructive normalization.
- **Provenance Conflict Rejection (Condition 2 Hardening)**: Passing both legacy fields (`source_entity_id`, `metadata_version`, `updated_at`) and structured `provenance: MetadataProvenance` with conflicting values raises an explicit `ValidationError` rather than silently favoring one.
- **Pure Semantic Content Hashing (Condition 1 Hardening)**: `compute_content_hash()` and `semantic_content_hash` hash strictly semantic metadata (identity, columns, types, descriptions, constraints, business tags/glossary, domain, owner, SQL identifier) while completely excluding operational observation/freshness fields (`provenance`, `source_entity_id`, `metadata_version`, `updated_at`). Change detection is invariant to sync timestamps (`snapshot_at`, `updated_at`) or source version strings.
- **Deterministic Canonical FQN Semantics (Condition 3 Hardening)**: `AssetIdentity` enforces that `canonical_fqn` represents the internal T2S canonical locator (`<service>.<database>.<schema>.<asset>`), with deterministic helper `AssetIdentity.build_canonical_fqn(...)` and `AssetIdentity.from_parts(...)`. Opaque provider locators (OpenMetadata REST FQN, Postgres OID) are strictly isolated into `MetadataProvenance.source_entity_id`.

---

## 9. Comprehensive Synthetic Test Suite

Added in `tests/unit/catalog/test_canonical_metadata.py` (22 tests total):
1. `test_asset_identity_table_and_view`: Verifies structured table and view identity.
2. `test_asset_identity_preserves_case_and_unicode`: Verifies mixed-case identifiers and Vietnamese Unicode descriptions.
3. `test_column_model_preserves_native_and_canonical_types`: Tests native dialect type alongside canonical normalized type.
4. `test_column_model_supports_unknown_and_custom_types`: Verifies unknown source types do not crash validation.
5. `test_column_nullability_represents_uncertainty`: Validates tri-state nullability (`True`, `False`, `None`).
6. `test_single_and_composite_primary_keys`: Verifies composite primary key order preservation.
7. `test_foreign_key_composite_and_cross_schema`: Tests composite FKs and cross-schema references.
8. `test_foreign_key_cardinality_mismatch_rejected`: Verifies rejection of unequal FK column cardinality.
9. `test_foreign_key_empty_columns_rejected`: Verifies rejection of empty FK column lists.
10. `test_business_metadata_tags_glossary_domain_owner`: Validates tags, glossary terms, domain, and owner.
11. `test_provenance_provider_independence`: Tests provenance with a synthetic provider name (`synthetic_enterprise_catalog_v2`).
12. `test_validation_rejects_empty_identifiers`: Verifies blank/whitespace identifiers are rejected.
13. `test_validation_rejects_duplicate_columns`: Verifies duplicate column names in tables are rejected.
14. `test_validation_rejects_undefined_primary_key_column`: Verifies undefined PK columns are rejected.
15. `test_validation_rejects_undefined_foreign_key_local_column`: Verifies undefined local FK columns are rejected.
16. `test_immutability_prevents_accidental_mutation`: Verifies frozen model mutation rejection.
17. `test_round_trip_json_serialization`: Verifies Model → JSON → Model semantic equality and content hash matching.
18. `test_metadata_snapshot_telemetry`: Verifies metadata sync tracking records.
19. `test_content_hash_invariance_to_operational_and_sync_fields`: Verifies content hash is invariant across sync timestamps and versions, but sensitive to semantic schema changes.
20. `test_provenance_conflict_rejection`: Verifies conflicting legacy and provenance fields raise `ValidationError`.
21. `test_provenance_matching_values_accepted`: Verifies matching legacy and provenance fields are harmonized cleanly.
22. `test_asset_identity_deterministic_fqn_construction`: Verifies deterministic canonical FQN building and empty path segment rejection.

---

## 10. Quality Gates & Architecture Hygiene

### Test Suite Execution
- `pytest`: **329 passed in 4.61s** (307 existing baseline + 22 new canonical metadata tests).

### Static Analysis
- `ruff check src tests`: **PASS** (0 errors, clean).
- `mypy`: **PASS** (Success: no issues found in 115 source files).

### Architecture Hygiene Guards (Guards 1-10)
- `tests/unit/architecture/test_architecture_hygiene_guards.py`: **10 passed in 0.20s**.
  - Guard 1 (Zero phase names in production): **PASS**
  - Guard 2 (Zero benchmark tokens in runtime): **PASS**
  - Guard 3 (Direct dependency boundaries): **PASS**
  - Guard 4 (Transitive runtime boundaries): **PASS**
  - Guard 5 (Gold field isolation): **PASS**
  - Guard 6 (Prompt hygiene): **PASS**
  - Guard 7 (Secret scanning across tracked files): **PASS**
  - Guard 8 (Zero case IDs in production): **PASS**
  - Guard 9 (Historical artifact isolation): **PASS**
  - Guard 10 (Production path neutrality): **PASS**

### External API Calls
- Paid external calls: **0**
- Database mutations: **0**

---

## 11. Known Limitations

1. **Table Column Ordering Enforcement**: While `ordinal_position` is preserved on columns, tables with partially defined ordinal positions preserve declaration order without re-indexing gaps.
2. **Dialect Quoting Strategy**: The canonical model preserves exact unquoted identifier strings; dialect-specific quoting (e.g. double quotes for Postgres, backticks for SQLite) remains the responsibility of the SQL generation/dialect layer.

---

## 12. Recommended Next Capability

The next logical capability to implement is the **`MetadataProvider` Abstraction**:
- Establish a provider port: `MetadataProviderPort` (`fetch_metadata() -> list[CatalogTable]`).
- Implement the PostgreSQL Introspection provider (`PostgreSqlMetadataProvider`) adapting database catalogs directly into the canonical metadata model.
- Implement provider caching and incremental sync via `MetadataSnapshot`.
