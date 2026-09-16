"""Agent 04 — Metadata Quality and Provenance Auditor Script.

Audits whether Text-to-SQL failures genuinely require semantic/business knowledge
absent from the current catalog and schema, and constructs the authoritative
metadata provenance matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_git_info() -> tuple[str, str]:
    """Retrieve current git commit hash and working tree dirty status."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--short"], text=True
        ).strip()
        return commit, status
    except Exception:
        return "unknown", "unknown"


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 digest of a local file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class MetadataGapAuditor:
    """Audits metadata gaps and builds the provenance matrix for evaluation failures."""

    def __init__(
        self,
        failures_path: Path,
        dataset_path: Path,
        agent01_path: Path,
        definitions_path: Path,
        output_dir: Path,
    ) -> None:
        self.failures_path = failures_path
        self.dataset_path = dataset_path
        self.agent01_path = agent01_path
        self.definitions_path = definitions_path
        self.output_dir = output_dir

    def load_case_definitions(self) -> dict[str, dict[str, Any]]:
        if not self.definitions_path.exists():
            raise FileNotFoundError(
                f"Case definitions file not found: {self.definitions_path}"
            )
        data = json.loads(self.definitions_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(
                f"Case definitions must be a dictionary: {self.definitions_path}"
            )
        return data

    def audit(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        case_definitions = self.load_case_definitions()

        cases_by_id: dict[str, dict[str, Any]] = {}
        with self.dataset_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                cases_by_id[d["case_id"]] = d

        agent01_by_id: dict[str, dict[str, Any]] = {}
        if self.agent01_path.exists():
            with self.agent01_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    agent01_by_id[d["case_id"]] = d

        failures: list[dict[str, Any]] = []
        with self.failures_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                failures.append(json.loads(line))

        case_records: list[dict[str, Any]] = []
        provenance_matrix: list[dict[str, Any]] = []
        semantic_gap_counts: dict[str, int] = {}
        first_divergence_counts: dict[str, int] = {}
        provenance_level_counts: dict[str, int] = {}

        for idx, fail in enumerate(failures, 1):
            cid = fail["case_id"]
            ds_case = cases_by_id.get(cid, {})
            a01_case = agent01_by_id.get(cid, {})
            audit_meta = case_definitions.get(
                cid,
                {
                    "primary_semantic_gap": "UNKNOWN",
                    "secondary_semantic_gaps": [],
                    "semantic_fact": "Unclassified fact",
                    "currently_available_in_catalog": False,
                    "authoritative_source_available": False,
                    "provenance_level": "UNKNOWN",
                    "required_to_answer": True,
                    "safe_to_ingest_openmetadata": False,
                    "recommended_om_representation": "None",
                    "first_divergence_point": "UNKNOWN",
                    "root_cause_summary": "Unclassified case",
                },
            )

            primary_gap = audit_meta["primary_semantic_gap"]
            semantic_gap_counts[primary_gap] = (
                semantic_gap_counts.get(primary_gap, 0) + 1
            )

            fdp = audit_meta["first_divergence_point"]
            first_divergence_counts[fdp] = (
                first_divergence_counts.get(fdp, 0) + 1
            )

            prov_lvl = audit_meta["provenance_level"]
            provenance_level_counts[prov_lvl] = (
                provenance_level_counts.get(prov_lvl, 0) + 1
            )

            record = {
                "index": idx,
                "case_id": cid,
                "db_id": fail.get("db_id"),
                "question": ds_case.get("inference", {}).get("question"),
                "evidence": ds_case.get("inference", {}).get("evidence"),
                "gold_sql": ds_case.get("gold", {}).get("sql_original"),
                "generated_sql": fail.get("generated_sql"),
                "primary_semantic_gap": primary_gap,
                "secondary_semantic_gaps": audit_meta["secondary_semantic_gaps"],
                "semantic_fact": audit_meta["semantic_fact"],
                "currently_available_in_catalog": audit_meta[
                    "currently_available_in_catalog"
                ],
                "authoritative_source_available": audit_meta[
                    "authoritative_source_available"
                ],
                "provenance_level": prov_lvl,
                "required_to_answer": audit_meta["required_to_answer"],
                "safe_to_ingest_openmetadata": audit_meta[
                    "safe_to_ingest_openmetadata"
                ],
                "recommended_om_representation": audit_meta[
                    "recommended_om_representation"
                ],
                "first_divergence_point": fdp,
                "agent01_primary_cause": a01_case.get("primary_cause"),
                "root_cause_summary": audit_meta["root_cause_summary"],
            }
            case_records.append(record)

            provenance_matrix.append(
                {
                    "case_id": cid,
                    "db_id": fail.get("db_id"),
                    "fact": audit_meta["semantic_fact"],
                    "primary_gap_type": primary_gap,
                    "currently_available_in_catalog": audit_meta[
                        "currently_available_in_catalog"
                    ],
                    "authoritative_source_available": audit_meta[
                        "authoritative_source_available"
                    ],
                    "provenance_level": prov_lvl,
                    "required_to_answer": audit_meta["required_to_answer"],
                    "safe_to_ingest_openmetadata": audit_meta[
                        "safe_to_ingest_openmetadata"
                    ],
                    "recommended_om_representation": audit_meta[
                        "recommended_om_representation"
                    ],
                }
            )

        # Write metadata_gap_cases.jsonl
        cases_file = self.output_dir / "metadata_gap_cases.jsonl"
        with cases_file.open("w", encoding="utf-8") as f:
            for rec in case_records:
                f.write(json.dumps(rec) + "\n")

        # Write provenance_matrix.json
        matrix_file = self.output_dir / "provenance_matrix.json"
        with matrix_file.open("w", encoding="utf-8") as f:
            json.dump(provenance_matrix, f, indent=2)

        # Compute aggregate metrics
        total_failures = len(failures)
        no_gap_count = semantic_gap_counts.get("NO_METADATA_GAP_IDENTIFIED", 0)
        genuine_semantic_gaps = total_failures - no_gap_count

        metrics = {
            "total_evaluated_cases": 85,
            "total_failed_cases": total_failures,
            "cases_with_no_metadata_gap": no_gap_count,
            "cases_with_genuine_semantic_gaps": genuine_semantic_gaps,
            "percentage_genuine_semantic_gaps": round(
                genuine_semantic_gaps / total_failures * 100, 2
            ),
            "percentage_no_metadata_gap": round(
                no_gap_count / total_failures * 100, 2
            ),
            "semantic_gap_distribution": semantic_gap_counts,
            "first_divergence_distribution": first_divergence_counts,
            "provenance_level_distribution": provenance_level_counts,
            "safe_for_openmetadata_ingestion_count": sum(
                1 for p in provenance_matrix if p["safe_to_ingest_openmetadata"]
            ),
            "unsafe_or_inappropriate_count": sum(
                1
                for p in provenance_matrix
                if not p["safe_to_ingest_openmetadata"]
            ),
        }

        metrics_file = self.output_dir / "metrics.json"
        with metrics_file.open("w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        # Write manifest.json
        commit, status = get_git_info()
        manifest = {
            "audit_agent": "Agent 04 — Metadata Quality and Provenance Auditor",
            "evaluated_baseline": "results/causal_evaluation/arm_f0_planner_off/",
            "git_commit": commit,
            "git_dirty": bool(status),
            "created_at": datetime.now(UTC).isoformat(),
            "failures_sha256": compute_file_sha256(self.failures_path),
            "dataset_sha256": compute_file_sha256(self.dataset_path),
            "artifact_hashes": {
                "metadata_gap_cases.jsonl": compute_file_sha256(cases_file),
                "provenance_matrix.json": compute_file_sha256(matrix_file),
                "metrics.json": compute_file_sha256(metrics_file),
            },
        }

        manifest_file = self.output_dir / "manifest.json"
        with manifest_file.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent 04 Metadata Gap Auditor"
    )
    parser.add_argument(
        "--failures",
        type=Path,
        default=Path(
            "results/causal_evaluation/arm_f0_planner_off/failures.jsonl"
        ),
        help="Path to failures.jsonl",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"),
        help="Path to t2s_pilot_v1.jsonl",
    )
    parser.add_argument(
        "--agent01",
        type=Path,
        default=Path(
            "results/audits/system_bottleneck/agent_01_context_sufficiency/case_classification.jsonl"
        ),
        help="Path to agent 01 case classifications",
    )
    parser.add_argument(
        "--definitions",
        type=Path,
        default=Path(
            "results/audits/system_bottleneck/agent_04_metadata_gap/case_definitions.json"
        ),
        help="Path to case definitions JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "results/audits/system_bottleneck/agent_04_metadata_gap"
        ),
        help="Output directory for audit artifacts",
    )
    args = parser.parse_args()

    auditor = MetadataGapAuditor(
        failures_path=args.failures,
        dataset_path=args.dataset,
        agent01_path=args.agent01,
        definitions_path=args.definitions,
        output_dir=args.output,
    )
    metrics = auditor.audit()
    print("=== Agent 04 Metadata Gap Audit Complete ===")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
