# 12 — Glossary, ADR and Decision Log

**Version:** 2.0

---

## 1. Glossary

### MG0
Current deployable grounding baseline: SchemaRetriever + RelationshipExpander + GroundingBudget + S0 serializer.

### MG*
Certified composition of MG0 plus only evidence-approved grounding capabilities.

### OR*
Offline oracle diagnostic with the same evidence types as MG*, but oracle-perfect relevance selection.

### Grounding
Process of selecting and packaging legitimate facts about the database for the solver.

### Production Semantic Safe Rate
`(A+B) / Total` under the canonical A–F taxonomy.

### Strict EX
Execution-match metric against benchmark gold output.

### Lucky Match
Candidate SQL is logically wrong but matches the current fixture result by accident.

### Shadow
Capability executes for observation but does not control production release behavior.

### Enforce
Capability can block/alter release decisions after certification.

### Evidence
Verified metadata, runtime facts, or experimental results with provenance.

### Provenance
Traceability of where a grounding fact or evaluation result came from.

---

## 2. Architecture Decision Records

### ADR-001 — Direct SQL solver remains mainline

**Decision:** Keep direct gpt-oss-120b solver as mainline.  
**Reason:** no certified evidence yet that planner/agentic alternatives provide sufficient net benefit.

### ADR-002 — n8n is orchestration only

**Decision:** n8n does not host a second Text-to-SQL intelligence stack.  
**Reason:** single ownership of SQL generation and governance.

### ADR-003 — OpenMetadata is metadata truth

**Decision:** T2S consumes and derives from OpenMetadata rather than becoming another metadata system.

### ADR-004 — A–F is canonical semantic taxonomy

**Decision:** all future semantic audits use A/B/C/D/E/F.

### ADR-005 — P1 semantic conclusions are blocked

**Decision:** historical P1 strict observations remain directional only because candidate SQL was not persisted.

### ADR-006 — Current OR is invalid as solver ceiling

**Decision:** replace with future OR* definition.

### ADR-007 — MG is capability-certified, not feature-bundled

**Decision:** capabilities move OFF → EXPERIMENTAL → SHADOW → CERTIFIED → PRODUCTION.

### ADR-008 — Temporal Grounding is next experiment candidate

**Decision:** Temporal is tested next because it is the largest audited MG error class, but remains OFF until certification.

### ADR-009 — Candidate SQL persistence is mandatory

**Decision:** semantic conclusions from a run without candidate SQL are governance-invalid.

