# V2-P04 — n8n Integration, Internal UI Orchestration & End-to-End LAB Certification

**Phase:** V2-P04 (integration + verification + certification)
**Environment:** EC2 LAB (`/home/ubuntu/SQL`), Ubuntu 24.04.4 LTS, Docker Compose v5.5.0
**Date:** 2026-09-18
**Scope reminder:** P04 connects n8n as a **thin transport/orchestration** layer in front of the certified T2S `/v1/query` API. n8n must **not** become a second Text-to-SQL pipeline. P04 is not an accuracy phase and not an RBAC phase.

---

## 1. Executive Summary

n8n **2.39.7** runs under Docker (host networking, bound `127.0.0.1:5678`, persistent volume `t2s_n8n_data`) as an internal orchestration layer that calls **T2S `POST /v1/query`** and nothing else. A single webhook workflow normalizes transport, forwards the user question to T2S, and returns T2S's decision **verbatim**. End-to-end through n8n: single-table aggregation and a **declared-FK join** succeed; an out-of-scope question **stays an abstention** (no fabricated SQL); malformed input surfaces T2S's structured 422 (no fabricated success). The n8n execution id propagates to T2S as `x-request-id` (T2S `request_id = "n8n-<id>"`), verified in T2S logs. T2S remains loopback-only and unchanged; the T2S deterministic suite stays green (547 passed, 5 skipped, 0 failed), runtime ruff + mypy clean. No secrets committed or logged; no public exposure.

**Verdict: `PASS_WITH_CONDITIONS`** — carried non-core conditions only (live authorization remains PARTIAL, repo-wide ruff debt in `scripts/`, external-artifact tests skip, remote push pending operator credentials). The one-pipeline architecture invariant holds and is enforced by a new architecture guard.

---

## 2. Source Checkpoint

| Item | Value |
|---|---|
| HEAD (baseline) | `33afb24` |
| origin/master (local ref) | `33afb24` |
| Actual remote master (`git ls-remote`) | `33afb24` |
| Baseline classification | **CLEAN_SYNCED** |

P04 changes are committed on top of this synced baseline. The prior P03 finalization commit is present on the remote.

---

## 3. P03 Prerequisite — Verified

P03 verdict `PASS_WITH_CONDITIONS`. Live T2S baseline before P04: `t2s-api` **active + enabled**, `/health/live` **200**, `/health/ready` **200**, bind `127.0.0.1:8000` (unchanged). Carried condition **LIVE_METADATA_AUTHORIZATION = PARTIAL** is preserved, not upgraded. `P03_RUNTIME_BASELINE = PASS`.

---

## 4. n8n Deployment

- **Existing state before P04:** NOT_FOUND (no container/image/binary/volume).
- **Method:** Docker Compose (`deploy/n8n/docker-compose.yml`), image `n8nio/n8n:2.39.7`, container `t2s-n8n`, `network_mode: host`, `restart: unless-stopped`.
- **Persistence:** named volume `t2s_n8n_data` → `/var/lib/docker/volumes/t2s_n8n_data/_data` (outside the repo). SQLite backend (n8n default) — no separate DB provisioned; OpenMetadata/BIRD/olist DBs untouched.
- **Secrets:** none required in this layer. n8n encryption key auto-generated and persisted in the volume (redacted, not committed). Compose and workflow contain no secrets.
- **Retention (privacy):** `SAVE_ON_SUCCESS=none`, `SAVE_ON_ERROR=all`, `PRUNE=true`, `MAX_AGE=168h`. Telemetry disabled.

**Persistence + restart test:** `docker compose restart` → n8n healthy in 4 s, workflow still present, webhook functional. **PERSISTENCE = PASS, RESTART = PASS.**

---

## 5. Network Boundary

| Service | Bind | Exposure |
|---|---|---|
| T2S | `127.0.0.1:8000` | not public (unchanged) |
| n8n UI/webhook | `127.0.0.1:5678` | **LOCAL_ONLY** |

**Why host networking:** T2S is loopback-only; a bridge container cannot reach it via the docker gateway (`172.17.0.1`), because T2S does not listen there. Host networking shares the EC2 network namespace so n8n reaches `http://127.0.0.1:8000/v1/query`, while `N8N_LISTEN_ADDRESS=127.0.0.1` keeps n8n itself loopback-only. `ss` confirms **no `0.0.0.0` listener** for 5678/8000. No AWS security-group change made. Operator reaches the UI via SSH port-forward (`ssh -N -L 5678:127.0.0.1:5678`).

---

## 6. Workflow (one pipeline)

`deploy/n8n/workflows/t2s_query_orchestration.json` (id `P04T2SQueryFlow1`, active). Nodes: **Webhook → Code (normalize request) → HTTP Request `POST /v1/query` → Code (normalize response) → Respond to Webhook**. Egress targets **only** `/v1/query`.

- SQL-generation logic in n8n: **ABSENT**
- LLM / AI-agent node: **ABSENT**
- Direct DB access: **ABSENT**
- Direct OpenMetadata grounding: **ABSENT**
- **Retry:** `retryOnFail=false` — no semantic retry; exactly one T2S execution per request (`validator.completed` = 1 per run).

**Architecture guard (new):** `tests/unit/architecture/test_n8n_workflow_boundary.py` scans committed workflows and fails on any LLM/AI/SQL/DB/OM node type or any non-`/v1/query` HTTP egress (and on committed secrets). **3 tests PASS** (architecture suite now 38).

Contract used matches the live FastAPI schema — request required field `question` (+ `evidence/locale/target_hint/client_request_id/database_dialect`); response `request_id/run_id/trace_id/status/answer/sql/explanation/decision/evidence_summary/warnings`.

---

## 6a. Live vs Versioned Workflow Parity (drift guard)

Governance concern: someone edits the workflow in the n8n UI, so the **active**
workflow drifts from the **committed** one while Git stays clean. Guard:
`deploy/n8n/verify_workflow_parity.py` exports the active workflow, normalizes
volatile fields (ids, positions, timestamps, versionId, webhookId, meta), and
compares the behavioral **contract**: node types, node names, connections, HTTP
destination + method, retry policy, and absence of AI/DB/OpenMetadata node
classes.

- Result: **`LIVE_WORKFLOW_PARITY = PASS`** — versioned and live contract hashes
  are identical (`sha256:d966e1b4…`); single HTTP egress `POST /v1/query`,
  `retryOnFail=false`, no forbidden node classes.
- Falsification: a tampered export (injected OpenAI node + retry flip) correctly
  returns `FAIL` (exit 1), proving the guard detects real drift.
- Evidence: `results/v2_p04/live_workflow_parity_manifest.json`.

## 7. Correlation

`n8n $execution.id → x-request-id header → T2S request_id` (echoed in the response and present in T2S structured logs). Example: `n8n_execution_id=1 → t2s_request_id="n8n-1"` with `run_id`/`trace_id` server-generated and preserved. **CORRELATION = PASS.**

---

## 8. End-to-End (through n8n, generic questions — NOT benchmark, NO gold SQL)

| Case | Category | T2S status | SQL | Rows | Fingerprint | Latency | Semantic |
|---|---|---|---|---|---|---|---|
| A | single-table agg | answer | `SELECT Segment, COUNT(*) … GROUP BY Segment` | 3 | `sha256:…` | ~4.2 s | NOT_ASSESSED |
| B | declared-FK join | answer | `… SUM(y.Consumption) FROM yearmonth y JOIN customers c ON y.CustomerID=c.CustomerID …` | 3 | `sha256:…` | ~12.1 s | NOT_ASSESSED |
| C | out-of-scope | **abstain** (`unresolved`) | *(none)* | 0 | — | ~0.08 s | N/A |

- **Declared FK re-verified in LIVE OpenMetadata** (not trusted historically): `yearmonth` `tableConstraints` contains `FOREIGN_KEY CustomerID → customers.CustomerID`. The workflow does not know this FK; it sends only the question — T2S performs grounding.
- **Abstention preserved (mandatory invariant):** Case C returns `status=abstain`, `sql=null`, `answer=null`; n8n did **not** fabricate SQL/answer or retry.
- **Error path:** blank/whitespace and missing-question inputs surface T2S's structured **422** with `http_status`, no fabricated success.

**Accuracy rule honored:** `semantic_correctness = NOT_ASSESSED` — execution success proves the orchestration/transport path works, not SQL correctness.

---

## 9. Regression / Lint / Types

| Suite | Result |
|---|---|
| Core deterministic (`tests/unit` + `tests/integration`) | **547 passed, 0 failed, 5 skipped** |
| Architecture guards | **38 passed** (incl. new n8n boundary guard) |
| External-artifact tests | 3 **SKIP** on clean checkout (unchanged; not converted to PASS) |
| Runtime ruff (`src/t2s`) | **PASS** |
| P04-changed-files ruff | **PASS** (new test only; no runtime Python changed) |
| Repository-wide ruff | **DEBT_PRESENT** (pre-existing `scripts/` debt; zero in runtime; unchanged by P04) |
| Mypy (strict, 153 files) | **PASS** |

No T2S production source changed; MG0 unchanged; no new grounding capability activated.

---

## 10. Security / Leakage

L1_PROMPT PASS · L2_T2S_RUNTIME PASS · L3_OPENMETADATA PASS · L4_N8N_WORKFLOW PASS · L5_TEST PASS · L6_LOG PASS (t2s journal JWT=0; n8n logs sk-keys=0) · L7_NETWORK PASS · L8_N8N_STATE PASS · L9_SECRETS PASS. Secret leakage **NOT_DETECTED**; workflow secret exposure **NOT_DETECTED**; public unintended exposure **NOT_DETECTED**; benchmark/gold contamination **NOT_DETECTED**.

---

## 11. Resources

RAM 15 GiB (≈9.2 GiB available), root disk 58 G free (41% used), n8n container ≈348 MiB / ~0.2% CPU. OpenMetadata + Elasticsearch + T2S + n8n coexist comfortably. **RESOURCE_STATUS = HEALTHY_FOR_LAB.** No load testing; no EC2 resize.

---

## 12. Self-Review (falsification attempt)

n8n calls `/v1/query` (not bypassed) ✓ · no AI/SQL/DB/OM node in n8n (guard-enforced) ✓ · T2S is the only solver ✓ · OM/DB reached only through T2S ✓ · no secret in workflow/logs ✓ · n8n & T2S local-only ✓ · no semantic retry ✓ · abstention stays abstention ✓ · request IDs traceable ✓ · workflow survives restart ✓ · deploy template retained in a clean checkout ✓ · Grounding unchanged ✓ · semantic correctness not overclaimed ✓ · live authz reported PARTIAL (not upgraded) ✓ · repo-wide ruff debt not hidden ✓ · skipped external artifacts not called PASS ✓.

---

## 13. Conditions & Next Phase

**Non-blocking:** (1) LIVE_METADATA_AUTHORIZATION = PARTIAL (carried from P03); (2) repo-wide ruff DEBT_PRESENT in `scripts/`; (3) external-artifact tests SKIP on clean checkout; (4) remote push pending operator git credentials.

**Recommended next phase (evidence-driven):** identity/RBAC hardening to convert live authorization from PARTIAL → VERIFIED (a real two-principal differential policy), enabling a controlled multi-user LAB. Do not begin before P04 evidence is accepted.

---

## V2-P04 FINAL DECISION
See the FINAL DECISION BLOCK returned with this phase (mirrored in `results/v2_p04/closure_manifest.json`).
