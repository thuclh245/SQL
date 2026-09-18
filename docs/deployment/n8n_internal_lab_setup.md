# Internal n8n Lab Connectivity Setup Guide

**Target Component**: T2S FastAPI Service (`t2s.main:app`)  
**Orchestration Consumer**: Company Internal n8n Instance  
**Integration Tier**: Internal Lab & Integration Testing  
**Current Governance State**: `INTERNAL_N8N_LAB_READY = YES_WITH_CONDITIONS`  
**Production Enforcement**: `NO`  

---

## 1. T2S Service Startup Command

The T2S application entrypoint is located at `t2s.main:app`. To allow the company's internal n8n instance (running in a separate container, host, or VM) to connect over the internal network, uvicorn must be started bound to all interfaces (`0.0.0.0`):

```bash
# In repository root (/home/thuclh245/MyCode/SQL)
.venv/bin/uvicorn t2s.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --log-level info
```

*Note*: For standard development or background execution, this can be managed via systemd, Docker, or a background process.

---

## 2. Internal Host & Port Requirements

| Parameter | Recommended Setting | Rationale |
| :--- | :--- | :--- |
| **Listening Interface** | `0.0.0.0` | Allows connections from bridge network or remote internal n8n hosts. |
| **Port** | `8000` (Default) | Standard API port (configurable via `--port <port>`). |
| **Network Scope** | **Internal / Private Lab Only** | Do **not** bind to public interfaces or expose port 8000 to the public internet. |
| **Protocol** | `HTTP/1.1` | Plaintext HTTP acceptable for isolated lab testing; production requires TLS termination. |

### Topology

```text
Company Internal n8n Host
  └─ [HTTP Request Node]
       │
       ▼ (Internal Network / Bridge: http://<t2s-host-or-ip>:8000)
T2S FastAPI Service (0.0.0.0:8000)
  ├─ GET  /health/live
  ├─ GET  /health/ready
  ├─ GET  /openapi.json
  └─ POST /v1/query
       │
       ▼ (Internal Domain Runtime)
DatabaseGateway (Port 5432 / 5433)
  └─ PostgreSQL Read-Only Transaction
```

---

## 3. Health & Liveness Check Instructions

Before executing query workflows in n8n, verify service availability using standard HTTP nodes or curl:

### Liveness Probe (`GET /health/live`)
* **Endpoint**: `http://<t2s-host>:8000/health/live`
* **Expected Status**: `200 OK`
* **Response**: `{"status": "live"}`
* **Purpose**: Verifies that the FastAPI process is responsive (no DB or LLM calls made).

### Readiness Probe (`GET /health/ready`)
* **Endpoint**: `http://<t2s-host>:8000/health/ready`
* **Expected Status**: `200 OK`
* **Response**: `{"status": "ready", "environment": "dev"}`
* **Purpose**: Confirms application configuration loading.

---

## 4. Query Endpoint Specification (`POST /v1/query`)

All Text-to-SQL requests from n8n must target:

```text
POST http://<t2s-host>:8000/v1/query
Content-Type: application/json
```

---

## 5. Safe Request Contract

The request payload is governed strictly by the `QueryRequest` OpenAPI schema.

### Schema Fields

| Field | Type | Required | Description / Usage in n8n |
| :--- | :--- | :---: | :--- |
| `question` | `string` (1..4000 chars) | **Yes** | Natural language business question. Whitespace-only values are rejected with 422. |
| `locale` | `string` (`"auto"`, `"vi"`, `"en"`) | No | Language hint. Default is `"auto"`. |
| `target_hint` | `string \| null` | No | Optional domain or entity hint (e.g. `"orders"`). |
| `client_request_id` | `string \| null` (max 128 chars) | No | **Pass `$execution.id` from n8n here for distributed tracking**. |
| `database_dialect` | `string \| null` | No | SQL dialect override (`"postgres"`, `"sqlite"`, etc.). |

*Forbidden Fields*: Any additional fields will be rejected with HTTP 422 (`extra="forbid"`).

### Synthetic Example Payload for n8n

```json
{
  "question": "How many completed orders were placed in the last 30 days?",
  "locale": "auto",
  "client_request_id": "n8n-exec-2026-09-16-00123"
}
```

---

## 6. Response Routing Contract in n8n

The `QueryResponse` model includes a top-level routing field: `status`.

```text
n8n HTTP Request Node
       │
       ▼
n8n Switch Node: Check value of {{$json.status}}
       ├─ "answer"     ──► Formatter / UI Delivery (Tabular rows in $json.answer.rows)
       ├─ "ambiguous"  ──► Interactive Clarification Dialogue ($json.explanation)
       ├─ "abstain"    ──► Safe Refusal Notice ($json.decision.reason)
       └─ "error"      ──► Incident Alert / Error Handler ($json.explanation)
```

### Route Descriptions

1. **`status == "answer"`**:
   - `answer.columns`: List of result table columns.
   - `answer.rows`: List of records `[{"column": value}, ...]`.
   - `sql`: Executed SQL query.
   - `explanation`: Model explanation.
2. **`status == "ambiguous"`**:
   - Query could not be deterministically resolved without user clarification.
   - `explanation`: Describes the clarification question for the user.
3. **`status == "abstain"`**:
   - Query was refused by security risk controller, semantic safety check, or lack of configured runtime.
   - `decision.policy`: Policy rule triggered.
   - `decision.reason`: Rationale for refusal.
4. **`status == "error"`**:
   - Internal failure during grounding, inference, or database execution.

---

## 7. Distributed Correlation & Tracing

T2S supports bidirectional distributed tracing. In n8n's HTTP Request node, configure the following:

### Outgoing Headers from n8n to T2S
* `x-request-id`: Set to `{{$execution.id}}` (or a generated UUID).
* `x-trace-id`: Set to trace ID if available from an upstream gateway.

### Correlation Echo & Logging
* T2S binds `x-request-id` and `x-trace-id` to its internal structured logs (`structlog`).
* T2S echoes both headers back in the HTTP response headers.
* T2S includes `request_id`, `run_id`, and `trace_id` in the body of both `QueryResponse` and `ErrorResponse`.
* This enables linking an n8n execution run directly to T2S server logs.

---

## 8. Network Assumptions & Architecture Isolation

* **Isolated Network**: T2S must reside on an internal Docker network, internal Kubernetes cluster network, or company private VPC subnet accessible only to the internal n8n runner.
* **Direct Database Isolation**:
  - n8n **must never** have direct database credentials.
  - All warehouse access is mediated through T2S's `PostgresReadOnlyQueryExecutor`, which enforces `SET TRANSACTION READ ONLY`, per-query statement timeouts, and row caps.

---

## 9. Lab Security Limitations

In the current codebase, the following security constraints apply to the **lab environment**:

1. **Service Authentication is Missing (`SERVICE_AUTH = MISSING`)**:
   - `/v1/query` does not currently check an API key or Bearer token.
   - Anyone on the local network that can reach port 8000 can invoke queries.
   - **Mitigation**: Do not place T2S on an untrusted shared corporate network; keep on a restricted lab network.
2. **Header-Based Identity Extraction (`IDENTITY_BOUNDARY = PARTIAL`)**:
   - The API extracts `x-user-id` and `x-user-roles` directly from HTTP headers without cryptographic validation.
   - In lab smoke testing, send only minimal safe user identity headers or omit them (T2S falls back to default `api-user`).
   - Do **not** send privileged roles (e.g. `x-user-roles: admin`) in testing.

---

## 10. Production Blockers (Pre-requisites for Enterprise Production)

Before moving beyond the internal lab to production enterprise usage, the following must be implemented:
1. **Service Authentication Middleware**: An authenticating proxy (or FastAPI dependency) verifying mutual TLS (mTLS), internal API tokens, or HMAC signatures between n8n and T2S.
2. **Cryptographic Identity Verification**: An enterprise SSO gateway verifying user JWT tokens before passing role headers to T2S.
3. **Ingress & TLS Termination**: HTTPS enforcement on port 443 with internal corporate DNS naming (e.g. `https://t2s.internal.company.com`).
4. **Active Database Readiness Probe**: Enhancing `/health/ready` to ping the PostgreSQL warehouse and vLLM provider before reporting ready.
