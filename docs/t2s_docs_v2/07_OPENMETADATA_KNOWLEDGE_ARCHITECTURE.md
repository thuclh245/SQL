# 07 — OpenMetadata Knowledge Architecture

**Version:** 2.0

---

## 1. Role

OpenMetadata is the enterprise metadata / knowledge source of truth.

T2S consumes metadata to build question-specific grounding context.

---

## 2. Ownership boundary

### OpenMetadata owns

- service/database/schema/table/column metadata,
- descriptions,
- PK/FK,
- tags,
- glossary,
- owners,
- lineage,
- profile information,
- usage/query-history metadata where available.

### T2S owns

- question-specific retrieval,
- table/column ranking,
- relationship expansion,
- grounding budget,
- context serialization,
- capability certification,
- SQL generation/verification/execution policy.

---

## 3. Derived projection

T2S may maintain a read-only derived projection for latency and grounding quality.

Example derived fields:

```text
entity_fqn
entity_type
description
column_type
pk_fk
relationship_provenance
glossary_refs
profile_refs
metadata_version
last_synced_at
```

Projection is not the source of truth.

---

## 4. Synchronization

Recommended pipeline:

```text
OpenMetadata
→ metadata sync worker
→ canonical projection
→ retrieval index
→ grounding runtime
```

Requirements:

- idempotent sync,
- version/freshness markers,
- deletion handling,
- schema drift detection,
- stale projection alarms.

---

## 5. Glossary / profile / usage

These sources are optional evidence inputs and must be capability-governed.

Do not automatically treat usage frequency as semantic truth.

---

## 6. OpenMetadata integration readiness checklist

- [ ] connection configured
- [ ] token stored securely
- [ ] table/column ingestion verified
- [ ] PK/FK ingestion verified
- [ ] metadata versioning verified
- [ ] ACL/visibility mapping defined
- [ ] glossary ownership defined
- [ ] profiler/sample usage policy defined
- [ ] sync observability enabled
- [ ] stale metadata behavior defined

