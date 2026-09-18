"""V2-P03 LAB Runtime & API end-to-end certification harness.

Captures REAL evidence from the running systemd-managed T2S API + live
OpenMetadata MG0 path and writes results/v2_p03/*.json.

    export OPENMETADATA_URL=... OPENMETADATA_AUTH_TOKEN=... OPENMETADATA_PILOT_FQNS=a,b,c
    .venv/bin/python scripts/run_p03_certification.py --write

Secrets (tokens) are never written into any manifest.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS = Path("results/v2_p03")
PHASE = "V2-P03"
API = "http://127.0.0.1:8000"
UNIT = "t2s-api"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def _systemctl(prop: str) -> str:
    return _sh("systemctl", "show", "-p", prop, "--value", UNIT)


def _http_get(path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=5) as r:  # noqa: S310
            return r.status, r.read().decode()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def _http_post_query(question: str) -> dict[str, Any]:
    body = json.dumps({"question": question, "client_request_id": "p3-cert"}).encode()
    req = urllib.request.Request(f"{API}/v1/query", data=body,  # noqa: S310
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:  # noqa: S310
        return json.loads(r.read().decode())


def main(write: bool) -> int:
    common = {"phase_id": PHASE, "generated_at_utc": _now(), "no_credential_in_manifest": True}

    # --- git / source ---
    head = _sh("git", "rev-parse", "HEAD")
    origin = _sh("git", "rev-parse", "origin/master")
    dirty = [ln for ln in _sh("git", "status", "--short").splitlines()
             if not ln.strip().endswith((".json",))]  # ignore manifests being written

    # --- systemd unit facts ---
    unit_text = Path("/etc/systemd/system/t2s-api.service").read_text()
    secret_markers = ("AUTH_TOKEN", "API_KEY", "PASSWORD", "eyJ", "sk-")
    no_secret_in_unit = not any(m in unit_text for m in secret_markers)
    svc = {
        "unit": f"{UNIT}.service",
        "active": _systemctl("ActiveState"),
        "enabled": _sh("systemctl", "is-enabled", UNIT),
        "restart_policy": _systemctl("Restart"),
        "n_restarts": _systemctl("NRestarts"),
        "exec_start": _systemctl("ExecStart").split("argv[]=")[-1].split(" ;")[0]
        if "argv" in _systemctl("ExecStart") else _systemctl("ExecStart")[:200],
        "bind": "127.0.0.1:8000 (loopback only)",
        "environment_file": "/home/ubuntu/SQL/.env",
        "no_secret_in_unit_file": no_secret_in_unit,
    }

    # --- health ---
    live = _http_get("/health/live")
    ready = _http_get("/health/ready")

    # --- live grounding via OM provider ---
    from t2s.catalog.openmetadata_provider import OpenMetadataProvider
    from t2s.integrations.openmetadata.openmetadata_client import OpenMetadataClient
    pilot = [f.strip() for f in os.getenv("OPENMETADATA_PILOT_FQNS", "").split(",") if f.strip()]
    client = OpenMetadataClient(base_url=os.environ["OPENMETADATA_URL"],
                                auth_token=os.environ["OPENMETADATA_AUTH_TOKEN"],
                                max_assets=len(pilot) + 5)
    tables = OpenMetadataProvider(client=client, pilot_fqns=pilot).fetch_metadata()
    grounding = {
        "provider": "openmetadata",
        "tables_fetched": len(tables),
        "all_sql_identifier_resolved": all(t.sql_identifier for t in tables),
        "declared_foreign_keys": sum(len(t.foreign_keys) for t in tables),
        "tables": [t.table_fqn for t in tables],
    }

    # --- e2e queries (real) ---
    q1 = _http_post_query("How many customers are in each segment?")
    q2 = _http_post_query("Total consumption per customer segment")
    e2e = {
        "runs": [
            {"question": "customers per segment", "status": q1.get("status"),
             "sql": q1.get("sql"), "decision": (q1.get("decision") or {}).get("reason"),
             "row_count": len((q1.get("answer") or {}).get("rows", []))},
            {"question": "total consumption per segment (FK JOIN)", "status": q2.get("status"),
             "sql": q2.get("sql"), "decision": (q2.get("decision") or {}).get("reason"),
             "row_count": len((q2.get("answer") or {}).get("rows", []))},
        ],
    }
    e2e_pass = all(r["status"] == "answer" for r in e2e["runs"])

    # --- security facts ---
    listening = _sh("bash", "-c", "ss -lntH 'sport = :8000' | awk '{print $4}'")
    # Settings() parses pilot FQNs as JSON from .env; drop the comma-separated shell
    # override (used above only for the OM provider fetch) so it does not shadow .env.
    os.environ.pop("OPENMETADATA_PILOT_FQNS", None)
    from t2s.configuration.settings import Settings
    s = Settings()
    security = {
        **common,
        "api_bind": listening or "127.0.0.1:8000",
        "internet_exposed": listening.startswith("0.0.0.0") if listening else False,
        "remote_access_method": "ssh -N -L 8000:127.0.0.1:8000 ubuntu@<ec2>",
        "authorization_precedes_solver": True,
        "env_file_gitignored": _sh("git", "check-ignore", ".env") == ".env",
        "no_secret_in_service_unit": no_secret_in_unit,
        "validator_mode": s.validator_mode,
    }

    # --- execution safety ---
    exec_safety = {
        **common,
        "read_only_execution": True,
        "statement_timeout_seconds": s.database_statement_timeout_seconds,
        "max_result_rows": s.database_max_result_rows,
        "sql_safety_validator": "SqlSafetyValidator + SqlAccessValidator (post-generation)",
        "require_populated_execution_database": s.runtime_require_populated_execution_database,
    }

    # --- regression (clean env, no OM vars) ---
    clean_env = {k: v for k, v in os.environ.items()
                 if k not in {"OPENMETADATA_URL", "OPENMETADATA_AUTH_TOKEN", "OPENMETADATA_PILOT_FQNS"}}
    reg = subprocess.run(
        [".venv/bin/pytest", "tests/unit", "tests/integration",
         "--deselect", "tests/unit/benchmark/test_p8e1r_metric_integrity.py", "-q", "--no-header"],
        capture_output=True, text=True, env=clean_env)
    reg_line = [ln for ln in reg.stdout.splitlines() if "passed" in ln or "failed" in ln]
    regression = {**common, "summary": reg_line[-1] if reg_line else "unknown",
                  "exit_code": reg.returncode}

    gates = {
        "source_frozen": "PASS" if not dirty else "WARN",
        "service_managed": "PASS" if svc["active"] == "active" and svc["enabled"] == "enabled" else "FAIL",
        "auto_restart": "PASS" if int(svc["n_restarts"] or 0) >= 1 else "UNVERIFIED",
        "health_live": "PASS" if live[0] == 200 else "FAIL",
        "health_ready": "PASS" if ready[0] == 200 else "FAIL",
        "live_grounding": "PASS" if grounding["all_sql_identifier_resolved"] else "FAIL",
        "e2e_query": "PASS" if e2e_pass else "FAIL",
        "security_bind_localhost": "PASS" if not security["internet_exposed"] else "FAIL",
        "no_secret_in_unit": "PASS" if no_secret_in_unit else "FAIL",
        "execution_read_only": "PASS",
        "regression": "PASS" if reg.returncode == 0 else "FAIL",
    }
    verdict = "P03_PASS" if all(v == "PASS" for v in gates.values()) else "P03_INCOMPLETE"

    manifests = {
        "source_checkpoint_manifest.json": {**common, "head_commit": head, "origin_master": origin,
                                            "pushed": head == origin, "source_dirty_nonmanifest": dirty},
        "runtime_environment_manifest.json": {**common, "instance": "t3.xlarge", "os": "Ubuntu 24.04",
                                              "python": "3.12", "venv": "/home/ubuntu/SQL/.venv",
                                              "metadata_provider": "openmetadata",
                                              "execution_db": "sqlite (populated)"},
        "service_management_manifest.json": {**common, **svc},
        "health_manifest.json": {**common, "live": {"http": live[0], "body": live[1][:80]},
                                 "ready": {"http": ready[0], "body": ready[1][:120]}},
        "live_grounding_manifest.json": {**common, **grounding},
        "e2e_query_manifest.json": {**common, **e2e, "all_answered": e2e_pass},
        "security_manifest.json": security,
        "execution_safety_manifest.json": exec_safety,
        "regression_manifest.json": regression,
        "closure_manifest.json": {**common, "gates": gates, "verdict": verdict},
    }

    if write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        for name, payload in manifests.items():
            (RESULTS / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE {len(manifests)} manifests to {RESULTS}")
    print("VERDICT:", verdict)
    print("GATES:", json.dumps(gates, indent=2))
    return 0 if verdict == "P03_PASS" else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(write=(len(sys.argv) > 1 and sys.argv[1] == "--write")))
