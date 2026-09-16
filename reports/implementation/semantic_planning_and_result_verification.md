# Grounded Semantic Planning & Result-Aware Verification Implementation Report

## 1. Executive Summary

This report documents the architectural design, formal contracts, implementation, and empirical verification of two core reliability capabilities introduced into the T2S / CHATSQL system:
1. **Grounded Semantic Planning** (`src/t2s/semantics/`): Moving the query synthesis pipeline from an unconstrained `Question -> SQL` generation step to a decoupled, evidence-driven `Question -> Grounding -> SemanticPlan -> SQL` pipeline. The semantic plan captures intended metric aggregation, target entities, requested grain, required filters, and expected result shapes before SQL generation begins.
2. **Result-Aware Verification & Diagnostic Probing** (`src/t2s/verification/result_verifier.py`, `src/t2s/verification/diagnostic_probes.py`): Post-execution validation that eliminates the false-success pathology where an executed query returns `NULL` scalar aggregates, empty populations, or all-null rows, yet is falsely accepted and presented to users as a successful answer. When anomalous results occur, strictly read-only, timeout-bounded diagnostic SQL probes are executed to explain *why* the result is empty or null (distinguishing empty underlying database tables from filter grounding failures).

Both capabilities strictly adhere to zero benchmark-derived heuristics, zero keyword-to-arithmetic hardcoding, zero gold SQL leakage, and fail-closed security invariants.

---

## 2. Semantic Planning Port & Contracts

The semantics subsystem is formalized under `src/t2s/semantics/` with strict Pydantic v2 immutability (`frozen=True`, `extra="forbid"`):

- `SemanticPlan` (`src/t2s/semantics/semantic_plan.py`):
  - `plan_id: str`: Unique correlation ID for the plan.
  - `status: PlannerStatus`: `READY`, `UNCERTAIN`, `AMBIGUOUS`, or `INSUFFICIENT_EVIDENCE`.
  - `metric_name: str | None`: Target metric column name grounded in schema evidence.
  - `aggregation: MetricAggregation`: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `NONE`, or `UNKNOWN`.
  - `dimensions: list[str]`: Planned grouping dimensions.
  - `grain: SemanticGrain`: Explicit `requested_grain` and `source_grain`.
  - `filters: list[SemanticFilter]`: Structured filters tied to grounded value bindings.
  - `expectation: ResultExpectation`: Structural expectations for post-execution verification (`expected_shape`, `expected_value_type`, `can_be_empty`, `can_be_null`).
  - `evidence: list[SemanticEvidence]`: Traceable provenance linking each plan element to a specific table or column description in the catalog.
  - `semantic_uncertainty_level: str`: Calibrated uncertainty (`LOW`, `MEDIUM`, `HIGH`).

- Invariant on Unstated Grain:
  When a metric's grain, unit, or business period is absent from the database catalog metadata, the planner explicitly sets `grain.source_grain="unknown"`, marks `uncertainties=["UNKNOWN_METRIC_GRAIN"]`, and escalates uncertainty to `HIGH` rather than guessing arbitrary arithmetic divisors (such as `/12` or `*100`).

---

## 3. Grounded Semantic Planner Implementation

Implemented in `src/t2s/semantics/semantic_planner.py`:
- `SemanticPlannerPort`: Abstract protocol defining `plan(query_request, grounding_context) -> SemanticPlan`.
- `GroundedSemanticPlanner`: Dual-mode planner:
  1. **Deterministic Metadata Grounding**: Operates purely on authorized schema metadata, column descriptions, and grounded value bindings without LLM dependency.
  2. **LLM-Backed Structured Mode**: When an OpenAI-compatible / vLLM client is provided, prompts the model with strict operational constraints (no SQL generation, no invented definitions, fail-closed JSON schema adherence).
- `SemanticPlanConsistencyChecker` (`src/t2s/semantics/plan_consistency_checker.py`):
  A lightweight pre-execution AST analyzer comparing generated SQL against the plan:
  - Verifies presence of aggregate functions when `plan.aggregation` is non-NONE.
  - Verifies `GROUP BY` presence when dimensions and aggregation coexist.
  - Verifies presence of `WHERE` / `HAVING` clauses when filters are planned.
  - Confirms SQL AST references planned tables.

---

## 4. Result-Aware Verification & Diagnostic Probing

### 4.1 ResultVerifier (`src/t2s/verification/result_verifier.py`)
Evaluates executed query output against `ResultExpectation`:
- **Suspicious Null Scalar Aggregate**: If a scalar aggregation returns a single row with `None`, flags `SUSPICIOUS_NULL_RESULT` and recommends `METRIC_NON_NULL_PROBE`.
- **Mathematical Zero Differentiation**: Correctly accepts `0` or `0.0` as valid answers, never conflating `0` with `None`.
- **Empty Result Check**: If `row_count == 0` when `can_be_empty == False`, flags `SUSPICIOUS_EMPTY_RESULT` and recommends `POPULATION_COUNT_PROBE`.
- **All-Null Rows Check**: Flags `ALL_ROWS_NULL` when multi-column or multi-row queries return entirely null values.

### 4.2 DiagnosticProbeRunner (`src/t2s/verification/diagnostic_probes.py`)
When a result is suspicious:
- Executes read-only, timeout-bounded (5s), row-limited (10 rows max) SELECT probes.
- Every probe passes through `SqlAstParser`, `SqlSafetyValidator`, and `SqlAccessValidator` before dispatch.
- Differentiates:
  - `BASE_POPULATION_EMPTY`: The underlying database table itself has 0 rows.
  - `FILTER_GROUNDING_FAILURE`: The base table contains data, indicating that restrictive or misaligned filter predicates eliminated all rows.

### 4.3 Safe Runtime Response Calibration
In `RuntimeExecutionResult.to_query_response()`, when a suspicious outcome is detected, the API response status is calibrated to `"ambiguous"` with policy `"result-verification-v1"` and a descriptive explanation, rather than claiming unqualified success.

---

## 5. Architectural Hygiene & Security Guarantees

1. **Security Classification**: Added `"semantics"` to `production_packages` in `configs/security/benchmark_registry.json`.
2. **Naming & Secret Audits**: All 13 hygiene and security audits pass cleanly with status `HYGIENE_CLOSURE_COMPLETE`.
3. **AST Safety & Access Control**: Diagnostic probes reuse existing executor policies, preventing any privilege escalation or state modification.
4. **Test Isolation**: Autouse fixture `_isolate_local_env_file` in `tests/conftest.py` prevents developer `.env` contamination.

---

## 6. Verification & Test Evidence

- **New Test Suites**:
  - `tests/unit/semantics/test_semantic_plan.py`: Contract schema, immutability, extra forbid, round-trip serialization.
  - `tests/unit/semantics/test_semantic_planner.py`: Deterministic metadata planning, unstated grain uncertainty, aggregation mapping.
  - `tests/unit/semantics/test_plan_consistency_checker.py`: AST vs plan aggregation, GROUP BY, and syntax mismatch detection.
  - `tests/unit/verification/test_result_verifier.py`: Null scalar, zero preservation, empty population, all-null row detection.
  - `tests/unit/verification/test_diagnostic_probes.py`: SQLite-backed population count probe and filter grounding failure diagnosis.
  - `tests/unit/semantics/test_metamorphic_semantics.py`: English phrasing variations and Vietnamese translations produce invariant semantic plans.
  - `tests/unit/semantics/test_schema_mutation_semantics.py`: Metadata resilience against arbitrary identifier obfuscation.
- **Repository Regression Suite**:
  - 453 passed, 2 skipped across unit, integration, security, and architecture suites.
  - Full `mypy src/` pass (143 source files checked, 0 errors).
  - Full `ruff check src/ tests/` pass (0 errors).

---

## 7. Residual Risk & Production Roadmap

1. **Multi-turn Clarification**: In ambiguous situations where grain is unstated, provide an interactive user clarification callback in the API.
2. **Expanded Probe Catalog**: Add range-check probes (`MIN` / `MAX` value probes) to verify date boundaries when temporal filters return empty sets.
