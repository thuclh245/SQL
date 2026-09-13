# Phase Exit Report — P1 Database Safety & Access Control

## 1. Objective
Establish a hard security boundary between generated SQL candidates and physical database execution.

## 2. Scope Implemented
- Trusted `UserIdentity` contract.
- `AccessPolicyPort` and `AuthorizationService` using executable SQL identifiers.
- SQLGlot-backed single-statement AST parser.
- Read-only structural validator for mutating SQL classes and non-query roots.
- AST-derived table access validator that ignores model-reported references.
- Central `QueryExecutionPolicy`.
- `QueryExecutorPort`, explain/result contracts, and `SecureQueryExecutor` gateway.
- SQLite read-only adapter with `mode=ro`, `PRAGMA query_only`, statement timeout, and row cap.
- Query audit event contract and sink port, recording blocked and succeeded explain/execute attempts.

## 3. Audit Classification
| Area | Classification | Notes |
|---|---|---|
| P0/P4 contracts | Already correct | `SqlCandidate`, `UserRequest`, and `TableContext.sql_identifier` were usable without redesign. |
| Error model | Partial | `UnauthorizedDataAccessError` existed; SQL safety/execution errors were missing and added. |
| Security package | Missing | Added identity, policy port, and authorization service. |
| Verification package | Missing | Added parser, safety validator, and access validator. |
| Database package | Missing | Added execution policy, port, result contracts, secure gateway, and SQLite adapter. |
| Alternate execution path | Missing boundary | Added `SecureQueryExecutor` as the composed path downstream phases should use. |
| Conflicting abstractions | None found | No prior execution/security abstractions had to be removed or duplicated. |

## 4. Files Added / Changed
- `pyproject.toml` — added `sqlglot`.
- `src/t2s/errors/application_errors.py` and `src/t2s/errors/__init__.py` — added SQL safety/execution error exports.
- `src/t2s/security/` — identity and authorization boundary.
- `src/t2s/verification/` — SQL parsing, read-only validation, resource validation.
- `src/t2s/database/` — execution policy, executor port/contracts, secure gateway, SQLite adapter.
- `tests/unit/security/` — authorization tests.
- `tests/unit/verification/` — SQL parser/safety tests.
- `tests/integration/database/` — secure gateway and read-only adapter tests.

## 5. Commands Executed
```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest tests/unit/verification tests/unit/security tests/integration/database -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src
```

## 6. Test Results
| Test group | Passed | Failed | Notes |
|---|---:|---:|---|
| P1 unit/integration subset | 19 | 0 | Safety, auth, gateway, row cap, timeout, bypass. |
| Full test suite | 51 | 0 | Existing P0/P4 tests still pass. |
| Ruff | 1 | 0 | `All checks passed!` |
| Mypy | 1 | 0 | `Success: no issues found in 46 source files` |

## 7. Metrics
| Metric | Before | After | Target | Status |
|---|---:|---:|---:|---|
| Unsafe query block rate on security suite | 0% | 100% | 100% | PASS |
| Unauthorized reference block rate | 0% | 100% | 100% | PASS |
| Timeout enforcement success | 0% | 100% | 100% | PASS |
| Row cap enforcement success | 0% | 100% | 100% | PASS |
| Full suite pass count | 32 | 51 | No regressions | PASS |

## 8. Failures Found
- Initial dependency install failed under sandboxed network resolution; rerun with approved network access succeeded.
- Initial timeout test used a query too small to trigger SQLite's progress handler; replaced with a recursive query.
- Initial AST table extraction included aliases and CTE names; changed extraction to base executable identifiers and excluded CTE aliases.

## 9. Improvements Made During Self-Review
- Preserved catalog FQN versus executable SQL identifier distinction in authorization.
- Added a regression proving model-reported `referenced_tables` are ignored for authorization.
- Added a bypass regression proving direct adapter use still opens SQLite in read-only mode.
- Added alias/CTE extraction coverage to prevent false unauthorized blocks.

## 10. Known Limitations
- SQLite is the first concrete adapter for local verification; production warehouse adapters still need provider-specific implementations.
- SQLGlot parse success is only structural validation, not final database dialect validity; the adapter/database still owns `EXPLAIN`.
- Audit persistence is represented by a sink port and event contract; durable storage can be attached in a later phase.
- `SecureQueryExecutor` is available as the intended boundary, but P5 still needs to wire the end-to-end route through it.

## 11. Evidence / Artifacts
- `src/t2s/security/`
- `src/t2s/verification/`
- `src/t2s/database/`
- `tests/unit/security/`
- `tests/unit/verification/`
- `tests/integration/database/`

## 12. Exit Criteria Checklist
- [x] Hand-written safe SELECT can be explained/executed.
- [x] Write operations remain impossible at DB permission level for SQLite adapter.
- [x] Unauthorized table query is blocked.
- [x] Resource limits work.
- [x] Audit trail exists as a port/event boundary.
- [x] Security regression suite passes.

## 13. Exit Decision
`PASS`

## 14. Reason
All P1 security gates are implemented with focused tests and full-suite regression evidence.

## 15. Handoff to Next Phase
P5 should route generated `SqlCandidate` objects through `SecureQueryExecutor` before any physical database `EXPLAIN` or execution. Downstream adapters should implement `QueryExecutorPort` and independently enforce read-only credentials/session settings.
