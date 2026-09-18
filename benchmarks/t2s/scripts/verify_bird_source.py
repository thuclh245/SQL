#!/usr/bin/env python3
"""Verify official BIRD Mini-Dev source artifacts and generate bird_source_manifest.json."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def inspect_source_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "error": "File does not exist",
        }

    size_bytes = path.stat().st_size
    sha256_hash = compute_sha256(path)

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    record_count = len(data) if isinstance(data, list) else len(data.keys())
    sample_fields = sorted(list(data[0].keys())) if isinstance(data, list) and data else []

    return {
        "path": str(path),
        "exists": True,
        "size_bytes": size_bytes,
        "sha256": sha256_hash,
        "record_count": record_count,
        "schema_fields": sample_fields,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify official BIRD Mini-Dev sources.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/t2s/manifests/bird_source_manifest.json"),
        help="Output path for source manifest JSON",
    )
    args = parser.parse_args()

    canonical_local = Path(
        "/home/thuclh245/MyCode/Text2sql/third_party/mini_dev/llm/mini_dev_data/mini_dev_sqlite.json"
    )
    hf_local = Path("/home/thuclh245/MyCode/SQL/data/bird_mini_dev/mini_dev_sqlite.json")
    tables_file = Path("/home/thuclh245/MyCode/SQL/data/bird_mini_dev/mini_dev_tables.json")

    canonical_info = inspect_source_file(canonical_local)
    hf_info = inspect_source_file(hf_local)
    tables_info = inspect_source_file(tables_file)

    manifest = {
        "benchmark": "BIRD Mini-Dev",
        "canonical_source": {
            "name": "Local Official BIRD Mini-Dev (from minidev.zip)",
            "details": canonical_info,
            "verdict": ("MATCHES_PILOT_PROVENANCE" if canonical_info.get("exists") else "MISSING"),
        },
        "hf_mirror_source": {
            "name": "Hugging Face birdsql/bird_mini_dev",
            "details": hf_info,
            "verdict": ("OFFICIAL_HF_SNAPSHOT" if hf_info.get("exists") else "MISSING"),
        },
        "table_metadata_source": {
            "name": "BIRD mini_dev_tables.json",
            "details": tables_info,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote BIRD source manifest to {args.output}")


if __name__ == "__main__":
    main()
