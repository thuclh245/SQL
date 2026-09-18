# 13 — Configuration and Local Deployment

## 1. Configuration hierarchy

```text
default.yaml
  <- environment YAML
  <- environment variables / secret manager
  <- explicit test overrides
```

Validate everything at startup. Missing security-critical values cause startup/readiness failure.

## 2. Example configuration

See `examples/config.example.yaml`.

Critical groups:

- `auth` — issuer/audience/header mapping;
- `openmetadata` — URL/token/version;
- `retrieval` — index/limits/weights;
- `llm` — base URL/model/reasoning effort/timeouts;
- `database` — adapter DSNs/roles/timeouts;
- `orchestration` — budgets/feature flags;
- `risk` — policy version/thresholds;
- `audit` — retention/redaction.

## 3. Local dependencies

Use Docker Compose for **T2S-owned local state only**:

```text
PostgreSQL
OpenSearch
(optional) OpenTelemetry collector / Prometheus
```

Connect to development OpenMetadata/vLLM/warehouses using environment-specific endpoints. Avoid embedding production credentials in Compose.

## 4. Bootstrap commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

alembic upgrade head
python -m t2s.indexing.cli full-sync
uvicorn t2s.main:app --host 0.0.0.0 --port 8080
pytest -q
```

If the project standardizes on `uv`, use `uv sync` and commit the lock file; the runtime design does not depend on the package manager.

## 5. vLLM serving contract

T2S only requires an internal OpenAI-compatible URL, model identifier and supported structured-output contract. Do not make application code depend on how many GPUs vLLM uses.

Current vLLM supports OpenAI-compatible APIs and structured outputs. Its API-key setting alone is not a complete network security boundary, so run it behind internal ingress/proxy controls. [R2–R4]

## 6. Feature flags

Start with:

```yaml
features:
  dense_retrieval: false
  db_probes: true
  alternative_solver: false
  semantic_verifier: false
  semantic_runtime: false
  typed_ir: false
```

Turn features on through controlled experiments rather than enabling all optional complexity at once.
