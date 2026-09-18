"""Architecture guard (V2-P04): n8n must remain a thin transport layer.

Enforces the hard invariant that there is exactly ONE Text-to-SQL pipeline:

    User -> n8n -> HTTP POST /v1/query -> T2S

The committed n8n workflow(s) must NOT embed a second pipeline: no LLM/AI-agent
node, no SQL generation/execution node, no direct database node, and no direct
OpenMetadata grounding node. n8n may only normalize transport and call T2S over
HTTP. This test is deterministic and reads only the committed workflow JSON.
"""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_DIR = PROJECT_ROOT / "deploy" / "n8n" / "workflows"

# Node types that would make n8n a second reasoning/SQL/data pipeline.
FORBIDDEN_NODE_TYPE_MARKERS = (
    "agent",           # AI agent nodes
    "openai",          # direct LLM nodes
    "anthropic",
    "huggingface",
    "lmchat",
    "chainllm",
    "postgres",        # direct DB nodes
    "mysql",
    "sqlite",
    "snowflake",
    "microsoftsql",
    "clickhouse",
    "questdb",
    "cratedb",
    "timescale",
    "executequery",
)

# The single allowed egress: the T2S query API.
ALLOWED_HTTP_URL_SUBSTRING = "/v1/query"

WORKFLOW_FILES = sorted(WORKFLOW_DIR.glob("*.json")) if WORKFLOW_DIR.exists() else []


def test_workflow_directory_has_at_least_one_workflow() -> None:
    assert WORKFLOW_FILES, f"expected at least one n8n workflow under {WORKFLOW_DIR}"


@pytest.mark.parametrize("wf_path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_workflow_is_thin_transport_only(wf_path: Path) -> None:
    workflow = json.loads(wf_path.read_text())
    nodes = workflow.get("nodes", [])
    assert nodes, f"{wf_path.name}: workflow has no nodes"

    node_types = [str(n.get("type", "")).lower() for n in nodes]

    # No forbidden reasoning/SQL/DB/grounding node types.
    for node_type in node_types:
        for marker in FORBIDDEN_NODE_TYPE_MARKERS:
            assert marker not in node_type, (
                f"{wf_path.name}: forbidden node type '{node_type}' "
                f"(marker '{marker}') — n8n must not embed a second pipeline"
            )

    # Every HTTP request egress must target the T2S /v1/query contract only.
    http_urls = [
        str(n.get("parameters", {}).get("url", ""))
        for n in nodes
        if str(n.get("type", "")).lower().endswith("httprequest")
    ]
    assert http_urls, f"{wf_path.name}: expected at least one HTTP Request node calling T2S"
    for url in http_urls:
        assert ALLOWED_HTTP_URL_SUBSTRING in url, (
            f"{wf_path.name}: HTTP node URL '{url}' does not target {ALLOWED_HTTP_URL_SUBSTRING}"
        )


@pytest.mark.parametrize("wf_path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_workflow_contains_no_obvious_secret(wf_path: Path) -> None:
    text = wf_path.read_text()
    for marker in ("sk-", "Bearer ey", "OPENMETADATA_AUTH_TOKEN", "POSTGRES_PASSWORD"):
        assert marker not in text, f"{wf_path.name}: possible secret marker '{marker}' committed"
