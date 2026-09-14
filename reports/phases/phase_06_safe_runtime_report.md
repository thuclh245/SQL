# Phase Exit Report — P6 Safe End-to-End Runtime

## 1. Objective

Implement `P6 — Safe End-to-End Runtime`: a single, production-oriented application runtime pipeline ([`TextToSqlRuntime`](file:///home/thuclh245/MyCode/SQL/src/t2s/runtime/text_to_sql_runtime.py)) connecting all accepted components (P1 Database Safety & Verification, P2 Metadata Catalog, P3 Grounding Baseline, P4 Direct SQL Solver, P5 Adaptive Escalation) to securely process user queries from question to executed rows.

P6 enforces the core architectural invariant:
> An LLM-generated query cannot reach the database unless it has passed deterministic safety validation, independent authorization validation, and the read-only execution boundary.

---

## 2. Initial Audit

- **P1 Verification & Database**: [`SqlSafetyValidator`](file:///home/thuclh245/MyCode/SQL/src/t2s/verification/sql_safety_validator.py) and [`SqlAccessValidator`](file:///home/thuclh245/MyCode/SQL/src/t2s/verification/sql_access_validator.py) parse ASTs via [`SqlAstParser`](file:///home/thuclh245/MyCode/SQL/src/t2s/verification/sql_ast_parser.py) (`sqlglot`) to block mutations and unauthorized tables. [`SqliteReadOnlyQueryExecutor`](file:///home/thuclh245/MyCode/SQL/src/t2s/database/sqlite_read_only_query_executor.py) enforces statement timeouts, read-only mode, and result row trashing limits.
- **P2 Metadata Catalog**: Preserves strict separation between `table_fqn` (catalog domain) and `sql_identifier` (executable relation identifier).
- **P3 Grounding**: Deterministically retrieves scoped, hydrated schema contexts within `GroundingBudget` bounds.
- **P4 Direct SQL Solver**: Uses structured JSON schema outputs to produce typed `SqlCandidate` instances.
- **P5 Adaptive Orchestration**: Orchestrates P3 and P4 with deterministic escalation policies and same-context guards.

P6 integrates these components cleanly without rewriting them into a monolithic class.

---

## 3. Architecture

`TextToSqlRuntime` sits at the application layer, orchestrating the fail-closed lifecycle:

```text
QueryRequest + UserIdentity
          │
          ▼ [State: RECEIVED]
┌──────────────────────────────────────┐
│ AdaptiveOrchestrator (P5: P3 + P4)   │
└──────────────────────────────────────┘
          │
          ├── UNRESOLVED ─────────────► [Terminal: UNRESOLVED, DB calls = 0]
          ├── FAILED ─────────────────► [Terminal: GENERATION_FAILED, DB calls = 0]
          │
          ▼ [State: GROUNDED_GENERATED]
┌──────────────────────────────────────┐
│ SqlSafetyValidator (P1: AST)         │
└──────────────────────────────────────┘
          │
          ├── UnsafeSqlError ─────────► [Terminal: SAFETY_REJECTED, DB calls = 0]
          │
          ▼ [State: VERIFIED]
┌──────────────────────────────────────┐
│ SqlAccessValidator (P1: AST)         │
└──────────────────────────────────────┘
          │
          ├── UnauthorizedAccessError ► [Terminal: ACCESS_DENIED, DB calls = 0]
          │
          ▼ [State: AUTHORIZED]
┌──────────────────────────────────────┐
│ ReadOnlyQueryExecutor (P1: DB)       │
└──────────────────────────────────────┘
          │
          ├── TimeoutError ───────────► [Terminal: TIMEOUT]
          ├── QueryExecutionError ────► [Terminal: EXECUTION_FAILED]
          │
          ▼ [State: EXECUTED -> COMPLETED]
RuntimeExecutionResult (columns, rows, execution_time_ms, trace)
```

---

## 4. Runtime State Machine

The lifecycle of each request is modeled explicitly in [`RuntimeState`](file:///home/thuclh245/MyCode/SQL/src/t2s/runtime/runtime_contracts.py):

```text
RECEIVED
    ↓
GROUNDED_GENERATED
    ↓
VERIFIED
    ↓
AUTHORIZED
    ↓
EXECUTED
    ↓
COMPLETED
```

Terminal failure states:
- `UNRESOLVED`: P5 reported unresolvable ambiguity or lack of schema.
- `GENERATION_FAILED`: P5 solver encountered dependency or structured parsing failures.
- `SAFETY_REJECTED`: AST validation caught non-read-only operations or multi-statement payloads.
- `ACCESS_DENIED`: AST table extraction found references to unauthorized database resources.
- `EXECUTION_FAILED`: Database driver execution failure (e.g. invalid column name).
- `TIMEOUT`: Database statement execution exceeded configured time budget.

Every state transition records `from_state`, `to_state`, and `elapsed_ms` in the request's `RuntimeTrace`.

---

## 5. P5 Integration

`TextToSqlRuntime` calls `AdaptiveOrchestrator.run()` with the incoming `QueryRequest`, `UserIdentity`, and `run_id`.

- `BASELINE_SUCCESS` or `ESCALATED_SUCCESS`: The pipeline proceeds to AST safety validation with `sql_candidate`.
- `UNRESOLVED`: Execution halts immediately. The runtime transitions to `RuntimeState.UNRESOLVED` and returns `RuntimeStatus.UNRESOLVED`. Database execution is skipped.
- `FAILED`: Execution halts immediately. The runtime transitions to `RuntimeState.GENERATION_FAILED` and returns `RuntimeStatus.GENERATION_FAILED`. Database execution is skipped.

---

## 6. SQL Safety Integration

Uses P1 [`SqlSafetyValidator`](file:///home/thuclh245/MyCode/SQL/src/t2s/verification/sql_safety_validator.py) with AST parsing via [`SqlAstParser`](file:///home/thuclh245/MyCode/SQL/src/t2s/verification/sql_ast_parser.py).

- No regex or string matching fallbacks.
- Verified blocking of:
  - `DELETE`, `DROP`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `MERGE`
  - `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE`
  - Multi-statement injections (e.g. `SELECT 1; DROP TABLE customers`)
- Any failure raises `UnsafeSqlError`, transitions to `SAFETY_REJECTED`, audits the blocked attempt, and guarantees zero database calls.

---

## 7. Authorization Integration

Model-produced `SqlCandidate.referenced_tables` is treated as **untrusted user input**.

- The runtime extracts relation identifiers directly from the AST (`parsed_sql.referenced_table_identifiers()`).
- [`SqlAccessValidator`](file:///home/thuclh245/MyCode/SQL/src/t2s/verification/sql_access_validator.py) checks every referenced relation against `AuthorizationService.validate_sql_resource_access(user_identity, ...)`.
- If an unauthorized table is referenced, `UnauthorizedDataAccessError` is raised, transitioning to `ACCESS_DENIED`.
- Critical security test `test_critical_negative_model_reported_tables_cannot_bypass_ast` proves that a model maliciously reporting `referenced_tables=["customers"]` while querying `secret_payroll` is caught and blocked by the AST check.

---

## 8. Execution Integration

Uses P1 [`QueryExecutorPort`](file:///home/thuclh245/MyCode/SQL/src/t2s/database/query_executor_port.py) (implemented by [`SqliteReadOnlyQueryExecutor`](file:///home/thuclh245/MyCode/SQL/src/t2s/database/sqlite_read_only_query_executor.py)):
- Read-only connection mode.
- Statement timeouts enforced via monotonic clocks.
- Row limits enforced via `QueryExecutionPolicy.maximum_result_rows` with `has_more_rows` tracking.
- Database errors normalized to typed `QueryExecutionError` / `QueryExecutionTimeoutError`.

---

## 9. Failure Semantics

- **Fail-Closed**: Database execution only happens when `generation_success AND safety_valid AND access_valid`.
- **No Automatic Repair**: Execution, safety, or access errors do not trigger re-prompting or retry loops. Failures terminate immediately with structured diagnostics.
- **Sanitized Outputs**: Error messages do not leak internal credentials or raw stack traces.

---

## 10. Traceability

Cross-stage correlation is maintained via a single `run_id`:
- `RuntimeTrace.run_id` links:
  - `orchestration_trace`: baseline/escalated grounding and solver call counts, escalation records.
  - `ast_referenced_tables`: tables extracted by AST parser.
  - `state_history`: complete timestamped lifecycle history.
  - `safety_check_passed`, `access_check_passed`, `execution_passed`.
- Audit events logged to `QueryAuditSinkPort` preserve `run_id`, `request_id`, and `trace_id`.

---

## 11. Evaluation Design

Implemented in [`src/t2s/evaluation/runtime_evaluation.py`](file:///home/thuclh245/MyCode/SQL/src/t2s/evaluation/runtime_evaluation.py) via `RuntimeEvaluationCollector`:
- Tracks case count ($N$), completed count, unresolved count, safety rejection count, access denial count, execution failure count, timeout count, total executor calls, and average latency.

---

## 12. Evaluation Results

Measured via `tests/unit/runtime/test_runtime_benchmark.py`:

| Metric | Measured Value | Target | Status |
|---|---:|:---:|:---:|
| Benchmark cases ($N$) | 4 | >= 4 | PASS |
| Successful executions (`COMPLETED`) | 1 | > 0 | PASS |
| Safety rejections (`SAFETY_REJECTED`) | 1 | >= 1 | PASS |
| Access denials (`ACCESS_DENIED`) | 1 | >= 1 | PASS |
| Execution failures (`EXECUTION_FAILED`) | 1 | >= 1 | PASS |
| Timeouts (`TIMEOUT`) | 0 | 0 | PASS |
| Total database executor calls | 2 | Exactly 2 (1 success + 1 DB failure; 0 for rejected cases) | PASS |
| Average runtime latency | 0.55 ms | < 100 ms (mock solver) | PASS |

---

## 13. Negative Security Tests

Critical negative security proofs verified in `tests/integration/runtime/test_text_to_sql_runtime.py`:

1. **Unsafe SQL Never Reaches Executor**:
   - `test_case_c_unsafe_generated_sql_rejected`: Model generates `DELETE FROM customers` -> `SAFETY_REJECTED`, executor call count = 0.
2. **Multi-Statement Injection Blocked**:
   - `test_case_g_multi_statement_injection_rejected`: Model generates `SELECT *; DROP TABLE` -> `SAFETY_REJECTED`, executor call count = 0.
3. **Unauthorized SQL Never Reaches Executor**:
   - `test_case_d_unauthorized_table_access_denied`: Model accesses `secret_payroll` -> `ACCESS_DENIED`, executor call count = 0.
4. **AST Overrides Model Claims**:
   - `test_critical_negative_model_reported_tables_cannot_bypass_ast`: Model reports `referenced_tables=["customers"]` but SQL contains `secret_payroll` -> blocked by AST access check, executor call count = 0.
5. **P5 Unresolved Never Reaches Executor**:
   - `test_case_e_p5_unresolved_halts_without_execution`: Missing `sql_identifier` -> `UNRESOLVED`, executor call count = 0.
6. **P5 Failure Never Reaches Executor**:
   - `test_case_f_solver_failure_halts_without_execution`: Solver error -> `GENERATION_FAILED`, executor call count = 0.

---

## 14. Files Changed

### New Files
- `src/t2s/runtime/__init__.py`: Public package exports.
- `src/t2s/runtime/runtime_contracts.py`: Lifecycle state machine, result models, trace models.
- `src/t2s/runtime/text_to_sql_runtime.py`: End-to-end safe runtime pipeline implementation.
- `src/t2s/evaluation/runtime_evaluation.py`: Runtime evaluation harness and collector.
- `tests/unit/runtime/test_runtime_contracts.py`: Unit tests for contracts and `QueryResponse` conversions (7 tests).
- `tests/unit/runtime/test_runtime_benchmark.py`: Benchmark suite evaluation test (1 test).
- `tests/integration/runtime/test_text_to_sql_runtime.py`: End-to-end integration tests (Cases A–J + negative security tests, 11 tests).
- `reports/phases/phase_06_safe_runtime_report.md`: Phase exit report.

### Modified Files
- `src/t2s/evaluation/__init__.py`: Exported runtime evaluation classes.
- `src/t2s/orchestration/adaptive_orchestrator.py`: Clarified distinction between baseline `FAILED` (solver failure on resolved tables) and `UNRESOLVED` (unresolved grounding).

---

## 15. Tests

All 133 tests pass across the entire suite:

- **114 Existing Regression Tests**: P0 foundation, P1 safety/database, P2 catalog, P3 grounding, P4 solver, P5 escalation (100% pass, zero regressions).
- **19 New P6 Tests**:
  - `tests/unit/runtime/test_runtime_contracts.py`: 7 tests.
  - `tests/unit/runtime/test_runtime_benchmark.py`: 1 test.
  - `tests/integration/runtime/test_text_to_sql_runtime.py`: 11 tests.

---

## 16. Commands & Results

```bash
.venv/bin/python -m pytest -vv
# 133 passed in 0.47s

.venv/bin/python -m ruff check .
# All checks passed!

.venv/bin/python -m mypy src workers
# Success: no issues found in 83 source files
```

---

## 17. Known Limitations

- **Mock LLM In Integration Tests**: Integration tests use deterministic mock chat clients (`FakeStructuredChatClient`); live LLM inference depends on reachable vLLM/OpenAI endpoint availability (carried debt from P4).
- **SQLite Single Warehouse**: Database execution currently validates SQLite; additional warehouse engines (ClickHouse, PostgreSQL, StarRocks) will be connected via `QueryExecutorPort` implementations in later phases.

---

## 18. Deferred Work

Explicitly deferred to post-P6 phases:
- Automatic SQL error repair loops
- Natural language result summarizers / explanation LLM calls
- Semantic caching / query result caching
- UI / API frontend integrations
- Warehouse-specific dialect execution adapters (PostgreSQL, ClickHouse, StarRocks)

---

## 19. Status

`READY_FOR_INDEPENDENT_REVIEW`
