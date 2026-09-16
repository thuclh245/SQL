# Repository-wide Leakage, Contamination & Architecture Hygiene Audit

## Executive Summary

An exhaustive repository-wide security, scientific-integrity, and architecture-hygiene audit was conducted across the T2S Text-to-SQL system (`/home/thuclh245/MyCode/SQL`). The audit rigorously addressed two central questions:

> **Core Question 1**: *Does any production-capable T2S code, prompt, configuration, runtime policy, test utility, cache, evaluator, validator, or orchestration path contain or consume information that should belong only to development/evaluation/research?*
> 
> **Finding**: Prior to remediation, **YES**. Two significant leakage vectors were discovered:
> 1. **Benchmark-Specific Overfitting in Runtime Verification**: The deterministic validator (`p4_validator.py`) and diagnostic evaluator (`shadow_evaluator.py`) contained hardcoded table names (`foreign_data`, `cards`, `team_attributes`), column names (`fastestlapspeed`, `member_id`), and specific question phrasing matching known error cases in the BIRD Mini-Dev dataset.
> 2. **Cross-Boundary Dependency Ingestion**: The production bootstrap factory (`runtime_factory.py`) imported `load_bird_catalog_tables` from `t2s.benchmark.catalog_loader`.

> **Core Question 2**: *Is any production implementation coupled to phase names, benchmark names, dataset splits, case IDs, or historical experiment artifacts?*
> 
> **Finding**: Prior to remediation, **YES**. Experimental phase tokens (`P4`, `P5`, `P6`) permeated production filenames (`p4_validator.py`, `p4_risk_controller.py`), class definitions (`P4DeterministicValidator`, `P4RiskController`), enum names (`P4ValidatorMode`, `P4RuntimeAction`), configuration fields (`p4_validator_mode`), and runtime execution trace objects (`p4_validator_outcome`).

### Audit Status Post-Remediation
- **Remediation Status**: **100% COMPLETE & VERIFIED**
- **Production Cleanliness**: 0 phase names, 0 benchmark names in `src/t2s` production code.
- **Architectural CI Guards**: 5 automated guards (Guards A–E) implemented and passing in `tests/unit/architecture/test_architecture_hygiene_guards.py`.
- **Test Suite Status**: 271/271 tests passing (100%).
- **Production Enforcement Authorization**: **BLOCKED (`AUTHORIZED = NO`, `DEFAULT_MODE = SHADOW`)**.

---

## Audit Scope & Category Breakdown

The audit systematically evaluated 12 categories:

### Category A: Benchmark-Specific Hardcoding in Runtime (Remediated)
- **Findings**:
  - `src/t2s/verification/p4_validator.py`: Lines 282–297 (`card_games` heuristic checking `foreign_data` and `cards`), lines 317–333 (`european_football_2` heuristic checking `team_attributes`), lines 359–368 (`completed on what date`), lines 389–404 (`student_club` checking `member_id`), lines 406–436 (`formula_1` checking `fastest lap speed`), lines 510–525 (cross join checking `foreign_data`).
  - `src/t2s/evaluation/shadow_evaluator.py`: Phrases extracted from specific BIRD error cases (`order.k_symbol`, `cards.asciiname`, `foreign_data.name`, `isstorylight`, `total cards`).
- **Remediation**:
  - Removed all dataset-specific rules and replaced the file with `src/t2s/verification/sql_semantic_risk_validator.py`.
  - Retained purely general, dataset-agnostic AST invariants: syntax correctness, unbound parameters (`:var`), empty `IN ()` clauses, ratio/division structure, and cross-join detection.
  - Sanitized `shadow_evaluator.py` phrase lists to retain only universal linguistic and SQL ambiguity patterns.

### Category B: Dependency Boundary Leaks (Remediated)
- **Findings**:
  - `src/t2s/bootstrap/runtime_factory.py` contained an unused import: `from t2s.benchmark.catalog_loader import load_bird_catalog_tables`.
- **Remediation**:
  - Removed the import. Production bootstrap now cleanly uses `t2s.catalog.schema_manifest_loader.load_catalog_tables_from_manifest`.
  - Guard A in `test_architecture_hygiene_guards.py` now enforces that production code (`src/t2s/` excluding `benchmark/` and `evaluation/`) cannot import from `t2s.benchmark.*`, `t2s.evaluation.*`, `tests.*`, or `scripts.*`.

### Category C: Gold Data Leakage into Validation / Generation (Verified Clean)
- **Verification**:
  - `ValidationInput` enforces `extra = "forbid"` and explicitly disallows `gold_sql`, `gold_answer`, `gold_tables`, or `ground_truth`.
  - Guard C automated test confirms that passing any gold fields raises an immediate `pydantic.ValidationError`.
  - Runtime pipelines operate completely blind of gold labels.

### Category D: Prompt Hygiene & Dynamic Grounding (Verified Clean)
- **Verification**:
  - `DirectSqlPromptBuilder` does not contain static few-shot examples or benchmark-specific schemas.
  - Dynamic grounding retrieves schemas strictly via `SchemaRetriever` from the provided database catalog.
  - Guard D automated test validates zero occurrences of benchmark table names in production system prompts.

### Category E: Caching & State Leaks (Verified Clean)
- **Verification**:
  - No prompt caching, query result caching, or persistent cross-request state exists that carries evaluation ground truth into runtime.
  - In-memory catalogs are scoped to the active database.

### Category F: Benchmark Harness & Evaluation Leakage (Verified Clean)
- **Verification**:
  - Evaluation scripts execute against quarantined benchmark manifests and never write back to production configuration.
  - Gold execution checks run in an isolated test runner environment.

### Category G: Historical Experiment & Phase Coupling in Code (Remediated)
- **Findings**:
  - Extensive naming coupling with research phases: `P4DeterministicValidator`, `P4RiskController`, `p4_validator_outcome`, `p4_validator_mode`, and docstrings referencing "P5", "P6", "P1".
- **Remediation**:
  - Executed complete renaming to phase-neutral architectural symbols:
    * `p4_validator.py` -> `sql_semantic_risk_validator.py` (`SqlSemanticRiskValidator`)
    * `p4_risk_controller.py` -> `sql_risk_controller.py` (`SqlRiskController`)
    * `P4ValidatorMode` -> `ValidatorMode`
    * `P4RuntimeAction` -> `ValidatorRuntimeAction`
    * `P4ValidatorRuntimeOutcome` -> `ValidatorRuntimeOutcome`
    * `p4_validator_outcome` -> `validator_outcome`
    * `p4_validator_mode` -> `validator_mode`
  - All phase references archived to `docs/research/phase_index.md`.
  - Guard B enforces 0 phase names and 0 benchmark names in production code.

### Category H: Test Utility & Harness Contamination (Remediated)
- **Findings**:
  - Unit tests in `tests/unit/verification/test_p4_validator.py` and `tests/unit/runtime/test_p4_risk_controller.py` reflected phase names.
- **Remediation**:
  - Migrated to `tests/unit/verification/test_sql_semantic_risk_validator.py` and `tests/unit/runtime/test_sql_risk_controller.py`.

### Category I: Offline Artifact vs Online Code Boundary (Verified Clean)
- **Verification**:
  - Research scripts and build artifacts (`scripts/build_*.py`, `results/p8*`) reside strictly outside `src/t2s/`.
  - Production code has no awareness of or dependencies on offline build scripts.

### Category J: Data Provenance & Split Integrity (Quarantined)
- **Status**:
  - BIRD Mini-Dev (500 items): 100 dev items are contaminated by historical inspection; 400 holdout items remain quarantined and uninspected. Status: `QUARANTINED / UNCERTIFIABLE_FOR_ENFORCEMENT`.
  - Enterprise Olist (60 items): 20 canonical verified, 40 staged. Status: `STAGED / BLIND`. Requires independent auditor certification before paid validation.

### Category K: Secret & Token Hygiene (Verified Clean)
- **Findings**:
  - Local `.env` contained an OpenRouter API key. `.env` is gitignored and was never committed to git.
- **Remediation**:
  - Verified `git ls-files` across the entire repository. Zero live secrets are committed to git.
  - Guard E automated scan runs on every test invocation to prevent credential leakage into git tracking.

### Category L: Logging, Privacy & Observability Hygiene (Verified Clean)
- **Verification**:
  - Structlog pipelines filter sensitive fields and redact API tokens using `t2s.security.sanitization.sanitize_text`.
  - Only event identifiers, latencies, correlation IDs, and rule codes are logged.

---

## Summary of Remediation Actions Taken

1. **Renamed and Decoupled Files**:
   - `src/t2s/verification/p4_validator.py` $\rightarrow$ `src/t2s/verification/sql_semantic_risk_validator.py`
   - `src/t2s/runtime/p4_risk_controller.py` $\rightarrow$ `src/t2s/runtime/sql_risk_controller.py`
2. **Sanitized Rules**:
   - Removed 7 benchmark-specific hardcoded heuristics from `sql_semantic_risk_validator.py`.
   - Cleaned database-specific note phrases from `shadow_evaluator.py`.
3. **Decoupled API & Configuration**:
   - Renamed `p4_validator_mode` to `validator_mode` in `Settings` and `TextToSqlRuntime`.
   - Renamed `p4_validator_outcome` to `validator_outcome` in `RuntimeExecutionResult` and `RuntimeTrace`.
4. **Cleaned Docstrings & Comments**:
   - Purged all phase tokens (`P0`–`P9`, `P8-E*`) from `src/t2s` production code.
5. **Architectural CI Enforcement**:
   - Implemented `tests/unit/architecture/test_architecture_hygiene_guards.py` verifying Guards A, B, C, D, and E.
6. **Full Suite Green**:
   - Verified 271 passing tests across all unit and integration test suites.
