# Phase Exit Report — P4 Direct SQL Solver

## 1. Objective
Implement the simplest typed direct-SQL generation baseline: `QueryRequest + GroundingContext -> SqlCandidate`, using a versioned prompt and an OpenAI-compatible vLLM adapter, without retrieval, verification, DB execution, repair loops, or orchestration.

## 2. Scope Implemented
- `SolverPort` and `DirectSqlSolver`.
- Project-owned `GroundingContext` and `SqlCandidate` contracts.
- Versioned direct SQL prompts in `prompts/direct_sql/`.
- vLLM OpenAI-compatible chat adapter with JSON schema structured output.
- Trace metadata for model, prompt version, run ID, reasoning effort, token counts, and latency.
- Grounding fixtures for single-table aggregate/value-filter and two-table FK join contexts.
- Deterministic unit tests with mocked vLLM transport.
- Smoke artifact for small generation-case coverage.

## 3. Files Added / Changed
- `pyproject.toml` — moved `httpx` to runtime dependencies for the vLLM adapter.
- `src/t2s/contracts/grounding_context.py` — P3-compatible grounding contract.
- `src/t2s/contracts/sql_candidate.py` — typed SQL candidate and generation trace.
- `src/t2s/solver/solver_port.py` — provider-independent solver protocol.
- `src/t2s/solver/solver_request.py` — solver input with dialect and generation settings.
- `src/t2s/solver/solver_response.py` — strict structured output parser model.
- `src/t2s/solver/prompt_builder.py` — versioned prompt construction from grounding context.
- `src/t2s/solver/direct_sql_solver.py` — single-call direct SQL solver.
- `src/t2s/integrations/vllm/vllm_chat_client.py` — OpenAI-compatible vLLM adapter.
- `src/t2s/integrations/vllm/structured_output_schema.py` — JSON schema for structured output.
- `prompts/direct_sql/v001_system.md` — system prompt.
- `prompts/direct_sql/v001_user_template.md` — user prompt template.
- `tests/fixtures/grounding_fixtures.py` — realistic fixture grounding contexts.
- `tests/unit/solver/` — prompt and solver tests.
- `tests/unit/integrations/vllm/` — vLLM adapter tests.
- `reports/smoke/p4_direct_sql_solver_smoke.md` — smoke set notes.

## 4. Commands Executed
```bash
.venv/bin/python -m pytest -vv
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src
rg -n "BIRD|benchmark|SQLite|sqlite|Wren|QueryPlan|multi-agent|think again|guided_json" src prompts tests reports/smoke pyproject.toml
printenv | rg '^LLM_|^VLLM_|^OPENAI_' || true
```

## 5. Test Results
| Test group | Passed | Failed | Notes |
|---|---:|---:|---|
| P0 integration/unit tests | 6 | 0 | Existing foundation tests still pass. |
| P4 solver/prompt tests | 6 | 0 | Prompt construction, trace metadata, malformed/empty output rejection. |
| P4 vLLM adapter tests | 3 | 0 | Structured content parsing, malformed JSON, timeout handling. |
| Lint | 1 | 0 | `ruff check .` passed. |
| Type check | 1 | 0 | `mypy src` passed. |

## 6. Metrics
| Metric | Before | After | Target | Status |
|---|---:|---:|---:|---|
| Structured-output success rate | n/a | 1/1 mocked success path | Parser accepts valid schema | PASS |
| Malformed-output rejection | n/a | 2/2 failure paths rejected | Fail closed | PASS |
| Generation latency | n/a | Captured from adapter response path | Traceable | PASS |
| Prompt token count | n/a | Captured when vLLM returns usage | Traceable | PASS |
| Output token count | n/a | Captured when vLLM returns usage | Traceable | PASS |

## 7. Failures Found
- Initial parser allowed missing structured-output list fields through defaults. It now requires all schema fields.
- Initial vLLM adapter tests monkeypatched `httpx.AsyncClient`; the adapter now accepts an optional transport for deterministic tests.
- No real vLLM endpoint variables were present in the shell, so real `gpt-oss-120b` smoke verification is pending.

## 8. Improvements Made During Self-Review
- Prompt files are external and versioned as `v001`.
- The solver port is independent of vLLM-specific request/response types.
- No retry loop, repair flow, verifier, DB gateway, semantic runtime, Wren, QueryPlan IR, or multi-agent workflow was introduced.
- Prompt self-review found no BIRD/benchmark-specific assumptions; `sqlite` appears only as a supported dialect.
- vLLM adapter uses `response_format` JSON schema, not deprecated `guided_json`.
- Adapter lives under `src/t2s/integrations/vllm` so it is packaged with the application.

## 9. Known Limitations
- The solver does not prove SQL safety, executability, or semantic correctness.
- No real endpoint smoke test was performed because no `LLM_`, `VLLM_`, or `OPENAI_` endpoint configuration was present.
- Prompt token counts depend on provider usage metadata; the local mock only verifies propagation.
- Fixtures stand in for P3 grounding until real retrieval is ready.

## 10. Evidence / Artifacts
- `src/t2s/solver/`
- `src/t2s/integrations/vllm/`
- `prompts/direct_sql/`
- `tests/fixtures/grounding_fixtures.py`
- `reports/smoke/p4_direct_sql_solver_smoke.md`
- `.venv/bin/python -m pytest -vv` -> 15 passed.
- `.venv/bin/python -m ruff check .` -> all checks passed.
- `.venv/bin/python -m mypy src` -> success.

## 11. Exit Criteria Checklist
- [x] SolverPort is clear and typed.
- [x] GroundingContext fixtures exist.
- [x] Prompt is versioned.
- [x] vLLM adapter exists.
- [x] Structured output is parsed into SqlCandidate.
- [x] Model/prompt/run metadata is traceable.
- [x] Timeout/malformed responses are handled.
- [x] Unit tests pass.
- [x] Ruff passes.
- [x] Mypy passes.
- [x] Real model smoke test performed if endpoint is available; no endpoint was available, status pending.
- [x] No P5/P8 functionality was introduced.

## 12. Exit Decision
`PASS`

## 13. Reason
The direct solver baseline is implemented, provider boundaries remain clear, structured output fails closed, and P0/P4 tests, lint, and type checks pass.

## 14. Handoff to Next Phase
P5 can call `DirectSqlSolver.generate_sql_candidate()` with a trusted `SolverRequest` and receive either a typed `SqlCandidate` or an explicit solver error. P3 can replace test fixtures with real `GroundingContext` instances without changing the solver interface.
