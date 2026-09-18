#!/usr/bin/env python3
"""V2-P04 governance guard: LIVE_WORKFLOW_PARITY.

Detects drift between the workflow ACTIVE in n8n and the workflow versioned in
Git. n8n adds/rewrites volatile fields (ids, positions, timestamps, versionId,
webhookId, meta, pinData) when a workflow is edited in the UI, so a byte-for-byte
compare is meaningless. Instead we extract a normalized *contract* from each and
compare only what governs behavior:

    - node types            (which kinds of nodes exist)
    - node names            (the pipeline shape by name)
    - connections           (name -> downstream names)
    - HTTP destination(s)    (url) and method
    - retry policy          (retryOnFail / onError per HTTP node)
    - absence of forbidden node classes (AI / DB / OpenMetadata)

Usage:
    verify_workflow_parity.py <versioned.json> <live_export.json>

Exit 0 and prints LIVE_WORKFLOW_PARITY=PASS when contract-equivalent; exit 1 and
prints the diff otherwise. Reads files only; no runtime side effects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FORBIDDEN_MARKERS = (
    "agent", "openai", "anthropic", "huggingface", "lmchat", "chainllm",
    "postgres", "mysql", "sqlite", "snowflake", "microsoftsql", "clickhouse",
    "questdb", "cratedb", "timescale", "executequery",
)


def _unwrap(doc: Any) -> dict[str, Any]:
    """n8n export wraps workflows in a list; the committed template is a dict."""
    if isinstance(doc, list):
        if len(doc) != 1:
            raise ValueError(f"expected exactly one workflow, got {len(doc)}")
        return doc[0]
    return doc


def extract_contract(doc: Any) -> dict[str, Any]:
    wf = _unwrap(doc)
    nodes = wf.get("nodes", [])
    node_types = sorted(str(n.get("type", "")).lower() for n in nodes)
    node_names = sorted(str(n.get("name", "")) for n in nodes)

    # connections: name -> sorted list of downstream node names (across all outputs)
    connections: dict[str, list[str]] = {}
    for src, outs in (wf.get("connections", {}) or {}).items():
        downstream: list[str] = []
        for out_list in (outs.get("main", []) or []):
            for link in (out_list or []):
                downstream.append(str(link.get("node", "")))
        connections[src] = sorted(downstream)

    http = []
    for n in nodes:
        if str(n.get("type", "")).lower().endswith("httprequest"):
            p = n.get("parameters", {}) or {}
            http.append({
                "url": str(p.get("url", "")),
                "method": str(p.get("method", "GET")).upper(),
                "retryOnFail": bool(n.get("retryOnFail", False)),
                "onError": str(n.get("onError", "")),
            })
    http.sort(key=lambda x: (x["url"], x["method"]))

    forbidden_present = sorted(
        {m for t in node_types for m in FORBIDDEN_MARKERS if m in t}
    )

    return {
        "node_types": node_types,
        "node_names": node_names,
        "connections": connections,
        "http": http,
        "forbidden_node_classes_present": forbidden_present,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    versioned = extract_contract(json.loads(Path(sys.argv[1]).read_text()))
    live = extract_contract(json.loads(Path(sys.argv[2]).read_text()))

    if versioned == live:
        print("LIVE_WORKFLOW_PARITY=PASS")
        print(json.dumps({"contract": versioned}, indent=2))
        return 0

    print("LIVE_WORKFLOW_PARITY=FAIL")
    diffs = {}
    for key in versioned:
        if versioned[key] != live.get(key):
            diffs[key] = {"versioned": versioned[key], "live": live.get(key)}
    print(json.dumps({"drift": diffs}, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
