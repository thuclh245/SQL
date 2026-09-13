# Foundation & Direct SQL Solver Stabilization Report

## Status
`READY_FOR_INDEPENDENT_REVIEW`

This remediation resolves the confirmed P0/P4 high-priority review findings without starting P1/P2/P3/P5 work.

## Finding Map

| Finding ID | Confirmed / Rejected | Evidence | Fix | Files Changed | Tests Added | Validation Result | Remaining Limitation |
|---|---|---|---|---|---|---|---|
| R1 / P0 HIGH-1 Alembic dependency missing | Confirmed | `.venv/bin/python -c "import alembic"` originally failed with `ModuleNotFoundError`. | Added `alembic>=1.17,<2.0`; installed Alembic 1.20.0 with SQLAlchemy 2.0.52. | `pyproject.toml` | `tests/unit/test_alembic_dependency.py` | `.venv/bin/python -c "import alembic; print(alembic.__version__)"` -> `1.20.0`; `.venv/bin/alembic --help` -> exit 0. | No real migrations were created, by design. |
| R2 / P0 HIGH-2 Missing global error boundary | Confirmed | FastAPI had no exception handlers for `T2SError` or unexpected exceptions. | Added structured safe JSON handlers for typed and unexpected errors. | `src/t2s/api/error_handlers.py`, `src/t2s/bootstrap/application.py`, `src/t2s/contracts/error_response.py` | `tests/integration/test_error_boundary.py` | Typed and unexpected exception tests pass. | Status mapping remains conservative 500 until later auth/security phases define HTTP semantics. |
| R3 / P0 HIGH-3 Correlation IDs not bound to contextvars | Confirmed | `structlog.contextvars.merge_contextvars` was configured but `bind_contextvars()` was unused. | Added request middleware to bind/clear `request_id` and `trace_id`, plus query-run binding for `run_id`. | `src/t2s/observability/correlation.py`, `src/t2s/api/query_routes.py`, `src/t2s/bootstrap/application.py` | `tests/integration/test_error_boundary.py` | Different requests receive different context; context clears after request; query route binds run ID. | No distributed tracing exporter yet; P0 only owns local correlation context. |
| R4 / P0 MEDIUM-2 Whitespace-only question accepted | Confirmed | `QueryRequest(question="   ")` was accepted. | Added field validator that trims surrounding whitespace and rejects empty result. | `src/t2s/contracts/query_request.py` | `tests/integration/test_query_routes.py` | `""`, `" "`, and `"\t\n"` return 422; valid question with surrounding spaces returns 200. | Internal meaningful whitespace is preserved. |
| R5 / P0 MEDIUM-3 Ambiguous/missing connection settings | Confirmed | Settings lacked clearly named state/search/metadata/vLLM URL fields. | Added `state_postgres_url`, `opensearch_url`, `openmetadata_url`, and `vllm_base_url`; kept required semantics conservative for P0. | `src/t2s/configuration/settings.py`, `configs/default.yaml` | `tests/unit/test_settings.py` | Explicit construction and environment override tests pass. | YAML loading remains documented as not wired; env/settings are the active source. |
| R6 / P4 HIGH-1 FQN treated as SQL identity | Confirmed | `TableContext` had only `fqn`, and PromptBuilder rendered it as `table:`. | Added explicit `sql_identifier`; prompt now says `catalog_fqn` is provenance and `sql_identifier` is executable. | `src/t2s/contracts/grounding_context.py`, `src/t2s/solver/prompt_builder.py`, `prompts/direct_sql/v001_system.md`, fixtures | `tests/unit/solver/test_prompt_builder.py` | Prompt tests prove FQN and executable identifier differ and no FQN substitution occurs. | P4 does not compile dialect identifiers; P3 must populate `sql_identifier`. |
| R7 / P4 HIGH-2 Solver imports vLLM schema implementation | Confirmed | `DirectSqlSolver` imported `t2s.integrations.vllm.structured_output_schema`. | Moved JSON schema construction to solver-owned `SolverStructuredOutput.model_json_schema()`. Removed integration schema file. | `src/t2s/solver/direct_sql_solver.py`, `src/t2s/solver/solver_response.py`, deleted `src/t2s/integrations/vllm/structured_output_schema.py` | `tests/unit/solver/test_direct_sql_solver.py` | Test confirms solver core source contains no `t2s.integrations.vllm` import. | vLLM adapter still accepts generic JSON schema through the `StructuredChatClient` protocol. |
| R8 / P4 HIGH-3 Malformed vLLM HTTP 200 non-JSON leaks raw decode error | Confirmed | `response.json()` was outside adapter normalization. | Wrapped provider JSON parsing and normalized non-JSON provider responses as `SolverDependencyError`. | `src/t2s/integrations/vllm/vllm_chat_client.py` | `tests/unit/integrations/vllm/test_vllm_chat_client.py` | Tests cover timeout, connection failure, HTTP 500, HTTP 200 non-JSON, malformed provider shape, malformed model content. | Provider structure errors remain `MalformedSolverOutputError`; model content schema errors remain distinct downstream. |
| R9 / P4 HIGH-4 Prompt loading depends on CWD | Confirmed | Changing CWD to `/tmp` caused `FileNotFoundError`. | Default prompt root is resolved from the source tree rather than process CWD; explicit prompt root still supported. | `src/t2s/solver/prompt_builder.py` | `tests/unit/solver/test_prompt_builder.py` | CWD-changing regression test passes. | Wheel packaging of root-level prompts is not addressed; current repo/source deployment works. |
| P4 MEDIUM prompt boundary delimiters | Confirmed | User question and trusted schema were plain adjacent blocks. | Added XML-like delimiters around untrusted question and authorized schema. | `prompts/direct_sql/v001_user_template.md` | Covered by prompt construction tests. | Prompt tests pass. | Prompt-injection resistance is not a security boundary; downstream auth/verification still required. |
| Real gpt-oss-120b smoke | Confirmed pending gate, not a code defect | No `LLM_`, `VLLM_`, `OPENAI_`, or `REAL_GPT_OSS_120B` endpoint env was present. | Recorded status only. | This report | n/a | `printenv | rg '^LLM_|^VLLM_|^OPENAI_|^REAL_GPT_OSS_120B' || true` produced no endpoint. | `REAL_GPT_OSS_120B_SMOKE = PENDING`; must close before P5 production-like integration. |

## Architecture Self-Review

- API does not own business logic; middleware owns request correlation and handlers own safe error serialization.
- Solver core no longer imports concrete vLLM integration schema code.
- `GroundingContext` remains project-owned and does not import OpenMetadata wire types.
- `fqn` is catalog/provenance identity; `sql_identifier` is the executable relation reference supplied by grounding.
- Integration adapter normalizes transport/provider failures into typed project errors.
- Logging context is request-scoped and cleared after each request.

## Commands and Results

```bash
.venv/bin/python -m pip install -e '.[dev]'
# installed alembic-1.20.0, SQLAlchemy-2.0.52

.venv/bin/python -m pytest -vv
# 32 passed in 0.27s

.venv/bin/python -m ruff check .
# All checks passed!

.venv/bin/python -m mypy src
# Success: no issues found in 31 source files

.venv/bin/python -c "import alembic; print(alembic.__version__)"
# 1.20.0

.venv/bin/alembic --help
# exit 0, help text printed
```

## Pending External Gates

`REAL_GPT_OSS_120B_SMOKE = PENDING`

No real endpoint configuration was available locally. Do not treat this as satisfied until a real gpt-oss-120b/vLLM endpoint is configured and smoke-tested.

## Known Limitations

- No metadata retrieval, SQL safety validation, database execution, EXPLAIN, repair loop, candidate voting, semantic layer, Wren, or QueryPlan IR was introduced.
- YAML config loading remains disconnected from runtime settings; environment and direct settings construction are the verified configuration paths.
- Error handlers currently use conservative 500 responses for typed application errors until phase-specific HTTP semantics are defined.
- `sql_identifier` is trusted input from future P3; P4 does not compile or validate dialect identifiers.

## Recommended Next Action

Independent Gemini re-review of the remediated P0/P4 boundaries.
