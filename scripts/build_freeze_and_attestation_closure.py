#!/usr/bin/env python3
"""
Closure script for Reviewer Attestation, Exposure Ledger Correction,
and Certified Cohort Reassessment.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path("/home/thuclh245/MyCode/SQL")
GOV_DIR = REPO_ROOT / "results" / "security" / "enterprise_validation_governance"
REPORT_DIR = REPO_ROOT / "reports" / "security"
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "t2s" / "independent_validation"
CHATSQL_REF_DIR = Path("/home/thuclh245/MyCode/ChatSQL/data/benchmark/reference_sql")

def sha256_file(filepath: Path) -> str:
    if not filepath.exists():
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    GOV_DIR.mkdir(parents=True, exist_ok=True)
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Reviewer Attestation (Sections 2, 3, 4)
    reviewer_attestation = {
        "attestation_timestamp": now_iso,
        "reviewer_id": "ai_agent_t2s_governance_auditor",
        "reviewer_type": "AI_GOVERNANCE_AGENT",
        "reviewer_role": "GOVERNANCE_AUDITOR_AGENT",
        "gold_author_overlap": False,
        "solver_development_overlap": True,
        "prompt_development_overlap": True,
        "grounding_development_overlap": True,
        "validator_development_overlap": True,
        "dataset_authoring_overlap": False,
        "evaluation_execution_role": "BENCHMARK_AND_GOVERNANCE_SCRIPT_RUNNER",
        "evidence_paths": [
            "scripts/build_cohort_certification.py",
            "results/security/enterprise_validation_governance/role_separation_audit.json"
        ],
        "reviewer_separation_decision": "REVIEWER_SEPARATION_FAILED",
        "attestation_statement": (
            "The semantic review of candidate Gold SQL was performed by an AI coding/governance agent "
            "operating within the active T2S development repository. Under governance policy (Sections 2-4), "
            "an AI agent cannot be classified as an INDEPENDENT_HUMAN_REVIEWER. Because the agent participates "
            "in repository tasks involving solver, prompt, grounding, and validator development, institutional "
            "separation of duties cannot be established. Consequently, reviewer separation is evaluated as "
            "REVIEWER_SEPARATION_FAILED for independent certification purposes."
        )
    }
    with open(GOV_DIR / "reviewer_attestation.json", "w") as f:
        json.dump(reviewer_attestation, f, indent=2)

    # 2. Protected Exposure Correction (Sections 5, 6, 7)
    protected_exposure_correction = {
        "correction_timestamp": now_iso,
        "affected_cases": [
            "OLIST-0035",
            "OLIST-0036",
            "OLIST-0037",
            "OLIST-0038",
            "OLIST-0039",
            "OLIST-0040"
        ],
        "governance_reviewer_semantic_exposure": True,
        "exposure_type": "SEMANTIC_INTENT_INSPECTION_DURING_GOVERNANCE_CLASSIFICATION",
        "prior_claim_correction": (
            "The previous certification report claimed 'zero protected data disclosure' and 'never inspected'. "
            "This statement is corrected: While no raw Gold SQL or execution result rows were disclosed, "
            "limited semantic case information (natural language intent summaries) was inspected during "
            "governance classification and published in reports/security/enterprise_validation_certification.md. "
            "This semantic exposure is now formally recorded in the case provenance ledger."
        ),
        "remediation_actions": [
            "Updated case_provenance_ledger.jsonl setting governance_reviewer_semantic_exposure = YES for OLIST-0035..0040.",
            "Sanitized public governance report to state only high-level categorizations (3 AMBIGUOUS, 3 UNANSWERABLE) without reproducing protected intent details."
        ]
    }
    with open(GOV_DIR / "protected_exposure_correction.json", "w") as f:
        json.dump(protected_exposure_correction, f, indent=2)

    # 3. Update case_provenance_ledger.jsonl
    ledger_path = GOV_DIR / "case_provenance_ledger.jsonl"
    updated_ledger = []
    if ledger_path.exists():
        with open(ledger_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                cid = record.get("case_id", "")
                if cid in {"OLIST-0035", "OLIST-0036", "OLIST-0037", "OLIST-0038", "OLIST-0039", "OLIST-0040"}:
                    record["governance_reviewer_semantic_exposure"] = "YES"
                    record["Gold_reviewer_role"] = "AI_GOVERNANCE_AGENT"
                    record["Gold_author_reviewer_separated"] = "NO"
                elif record.get("database_id") == "qddd_olist" and record.get("Gold_status") == "INDEPENDENTLY_CERTIFIED":
                    record["Gold_status"] = "GOVERNANCE_REVIEWED"
                    record["Gold_reviewer_role"] = "AI_GOVERNANCE_AGENT"
                    record["Gold_author_reviewer_separated"] = "PARTIAL"
                    record["final_eligibility"] = "GOVERNANCE_REVIEWED_PENDING_INDEPENDENT_ATTESTATION"
                    record["governance_reviewer_semantic_exposure"] = "NO"
                else:
                    record.setdefault("governance_reviewer_semantic_exposure", "NO")
                updated_ledger.append(record)
        with open(ledger_path, "w") as f:
            for record in updated_ledger:
                f.write(json.dumps(record) + "\n")

    # 4. Update eligibility_decision.jsonl
    elig_path = GOV_DIR / "eligibility_decision.jsonl"
    updated_elig = []
    if elig_path.exists():
        with open(elig_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("is_certified"):
                    record["is_certified"] = False
                    record["certification_tier"] = "GOVERNANCE_REVIEWED"
                    record["blocking_reasons"] = ["AWAITING_INDEPENDENT_HUMAN_REVIEWER_SEPARATION_ATTESTATION"]
                updated_elig.append(record)
        with open(elig_path, "w") as f:
            for record in updated_elig:
                f.write(json.dumps(record) + "\n")

    # 5. Role Separation Audit (Update)
    role_separation = {
        "audit_timestamp": now_iso,
        "rule": "Gold Author != Gold Reviewer AND Reviewer not involved in T2S development/prompt/validator tuning",
        "reviewer_type": "AI_GOVERNANCE_AGENT",
        "reviewer_separation_status": "FAILED",
        "separation_metrics": {
            "complete": 0,
            "partial": 34,
            "failed": 20,
            "unknown": 6
        },
        "breakdown": {
            "ecommerce_db": {
                "author": "DATASET_AUTHOR_INTERNAL (T2S development team)",
                "reviewer": "INTERNAL_DEVELOPER_REVIEW",
                "separation_status": "FAILED",
                "reason": "Author-developer overlap; internal T2S development team."
            },
            "qddd_olist_reviewed_33": {
                "author": "GOLD_SQL_AUTHOR_EXTERNAL (chatsql_author)",
                "reviewer": "AI_GOVERNANCE_AGENT",
                "separation_status": "PARTIAL",
                "reason": "Gold author is external, but semantic review was conducted by an AI agent operating in the T2S development environment."
            },
            "qddd_olist_repaired_draft_1": {
                "author": "chatsql_author / governance remediation",
                "reviewer": "AI_GOVERNANCE_AGENT",
                "separation_status": "PARTIAL",
                "reason": "Draft status post-repair requires secondary human confirmation."
            },
            "qddd_olist_ambiguous_unanswerable_6": {
                "author": "NONE",
                "reviewer": "AI_GOVERNANCE_AGENT",
                "separation_status": "UNKNOWN",
                "reason": "Non-SQL specifications; excluded from execution cohort."
            }
        }
    }
    with open(GOV_DIR / "role_separation_audit.json", "w") as f:
        json.dump(role_separation, f, indent=2)

    # 6. Certification Reassessment (Sections 8, 9, 17, 18)
    reassessment = {
        "reassessment_timestamp": now_iso,
        "total_enterprise_candidates": 60,
        "cohort_breakdown": {
            "DRAFT": 1,
            "EXECUTION_VALID": 54,
            "SEMANTICALLY_REVIEWED": 53,
            "GOVERNANCE_REVIEWED": 53,
            "INDEPENDENTLY_CERTIFIED": 0,
            "AMBIGUOUS": 3,
            "UNANSWERABLE": 3,
            "QUARANTINED": 0
        },
        "certified_case_count": 0,
        "governance_reviewed_case_count": 33,
        "determination": "CERTIFICATION_REVIEW_REQUIRED",
        "independent_validation_data_ready": False,
        "production_enforcement_authorized": False,
        "paid_llm_calls": 0,
        "next_action": "OBTAIN_SEPARATE_GOLD_REVIEW_ATTESTATION",
        "rationale": (
            "Per governance rules, cases reviewed by an AI agent with repository development overlap "
            "must be classified as GOVERNANCE_REVIEWED, not INDEPENDENTLY_CERTIFIED. Consequently, "
            "CERTIFIED_CASE_COUNT is 0. All 33 reviewed cases are retained under GOVERNANCE_REVIEWED "
            "awaiting separate independent human reviewer attestation."
        )
    }
    with open(GOV_DIR / "certification_reassessment.json", "w") as f:
        json.dump(reassessment, f, indent=2)

    # 7. Repository Freeze Audit (Section 10)
    freeze_audit = {
        "audit_timestamp": now_iso,
        "claimed_commit_sha": "f8aded617dde36a69d1a4798c75f4365948c1ea7",
        "audit_findings": {
            "validation_manifest_v1_in_commit": False,
            "results_security_in_commit": False,
            "reports_security_in_commit": False,
            "git_dirty_at_previous_report": True
        },
        "repository_freeze_valid": False,
        "remediation_status": "CREATING_COMMITTED_IMMUTABLE_FREEZE",
        "remediation_details": (
            "The previous report referenced git commit f8aded617dde36a69d1a4798c75f4365948c1ea7, "
            "which did not contain the validation manifest, governance results, or security reports. "
            "A clean, dedicated git commit must be created containing all governance-relevant files "
            "to establish an authentic, immutable, commit-anchored validation freeze."
        )
    }
    with open(GOV_DIR / "repository_freeze_audit.json", "w") as f:
        json.dump(freeze_audit, f, indent=2)

    # 8. Certified Cohort Summary (Update)
    reviewed_33_cids = [
        f"OLIST-{i:04d}" for i in range(1, 35) if i != 17
    ]
    cohort_summary = {
        "summary_timestamp": now_iso,
        "enterprise_candidates": 60,
        "gold_missing": 0,
        "gold_invalid": 0,
        "gold_draft": 1,
        "gold_execution_valid": 54,
        "gold_semantically_reviewed": 53,
        "gold_governance_reviewed": 53,
        "gold_independently_certified": 0,
        "ambiguous": 3,
        "unanswerable": 3,
        "certified_case_ids": [],
        "governance_reviewed_case_ids": reviewed_33_cids,
        "certified_case_count": 0,
        "certification_verdict": "CERTIFICATION_REVIEW_REQUIRED",
        "independent_validation_data_ready": False,
        "next_action": "OBTAIN_SEPARATE_GOLD_REVIEW_ATTESTATION"
    }
    with open(GOV_DIR / "certified_cohort_summary.json", "w") as f:
        json.dump(cohort_summary, f, indent=2)

    # 9. Update validation_manifest_v1.json
    olist_schema_hash = "8040c518d6c3dc640936d718e2cfec230a20eb3491a8dfc39c7f7353586a04a6"
    gold_hashes = {cid: sha256_file(CHATSQL_REF_DIR / f"{cid}.sql") for cid in reviewed_33_cids}

    manifest_v1 = {
        "manifest_version": "1.0.0-governance-reviewed",
        "dataset_name": "t2s_independent_validation_enterprise_cohort",
        "freeze_timestamp": now_iso,
        "git_commit": "PENDING_COMMIT",
        "certified_case_count": 0,
        "governance_reviewed_case_count": len(reviewed_33_cids),
        "case_count": 0,
        "database_ids": ["qddd_olist"],
        "certified_case_ids": [],
        "governance_reviewed_case_ids": reviewed_33_cids,
        "database_snapshot_hashes": {
            "qddd_olist": olist_schema_hash
        },
        "gold_hashes": gold_hashes,
        "isolation_attestation": (
            "All 33 cases have zero exposure to production solver. Semantic review was conducted "
            "by AI governance agent. Reviewer separation is classified as GOVERNANCE_REVIEWED pending "
            "independent human reviewer attestation."
        )
    }
    manifest_bytes = json.dumps(manifest_v1, indent=2).encode("utf-8")
    manifest_v1["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    with open(BENCHMARK_DIR / "validation_manifest_v1.json", "w") as f:
        json.dump(manifest_v1, f, indent=2)

    print("Phase 1 governance artifacts generated successfully.")

if __name__ == "__main__":
    main()
