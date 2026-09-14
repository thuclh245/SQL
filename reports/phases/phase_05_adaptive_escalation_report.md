# Phase Exit Report — P5 Adaptive Escalation

## 1. Objective

Implement `P5 — Adaptive Escalation`: a bounded, deterministic orchestration layer that decides when the normal `P3 Grounding → P4 DirectSqlSolver` baseline path is sufficient, and when explicit, structured evidence of recoverable uncertainty justifies exactly one additional bounded corrective action.

P5 does **not** turn T2S into a generic autonomous agent, does not add multi-agent debates, and does not retry queries without new evidence.

---

## 2. Initial Audit

- **P3 Baseline**: `GroundingContextBuilder` provides deterministic lexical retrieval, table ranking, 1-hop relationship expansion, canonical catalog hydration, and column budget enforcement. It surfaces unresolved resources via `GroundingContext.unresolved` (e.g., `unresolved_sql_identifier`). P3 is frozen and must remain independently callable.
- **P4 Solver**: `DirectSqlSolver` generates typed `SqlCandidate` instances from `GroundingContext` via strict JSON schema structured outputs. It surfaces solver-reported uncertainty via `SqlCandidate.unresolved` and referenced tables via `SqlCandidate.referenced_tables`. P4 is frozen and must remain independently callable.
- **Security & Authorization Invariants**: `AuthorizationService` filters catalog resources upfront by `allowed_table_fqns`. P5 must never widen or bypass this authorization scope.
- **Identity Decoupling**: Separation of `table_fqn` (catalog identifier) from `sql_identifier` (executable relation identifier) must be preserved without exception.

---

## 3. Architecture

`AdaptiveOrchestrator` introduces a bounded composition layer around P3 and P4:

```text
QueryRequest + UserIdentity
          ↓
  Ground (Baseline Budget)
          ↓
  Generate (DirectSqlSolver)
          ↓
Assess uncertainty / failure evidence (EscalationPolicy)
          │
  ┌───────┴────────────────────────┐
  │ Sufficient confidence / Clean  │
  │ → return BASELINE_SUCCESS      │
  └────────────────────────────────┘
          │
          ▼
   Recoverable uncertainty?
          │
   yes ───┴─── no
    │            │
    ▼            ▼
 Bounded action   STOP_UNRESOLVED
    │
    ▼
 Same-context guard
    │
 context changed?
    ├── no  → UNRESOLVED (prevent meaningless retry)
    └── yes → Regenerate with resolved context
                  │
                  ▼
              Final candidate
              (ESCALATED_SUCCESS / FAILED)
```

The orchestrator composes `GroundingContextBuilder` and `DirectSqlSolver` via dependency injection without absorbing or modifying either module.

---

## 4. Baseline Path

The baseline path remains intact and independently callable:

```text
QueryRequest + UserIdentity
          ↓
GroundingContextBuilder.build_grounding_context()
          ↓
DirectSqlSolver.generate_sql_candidate()
          ↓
SqlCandidate
```

If `AdaptiveOrchestrator` is invoked with `EscalationBudget(max_escalations=0)`, or if the baseline outputs show no evidence of uncertainty, the orchestrator executes exactly 1 grounding call, 1 solver call, and returns `BASELINE_SUCCESS`.

---

## 5. Escalation Taxonomy

A strict, closed taxonomy of escalation reasons (`EscalationReason`) and actions (`EscalationAction`) is defined in `src/t2s/orchestration/escalation_contracts.py`:

### EscalationReason
| Code | Description | Recoverable? |
|---|---|---|
| `GROUNDING_INCOMPLETE` | Grounding issues reported other than missing SQL identifier | Yes (via expanded budget) |
| `RELATIONSHIP_AMBIGUITY` | Multiple tables selected but zero relationship evidence | Yes (via expanded relationship budget) |
| `UNRESOLVED_IDENTIFIER` | Catalog table has `sql_identifier=None` | No (cannot fabricate identifier) |
| `SOLVER_UNRESOLVED` | Solver explicitly reports unresolved ambiguities | Yes (via expanded budget) |
| `SCHEMA_REFERENCE_MISMATCH` | Solver generated SQL referencing tables not grounded | Yes (via expanded table budget) |

### EscalationAction
| Action | Description |
|---|---|
| `REGROUND_WITH_EXPANDED_BUDGET` | Re-run grounding with additive deltas on table/column/relationship budgets |
| `REGENERATE_WITH_RESOLVED_CONTEXT` | Re-run solver with new grounding context |
| `STOP_UNRESOLVED` | Halt immediately with outcome `UNRESOLVED` without further calls |

---

## 6. Escalation Policy

Implemented in `src/t2s/orchestration/escalation_policy.py` (`EscalationPolicy`).

- **Pure Python Deterministic Logic**: Zero LLM involvement in deciding whether to escalate.
- **Fail-Closed on Unresolvable Issues**: If `unresolved_sql_identifier` is present, policy immediately returns `STOP_UNRESOLVED`.
- **Evidence Requirement**: Every escalation decision requires concrete structured evidence (e.g. mismatched identifier string, unresolved message, missing relationship list).
- **Generic Retries Blocked**:
  - `budget_remaining <= 0` → `STOP_UNRESOLVED`
  - Solver failed (None candidate) without grounding issues → `STOP_UNRESOLVED`
  - No "try again", "think harder", or stochastic re-sampling.

---

## 7. Bounded-Loop Design

- **Strict Iteration Limit**: `max_escalations = 1` by default (enforced via `EscalationBudget(max_escalations: int = Field(default=1, ge=0, le=3))`).
- **Control Flow Termination**: The orchestrator performs at most `1 + max_escalations` grounding calls and `1 + max_escalations` solver calls. There are no `while` loops.
- **Same-Context Guard**: Prior to triggering regeneration, `AdaptiveOrchestrator._has_context_changed()` compares:
  - Table FQN set equality (`frozenset(table.fqn for table in tables)`)
  - Total column count
  - Total relationship count
  If expanded grounding produces identical context, the second generation is skipped and the run terminates with `UNRESOLVED` and trace outcome `context_unchanged`.

---

## 8. Security Preservation

- **Immutability of Authorization Scope**: `AdaptiveOrchestrator.run()` receives `user_identity: UserIdentity` and passes it directly to `GroundingContextBuilder`.
- **Zero Scope Broadening**: Regrounding re-evaluates `AuthorizationService.get_authorized_resources(user_identity)`. The set of `allowed_table_fqns` remains identical.
- **Tested Isolation**: Verified by test case `test_case_f_unauthorized_table_never_included_in_escalation`, which asserts that unauthorized tables (e.g., `secret.payroll`) never reach model context during baseline or escalated grounding.
- **Decoupled Identity**: Table context preserves `table_fqn != sql_identifier`. Missing `sql_identifier` produces `unresolved_sql_identifier` and stops deterministically (`test_case_g_missing_sql_identifier_is_never_fabricated`).

---

## 9. Observability

Every execution produces a structured `OrchestrationTrace` attached to `OrchestrationResult`:

- `run_id`: Request correlation ID.
- `outcome`: `BASELINE_SUCCESS | ESCALATED_SUCCESS | UNRESOLVED | FAILED`.
- `total_grounding_calls`: Integer counter.
- `total_solver_calls`: Integer counter.
- `escalation_records`: List of `EscalationRecord(attempt, reason, action, evidence, outcome)`.
- `baseline_table_fqns`: Tables selected in attempt 0.
- `baseline_unresolved_codes`: Grounding issues in attempt 0.
- `baseline_solver_unresolved`: Solver unresolved items in attempt 0.
- `final_table_fqns`: Final table context.

No unstructured chain-of-thought is persisted.

---

## 10. Evaluation Design

Implemented in `src/t2s/evaluation/orchestration_evaluation.py` (`OrchestrationEvaluationCollector`):

Measures:
- Case count ($N$)
- Baseline success count & escalated success count
- Unresolved and failed counts
- Escalation rate: $\frac{\text{escalations}}{\text{cases}}$
- Success-after-escalation rate: $\frac{\text{escalated\_success}}{\text{escalations}}$
- Unnecessary escalation count: escalations triggered on clean cases where escalation was not expected
- Average solver calls per case
- Average grounding calls per case

---

## 11. Evaluation Results

From benchmark test suite `tests/unit/orchestration/test_orchestration_benchmark.py`:

| Metric | Measured Value |
|---|---:|
| Benchmark case count ($N$) | 5 |
| Baseline success count | 2 |
| Escalated success count | 1 |
| Unresolved count | 2 |
| Failed count | 0 |
| Total escalations triggered | 2 |
| Escalation rate | 40.0% |
| Success-after-escalation rate | 50.0% (1/2; 1 succeeded, 1 stopped by same-context guard) |
| Unnecessary escalation count | 0 |
| Average grounding calls per case | 1.40 |
| Average solver calls per case | 1.00 |

### Breakdown by Case:
- **Case 1 (Clean Single-Table)**: 1 grounding call, 1 solver call, 0 escalations → `BASELINE_SUCCESS`.
- **Case 2 (Schema Mismatch / Missing Join Table)**: Attempt 0 missing related table → escalation triggered → expanded budget retrieves related table (`finance.orders` + `crm.customers`) → regenerated → `ESCALATED_SUCCESS`.
- **Case 3 (Solver Unresolved, No Additional Schema)**: Attempt 0 solver reports unresolved → expanded budget yields identical context → same-context guard halts → 0 regeneration calls → `UNRESOLVED` (`context_unchanged`).
- **Case 4 (Missing SQL Identifier)**: Grounding issue `unresolved_sql_identifier` → policy blocks retry → 0 solver calls → `UNRESOLVED`.
- **Case 5 (Unauthorized Neighbor Table)**: Neighbor table unauthorized → excluded by authorization service → 0 leaks → `BASELINE_SUCCESS`.

---

## 12. Failure Analysis

1. **Same-Context Stoppage**: In Case 3, when a solver reports unresolved ambiguity but the catalog contains no further authorized schema to hydrate, naive multi-agent architectures would loop or re-prompt the LLM. P5's same-context guard halts immediately after regrounding, saving a wasted LLM invocation.
2. **Unresolvable Identifiers**: Catalog tables without executable mappings cannot be solved by more tokens or larger budgets. P5 classifies this as a non-recoverable error and yields `UNRESOLVED` without escalation.

---

## 13. Files Changed

### New Files
- `src/t2s/orchestration/__init__.py`: Public API re-exports.
- `src/t2s/orchestration/escalation_contracts.py`: Taxonomy enums and structured trace/decision models.
- `src/t2s/orchestration/escalation_budget.py`: Budget limits and expansion deltas.
- `src/t2s/orchestration/escalation_policy.py`: Deterministic decision logic.
- `src/t2s/orchestration/adaptive_orchestrator.py`: Bounded orchestrator composition.
- `src/t2s/evaluation/orchestration_evaluation.py`: Benchmark evaluation collector and metrics.
- `tests/unit/orchestration/__init__.py`: Orchestration test package init.
- `tests/unit/orchestration/test_escalation_policy.py`: Policy unit tests (9 tests).
- `tests/unit/orchestration/test_adaptive_orchestrator.py`: Required scenarios A–H + trace tests (9 tests).
- `tests/unit/orchestration/test_orchestration_benchmark.py`: End-to-end benchmark evaluation test (1 test).
- `tests/unit/evaluation/test_orchestration_evaluation.py`: Evaluation collector unit tests (2 tests).

### Modified Files
- `src/t2s/evaluation/__init__.py`: Exported orchestration evaluation classes.

---

## 14. Tests

All 114 tests pass across unit, integration, and verification suites:

- **93 Existing Regression Tests**: P0 foundation, P1 safety/database, P2 catalog, P3 grounding, P4 solver (100% pass, zero regressions).
- **21 New P5 Tests**:
  - `test_adaptive_orchestrator.py`: Case A (clean), Case B (incomplete grounding), Case C (solver unresolved), Case D (same context guard), Case E (budget exhaustion), Case F (unauthorized isolation), Case G (missing sql_identifier), Case H (relationship ambiguity), trace completeness.
  - `test_escalation_policy.py`: All reason codes, budget exhaustion, unresolvable identifier stoppage, solver failure handling.
  - `test_orchestration_benchmark.py`: Benchmark suite metrics calculation.
  - `test_orchestration_evaluation.py`: Collector edge cases and rate computation.

---

## 15. Commands & Results

```bash
.venv/bin/python -m pytest -vv
# 114 passed in 0.43s

.venv/bin/python -m ruff check .
# All checks passed!

.venv/bin/python -m mypy src workers
# Success: no issues found in 79 source files
```

---

## 16. Known Limitations

- **Synthetic Fixture Evaluation**: Grounding and solver components in the unit benchmark use in-memory catalogs and mock chat clients; real end-to-end LLM inference requires a live vLLM/OpenAI endpoint.
- **Static Diagnostic Mapping**: Escalation currently addresses table and column budget saturation, missing relationships, and schema reference mismatches. Execution-time SQL syntax repair (e.g. database compiler errors) is deferred to post-P5 database integration phases.

---

## 17. Deferred Mechanisms

The following mechanisms are explicitly out of scope for P5 and deferred to later phases:
- LLM verifiers / judges / critic agents
- Multi-agent debate or candidate voting
- Sample-value lookups / database probing / EXPLAIN feedback loops
- Execution repair loops
- Learned / reinforcement learning escalation policies
- Vector / semantic IR retrieval

---

## 18. Status

`READY_FOR_INDEPENDENT_REVIEW`
