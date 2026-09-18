# T2S / CHATSQL — V2-P04 n8n Orchestration Layer

Thin internal orchestration/UI layer that calls the certified T2S API. n8n is a
**transport boundary only** — it does **not** generate SQL, call an LLM, query
OpenMetadata, or touch the database. There is exactly **one** Text-to-SQL
pipeline:

```
User → n8n (webhook) → HTTP POST /v1/query → T2S → response → n8n renders
```

## Components

- `docker-compose.yml` — n8n `2.39.7` under Docker, **host networking**, bound to
  `127.0.0.1:5678` (LOCAL_ONLY), persistent named volume `t2s_n8n_data`.
- `workflows/t2s_query_orchestration.json` — the single P04 workflow (sanitized,
  no secrets). Webhook `POST /webhook/t2s-query` → normalize → `POST /v1/query`
  → normalize → respond.

## Why host networking

T2S binds `127.0.0.1:8000` (loopback only, not public). A bridge-network
container cannot reach a loopback-only host service via the docker gateway. Host
networking lets n8n reach `http://127.0.0.1:8000` while T2S stays loopback-only.
n8n is pinned to `127.0.0.1` via `N8N_LISTEN_ADDRESS`, so nothing is exposed
beyond the host loopback. No AWS security-group change is required or made.

## Secrets

None required in this layer. n8n calls T2S; T2S owns the OpenMetadata token, LLM
key, and DB credentials. The n8n encryption key is auto-generated and persisted
inside the named volume (never committed). This directory contains **no secrets**.

## Operate

```bash
cd /home/ubuntu/SQL/deploy/n8n
sudo docker compose up -d            # start
sudo docker compose restart          # restart (state persists in t2s_n8n_data)
sudo docker compose logs --tail=50   # logs
```

Import + activate the workflow (already done during P04 certification):

```bash
sudo docker cp workflows/t2s_query_orchestration.json t2s-n8n:/tmp/wf.json
sudo docker exec t2s-n8n n8n import:workflow --input=/tmp/wf.json
sudo docker exec t2s-n8n n8n publish:workflow --id=P04T2SQueryFlow1
sudo docker compose restart
```

## Access the UI (operator, local-only)

The UI is not publicly exposed. Reach it via SSH port-forward:

```bash
ssh -N -L 5678:127.0.0.1:5678 ubuntu@<ec2-host>
# then open http://127.0.0.1:5678 on your laptop
```

## Call the pipeline

```bash
curl -s -X POST http://127.0.0.1:5678/webhook/t2s-query \
  -H 'Content-Type: application/json' \
  -d '{"question":"How many customers are there in each segment?","locale":"en"}'
```

The response preserves T2S decision semantics verbatim (`status`, `decision`,
`sql`, `answer`, `explanation`, `warnings`) plus `http_status`, the T2S
`request_id/run_id/trace_id`, and the `n8n_execution_id`. The n8n execution id is
propagated to T2S as the `x-request-id` header (T2S `request_id = "n8n-<id>"`),
giving end-to-end correlation. Abstentions stay abstentions; errors stay errors;
n8n never fabricates SQL or a success.

## Retention / privacy (LAB)

Successful execution payloads are not persisted (`EXECUTIONS_DATA_SAVE_ON_SUCCESS=none`);
error executions are kept for debugging (`EXECUTIONS_DATA_SAVE_ON_ERROR=all`);
everything is pruned after 7 days (`EXECUTIONS_DATA_PRUNE=true`, `MAX_AGE=168`).
No T2S secrets, tokens, or DB credentials pass through or are stored by n8n.
