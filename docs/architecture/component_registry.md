# Component Registry

This registry provides the canonical catalog of all functional components within the T2S Text-to-SQL architecture. All components strictly adhere to the Absolute Phase-Neutral Naming Policy.

---

## 1. Production Runtime Components

| Component Name | Module Location | Responsibility | Runtime Tier | Inputs | Outputs |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AdaptiveOrchestrator** | `src/t2s/orchestration/adaptive_orchestrator.py` | Bounded escalation control flow between grounding and LLM SQL solver | Production | `QueryRequest`, `GroundingContext` | `OrchestrationResult` |
| **DirectSqlSolver** | `src/t2s/solver/direct_sql_solver.py` | Single-turn LLM code generation client interfacing with vLLM | Production | `GroundingContext`, prompt | `SqlCandidate` |
| **SqlAstParser** | `src/t2s/verification/sql_ast_parser.py` | Static SQL dialect parsing and syntax tree extraction via sqlglot | Production | raw SQL string, dialect | `ParsedSql` |
| **SqlSafetyValidator** | `src/t2s/verification/sql_safety_validator.py` | Static AST read-only validation preventing DDL, DML, or unsafe calls | Production | `ParsedSql` | `None` (or `UnsafeSqlError`) |
| **SqlAccessValidator** | `src/t2s/verification/sql_access_validator.py` | Authorization validation against user identity and permitted tables | Production | `UserIdentity`, `ParsedSql` | `None` (or `UnauthorizedDataAccessError`) |
| **SqlSemanticRiskValidator** | `src/t2s/verification/sql_semantic_risk_validator.py` | Deterministic structural, aggregation, and join invariant verification | Production | `ValidationInput` | `ValidationResult` |
| **SqlRiskController** | `src/t2s/runtime/sql_risk_controller.py` | Policy gate mapping risk detections into runtime actions (shadow vs enforce) | Production | `ValidationInput`, `ValidatorMode` | `ValidatorRuntimeOutcome` |
| **SqliteReadOnlyQueryExecutor**| `src/t2s/database/sqlite_read_only_query_executor.py` | Isolated read-only query execution with strict timeouts and row limits | Production | SQL string, database connection | Execution rows, column types |
| **TextToSqlRuntime** | `src/t2s/runtime/text_to_sql_runtime.py` | Top-level state-machine orchestrating end-to-end safe execution | Production | `QueryRequest` | `RuntimeExecutionResult` |

---

## 2. Evaluation & Diagnostic Components

| Component Name | Module Location | Responsibility | Runtime Tier | Inputs | Outputs |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ShadowEvaluator** | `src/t2s/evaluation/shadow_evaluator.py` | Offline counterfactual evaluation of rejected candidates | Diagnostic / Evaluation | Case ID, database, candidate, gold | `ShadowCaseResult` |
| **LlmSemanticVerifier**| `src/t2s/verification/llm_semantic_verifier.py` | Optional LLM-assisted semantic verification gate | Evaluation / Gated | Verification prompt | `SemanticCheckResult` |
| **BenchmarkRunner** | `src/t2s/benchmark/runner.py` | Batch benchmark execution and metrics collection | Evaluation / Benchmark | Evaluation manifest | Benchmark summary |
| **Scoring** | `src/t2s/benchmark/scoring.py` | Execution accuracy and set matching calculations | Evaluation / Benchmark | Predicted SQL, Gold SQL | Match metrics |

---

## 3. Storage & Metadata Components

| Component Name | Module Location | Responsibility | Runtime Tier |
| :--- | :--- | :--- | :--- |
| **InMemoryCatalog** | `src/t2s/catalog/in_memory_catalog.py` | Ephemeral schema metadata and column type dictionary | Production |
| **SchemaManifestLoader** | `src/t2s/catalog/schema_manifest_loader.py` | Manifest parser populating catalog tables from JSON declarations | Production |
| **SchemaRetriever** | `src/t2s/grounding/schema_retriever.py` | BM25/Vector retrieval of relevant tables for question context | Production |
