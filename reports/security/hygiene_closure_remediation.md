# Repository Hygiene Closure & Remediation Log

## Overview

This document records the concrete technical remediations implemented to achieve repository hygiene closure and enforce permanent structural independence between production code and experimental artifacts.

---

## 1. Remediation Chronology

### A. Total Phase Name Elimination
1. **Renamed Files**:
   - `src/t2s/verification/p4_validator.py` $\rightarrow$ `src/t2s/verification/sql_semantic_risk_validator.py`
   - `src/t2s/runtime/p4_risk_controller.py` $\rightarrow$ `src/t2s/runtime/sql_risk_controller.py`
2. **Renamed Classes, Enums, and Contracts**:
   - `P4DeterministicValidator` $\rightarrow$ `SqlSemanticRiskValidator`
   - `P4RiskController` $\rightarrow$ `SqlRiskController`
   - `P4ValidatorFamily` $\rightarrow$ `ValidatorFamily`
   - `P4Violation` $\rightarrow$ `SemanticViolation`
   - `P4ValidationInput` $\rightarrow$ `ValidationInput`
   - `P4ValidationResult` $\rightarrow$ `ValidationResult`
   - `P4ValidatorMode` $\rightarrow$ `ValidatorMode`
   - `P4RuntimeAction` $\rightarrow$ `ValidatorRuntimeAction`
   - `P4ValidatorRuntimeOutcome` $\rightarrow$ `ValidatorRuntimeOutcome`
   - `RuntimeTrace.p4_validator_outcome` $\rightarrow$ `RuntimeTrace.validator_outcome`
   - `RuntimeExecutionResult.p4_validator_outcome` $\rightarrow$ `RuntimeExecutionResult.validator_outcome`
3. **Purged Legacy Aliases**:
   - Removed `"p4_validator_mode"` from `AliasChoices` in `src/t2s/configuration/settings.py`. Production configuration now strictly uses `validator_mode` (with capability alias `sql_risk_validator_mode`).
4. **Cleaned Docstrings & Comments**:
   - Sanitized all references to "P5 Adaptive Orchestration", "P6 Safe Runtime", and "P1 security" across `src/t2s/` modules.

### B. Benchmark-Specific Logic Removal
1. **Purged 7 Hardcoded Rules from Validator**:
   - Removed table-specific heuristics (`card_games: foreign_data`, `cards`, `european_football_2: team_attributes`).
   - Removed column-specific heuristics (`student_club: member_id`, `formula_1: fastestlapspeed`).
   - Removed question-specific string matches (`"completed on what date"`).
2. **Purged Diagnostic Phrase Hardcodes**:
   - Sanitized phrase lists in `src/t2s/evaluation/shadow_evaluator.py`.

### C. Dependency Boundary Hardening
1. **Removed Cross-Boundary Import**:
   - Removed `from t2s.benchmark.catalog_loader import load_bird_catalog_tables` from `src/t2s/bootstrap/runtime_factory.py`.
2. **Verified Transitive Graph**:
   - Traced all 71 modules reachable from production entrypoints (`application.py`, `runtime_factory.py`, `text_to_sql_runtime.py`, `query_routes.py`). 0 illegal transitive dependencies.

### D. Gold Isolation & Evaluation Model Relocation
1. **Moved `VerifierCandidateRecord`**:
   - `VerifierCandidateRecord` was originally in `src/t2s/verification/contracts.py` containing `bird_difficulty` and `gold_sql`.
   - Relocated `VerifierCandidateRecord` to `src/t2s/evaluation/verifier_evaluation.py`.
   - Purged all benchmark and gold attributes from `src/t2s/verification/contracts.py` and `src/t2s/verification/__init__.py`.
2. **Enforced Strict DTO Boundary**:
   - Added `model_config = ConfigDict(extra="forbid")` to:
     - `src/t2s/contracts/query_request.py:QueryRequest`
     - `src/t2s/contracts/sql_candidate.py:SqlCandidate`
     - `src/t2s/contracts/grounding_context.py:GroundingContext`
     - `src/t2s/verification/contracts.py:VerificationInput`
     - `src/t2s/solver/solver_request.py:SolverRequest`
     - `src/t2s/solver/solver_response.py:SolverStructuredOutput`
     - `src/t2s/runtime/runtime_contracts.py:RuntimeExecutionResult`

### E. Observability & Privacy Protection
1. **Integrated Secret Redaction in Structlog**:
   - Added `_scrub_secrets_processor` using `t2s.security.sanitization.sanitize_data` into `src/t2s/observability/logging.py`.
   - Every structured logging call automatically redacts API tokens and high-entropy credentials before JSON rendering.
2. **AST Logging Verification**:
   - Verified 0 unstructured `print()` calls in production code.
   - Verified 0 logging calls passing sensitive kwargs (`password`, `token`, `secret`, `gold_sql`).

---

## 2. CI Architecture Hygiene Test Suite

Ten permanent architectural guards were established in `tests/unit/architecture/test_architecture_hygiene_guards.py`:
- `test_guard_1_production_naming`
- `test_guard_2_benchmark_naming`
- `test_guard_3_direct_dependency_boundary`
- `test_guard_4_transitive_runtime_dependency`
- `test_guard_5_gold_field_isolation`
- `test_guard_6_prompt_hygiene`
- `test_guard_7_secret_scanning`
- `test_guard_8_case_id_prohibition`
- `test_guard_9_historical_artifact_runtime_access`
- `test_guard_10_production_path_naming`

Twelve audit engine unit tests were established in `tests/unit/security/test_audit_engine.py`:
- Positive tests for all 6 modular checkers.
- Negative tamper/injection tests for synthetic benchmark names, phase tokens, illegal imports, leaked secrets, and DTO leakage.
- Decision engine fail-closed behavior tests (fails closed on violations, incomplete on unknown or test failures).

---

## 3. Execution Verification

```bash
# Full test suite execution
.venv/bin/pytest tests/
# Output: 307 passed in 9.46s

# Linter and formatting check
.venv/bin/ruff check src/t2s tests/
# Output: All checks passed!

# Static type check
.venv/bin/mypy
# Output: Success: no issues found in 114 source files
```
