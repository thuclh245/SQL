# T2S Implementation Pack — Production-First NL-to-SQL

**Status:** implementation baseline, September 2026.  
**Architecture:** Security -> Grounding -> Generation -> Verification -> Controlled DB Interaction -> Decision, with bounded recovery loops only when new evidence can be obtained.

## Goal

This pack converts the current candidate architecture into an implementation that can be built immediately. It deliberately starts with a **modular monolith** rather than microservices. OpenMetadata, vLLM and analytical warehouses remain external systems; T2S owns policy, grounding, generation, verification, orchestration, risk decisions, audit and evaluation.

## Build order

1. Bootstrap API + configuration + request trace.
2. Security/identity boundary.
3. Catalog adapter + metadata index.
4. Grounded direct-SQL baseline using gpt-oss-120b.
5. SQL AST guard + dialect preflight + read-only DB gateway.
6. Conservative decision policy + answer/abstain.
7. Observability + evaluation harness integration.
8. Only then test adaptive loops, alternative solvers, semantic/Wren or IR branches.

## Documents

- `01_RUNTIME_STACK_AND_DEPLOYMENT_SHAPE.md`
- `02_REPOSITORY_AND_MODULE_BOUNDARIES.md`
- `03_DOMAIN_MODELS_AND_PORTS.md`
- `04_API_AND_REQUEST_LIFECYCLE.md`
- `05_SECURITY_AND_AUTHORIZATION.md`
- `06_METADATA_INDEX_AND_GROUNDING.md`
- `07_LLM_SOLVER_AND_PROMPT_CONTRACT.md`
- `08_SQL_VERIFICATION_AND_DB_GATEWAY.md`
- `09_ORCHESTRATOR_AND_RISK_CONTROLLER.md`
- `10_PERSISTENCE_CACHE_AND_AUDIT_SCHEMA.md`
- `11_OBSERVABILITY_AND_OPERATIONS.md`
- `12_TESTING_AND_EVALUATION.md`
- `13_CONFIG_AND_LOCAL_DEPLOYMENT.md`
- `14_IMPLEMENTATION_ROADMAP.md`
- `15_OPTIONAL_EXTENSION_POINTS.md`
- `16_ACCEPTANCE_CHECKLIST.md`

`examples/` contains copyable configuration, Pydantic contracts, interfaces and a minimal orchestrator skeleton.

## Non-negotiable implementation rules

- Identity comes from trusted authentication middleware, never from a request-body `user_id`.
- Authorization is applied before metadata retrieval and rechecked before DB access.
- The LLM never receives database credentials.
- All SQL touches a single controlled `DatabaseGateway`.
- Only read-only query forms are allowed; database permissions remain the final security boundary.
- Generic “think again” retries are not a default. Recovery must be driven by concrete evidence or an independent path.
- Semantic/Wren, IR, multi-solver and LLM verifier are plug-ins, not prerequisites for v1.
