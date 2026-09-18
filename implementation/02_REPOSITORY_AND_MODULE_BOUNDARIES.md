# 02 — Repository and Module Boundaries

## 1. Proposed repository

```text
t2s/
├── pyproject.toml
├── uv.lock / requirements.lock
├── alembic.ini
├── config/
│   ├── default.yaml
│   ├── dev.yaml
│   └── policy/
├── src/t2s/
│   ├── main.py
│   ├── api/
│   │   ├── routes_query.py
│   │   ├── routes_feedback.py
│   │   ├── routes_admin.py
│   │   └── dependencies.py
│   ├── domain/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   └── policies.py
│   ├── ports/
│   │   ├── catalog.py
│   │   ├── query_log.py
│   │   ├── retrieval.py
│   │   ├── llm.py
│   │   ├── authorization.py
│   │   ├── database.py
│   │   ├── risk.py
│   │   └── audit.py
│   ├── services/
│   │   ├── query_service.py
│   │   ├── grounding.py
│   │   ├── solver.py
│   │   ├── verification.py
│   │   ├── orchestrator.py
│   │   ├── risk_controller.py
│   │   └── response_builder.py
│   ├── adapters/
│   │   ├── auth/
│   │   ├── openmetadata/
│   │   ├── opensearch/
│   │   ├── querylog/
│   │   ├── vllm/
│   │   ├── sqlglot/
│   │   ├── db/
│   │   │   ├── postgres.py
│   │   │   ├── clickhouse.py
│   │   │   └── starrocks.py
│   │   └── persistence/
│   ├── indexing/
│   │   ├── document_builder.py
│   │   ├── sync.py
│   │   └── cli.py
│   └── observability/
│       ├── logging.py
│       ├── metrics.py
│       └── tracing.py
├── migrations/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── security/
│   └── regression/
└── eval/
    ├── datasets/
    ├── runners/
    └── reports/
```

## 2. Dependency rule

```text
api -> services -> domain/ports
adapters -> domain/ports
services must not import concrete adapters
```

`domain/` and `ports/` must have no dependency on FastAPI, OpenSearch, OpenMetadata SDK, vLLM or a DB driver. This keeps every mechanism replaceable.

## 3. Main service responsibilities

- `QueryService`: one public use-case entry point.
- `GroundingService`: builds the smallest sufficient authorized context.
- `SolverService`: invokes one solver strategy and returns structured candidate(s).
- `VerificationService`: deterministic checks plus optional verifier plug-in.
- `Orchestrator`: bounded transition policy; never owns DB credentials or retrieval implementation.
- `RiskController`: Answer/Ambiguous/Abstain decision from evidence features.
- `ResponseBuilder`: final user-safe payload; no internal chain-of-thought leakage.

## 4. Extension rule

A new mechanism (Wren, IR, alternative solver, learned reranker) is added as an adapter/strategy implementing an existing port wherever possible. If it requires changing every module, the boundary design is wrong.
