# Historical Research Phase Index

This index records the chronological research milestones of the T2S Text-to-SQL project. In accordance with the Absolute Phase-Neutral Naming Policy, these historical phase identifiers are strictly archived within `docs/research/` and `reports/` and are forbidden from appearing in production code (`src/t2s/`).

---

## Milestone Summary

| Phase Identifier | Research Goal / Description | Status | Primary Artifacts | Production Code Changes |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | Initial architecture baseline and skeleton contracts | Superseded | Baseline contracts | Core interface definitions |
| **P1** | Security perimeter: AST read-only validation & authorization | Active | Safety and access validators | `SqlSafetyValidator`, `SqlAccessValidator` |
| **P2** | Catalog and schema representation layer | Active | In-memory catalog, document builder | `InMemoryCatalog`, `CatalogSearchDocumentBuilder` |
| **P3** | Grounding and retrieval subsystem | Active | BM25 schema retriever, relationship expander | `SchemaRetriever`, `RelationshipExpander` |
| **P4** | Direct SQL generation solver | Active | Prompt builder and solver client | `DirectSqlSolver`, `DirectSqlPromptBuilder` |
| **P5** | Adaptive bounded escalation orchestrator | Active | Multi-turn bounded recovery flow | `AdaptiveOrchestrator` |
| **P6** | End-to-end safe runtime execution state machine | Active | Structured execution loop with audit logs | `TextToSqlRuntime` |
| **P7** | Rejected candidate forensics & shadow diagnostic evaluator | Superseded | Counterfactual diagnostic harness | `ShadowEvaluator` |
| **P8-E0** to **E4** | Metric integrity, benchmark harness safety, selective grounding | Superseded | Forensics reports, calibration scripts | Calibration metrics |
| **P8-E5** to **E8** | Deterministic semantic risk rules & shadow runtime integration | Active (Shadow) | Initial deterministic validator prototypes | `SqlSemanticRiskValidator`, `SqlRiskController` |
| **P8-E9** | Independent validation audit & cohort sufficiency review | Concluded | Validation blocking decision report | Zero (Enforcement blocked) |
| **P8-E10 / E10R** | Enterprise data acquisition & statistical power governance | Concluded | 60 Olist questions staged; gold cert pending | Zero paid calls |

---

## Governance Policy

1. **Isolation**: Research phase numbers must never be used as package names, module names, class names, or public API fields in production code.
2. **Deprecation of Hardcoded Heuristics**: Any heuristic devised by observing errors on a specific evaluation split must not be hardcoded into production validators. Production validators must enforce only universal SQL semantics and AST invariants.
3. **Evaluation Gate**: Production enforcement of deterministic validators remains blocked (`AUTHORIZED = NO`, `DEFAULT_MODE = SHADOW`) until certified on an independent, non-contaminated evaluation dataset.
