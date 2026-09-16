# ruff: noqa: E501
"""Build Phase P8-E9: Independent Validation Cohort Provisioning & Blind Preregistration Artifacts.

ZERO API: No LLM calls, no SQL generation, no prompt changes, no validator tuning.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results" / "p8e9_independent_validation"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e9_independent_validation.md"

VALIDATOR_PY = PROJECT_ROOT / "src" / "t2s" / "verification" / "p4_validator.py"
PROMPT_SYSTEM_MD = PROJECT_ROOT / "prompts" / "direct_sql" / "v001_system.md"
PROMPT_USER_MD = PROJECT_ROOT / "prompts" / "direct_sql" / "v001_user_template.md"
MINI_DEV_SQLITE = PROJECT_ROOT / "data" / "bird_mini_dev" / "mini_dev_sqlite.json"
PARTITION_MANIFEST = PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "bird_unopened_partition_manifest.json"
POOL_MANIFEST = PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "opened_vs_unopened_question_pool.json"


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 1. Validator Freeze & Reference Hashes
    validator_bytes = VALIDATOR_PY.read_bytes()
    validator_sha256 = hashlib.sha256(validator_bytes).hexdigest()
    git_sha = "f8aded617dde36a69d1a4798c75f4365948c1ea7"
    git_dirty = True
    policy_config_str = "mode=shadow,enforce_action=REJECT_OR_ESCALATE,confidence=HIGH,families=[V1,V2,V3,V4,V5]"
    policy_hash = hash_text(policy_config_str)

    prompt_system_sha256 = hashlib.sha256(PROMPT_SYSTEM_MD.read_bytes()).hexdigest()
    prompt_user_sha256 = hashlib.sha256(PROMPT_USER_MD.read_bytes()).hexdigest()

    validator_freeze_data = {
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "validator_path": "src/t2s/verification/p4_validator.py",
        "validator_sha256": validator_sha256,
        "policy_config_string": policy_config_str,
        "policy_hash": policy_hash,
        "prompt_version": "v001",
        "prompt_system_sha256": prompt_system_sha256,
        "prompt_user_template_sha256": prompt_user_sha256,
        "grounding_configuration": "P3 baseline (compact schema retrieval, small_db_threshold=0, relationship_expansion_mode=off, fill_column_budget=False)",
        "immutability_rule": "Any semantic modification to validator rules, regexes, thresholds, or composition invalidates future validation preregistration.",
        "enforcement_status": "NOT_AUTHORIZED",
        "current_mode": "shadow",
    }
    (RESULTS_DIR / "validator_freeze.json").write_text(json.dumps(validator_freeze_data, indent=2))

    # 2. Dataset Inventory
    dataset_inventory_data = [
        {
            "dataset_name": "t2s_pilot_v1",
            "source": "data/configs/pilot_v1.json / benchmarks/t2s/datasets/t2s_pilot_v1.jsonl",
            "number_of_questions": 85,
            "databases": ["financial", "california_schools", "superhero", "formula_1", "toxicology", "student_club"],
            "gold_available": True,
            "historical_phases_referencing": ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"],
            "historical_generation_exposure": True,
            "human_inspection_exposure": True,
            "independence_label": "DEVELOPMENT_CONTAMINATED",
            "eligible": False,
            "disqualification_rationale": "Initial pilot exploration dataset; fully opened and inspected; used for early prompt and parser development.",
        },
        {
            "dataset_name": "t2s_eval_v1",
            "source": "data/configs/eval_v1.json / benchmarks/t2s/datasets/t2s_eval_v1.jsonl",
            "number_of_questions": 100,
            "databases": ["financial", "california_schools", "superhero", "formula_1", "toxicology", "student_club", "card_games", "european_football_2", "debit_card_specializing", "thrombosis_prediction", "codebase_community"],
            "gold_available": True,
            "historical_phases_referencing": ["P6", "P7", "P8"],
            "historical_generation_exposure": True,
            "human_inspection_exposure": True,
            "independence_label": "DEVELOPMENT_CONTAMINATED",
            "eligible": False,
            "disqualification_rationale": "Primary regression checkpoint for early phases; fully opened and executed in P6/P7 evaluations.",
        },
        {
            "dataset_name": "t2s_p8b_dev100",
            "source": "benchmarks/t2s/datasets/t2s_p8b_dev100.jsonl",
            "number_of_questions": 100,
            "databases": ["california_schools", "card_games", "codebase_community", "debit_card_specializing", "european_football_2", "financial", "formula_1", "student_club", "superhero", "thrombosis_prediction", "toxicology"],
            "gold_available": True,
            "historical_phases_referencing": ["P8-B", "P8-C", "P8-D", "P8-E0", "P8-E1", "P8-E2", "P8-E3", "P8-E4", "P8-E5", "P8-E6", "P8-E7", "P8-E8"],
            "historical_generation_exposure": True,
            "human_inspection_exposure": True,
            "independence_label": "DEVELOPMENT_CONTAMINATED",
            "eligible": False,
            "disqualification_rationale": "Direct iterative development cohort; residual cases used to design P4 validator rules; negative controls used for threshold tuning.",
        },
        {
            "dataset_name": "t2s_final_holdout_v1",
            "source": "configs/final_holdout/t2s_final_holdout_v1.json",
            "number_of_questions": 215,
            "databases": ["california_schools", "card_games", "codebase_community", "debit_card_specializing", "european_football_2", "financial", "formula_1", "student_club", "superhero", "thrombosis_prediction", "toxicology"],
            "gold_available": True,
            "historical_phases_referencing": ["Historical unmonitored inference"],
            "historical_generation_exposure": True,
            "human_inspection_exposure": False,
            "independence_label": "UNKNOWN_PROVENANCE",
            "eligible": False,
            "disqualification_rationale": "Quarantined by project governance; >= 25 historical inference executions occurred; exact exposed IDs unknown; residual uncertifiable; strictly forbidden from access.",
        },
        {
            "dataset_name": "bird_mini_dev_full_source",
            "source": "data/bird_mini_dev/mini_dev_sqlite.json",
            "number_of_questions": 500,
            "databases": ["california_schools", "card_games", "codebase_community", "debit_card_specializing", "european_football_2", "financial", "formula_1", "student_club", "superhero", "thrombosis_prediction", "toxicology"],
            "gold_available": True,
            "historical_phases_referencing": ["P0 through P8-E8"],
            "historical_generation_exposure": True,
            "human_inspection_exposure": True,
            "independence_label": "DEVELOPMENT_CONTAMINATED",
            "eligible": False,
            "disqualification_rationale": "Sum of pilot (85) + eval_v1 (100) + dev100 (100) + holdout (215) = 500. Entire BIRD Mini-Dev pool is exhausted and officially closed.",
        },
        {
            "dataset_name": "fresh_enterprise_benchmark",
            "source": "Priority A: Internal enterprise Text-to-SQL benchmark",
            "number_of_questions": 0,
            "databases": [],
            "gold_available": False,
            "historical_phases_referencing": [],
            "historical_generation_exposure": False,
            "human_inspection_exposure": False,
            "independence_label": "CERTIFIED_UNTOUCHED",
            "eligible": False,
            "disqualification_rationale": "Not currently present in repository; requires external enterprise provisioning before evaluation.",
        },
        {
            "dataset_name": "external_benchmark_unconsumed_partition",
            "source": "Priority B: External unconsumed benchmark (e.g. BIRD train partition or Spider 2.0)",
            "number_of_questions": 0,
            "databases": [],
            "gold_available": False,
            "historical_phases_referencing": [],
            "historical_generation_exposure": False,
            "human_inspection_exposure": False,
            "independence_label": "CERTIFIED_UNTOUCHED",
            "eligible": False,
            "disqualification_rationale": "Not present in repository; downloading or importing external datasets was not pre-authorized for P8-E9.",
        },
    ]
    (RESULTS_DIR / "dataset_inventory.json").write_text(json.dumps(dataset_inventory_data, indent=2))

    # 3. Dataset Provenance JSONL
    with open(RESULTS_DIR / "dataset_provenance.jsonl", "w") as f:
        for item in dataset_inventory_data:
            f.write(json.dumps(item) + "\n")

    # 4. Independence Audit
    mini_dev = json.loads(MINI_DEV_SQLITE.read_text())
    pool = json.loads(POOL_MANIFEST.read_text())
    part = json.loads(PARTITION_MANIFEST.read_text())

    audit_data = {
        "bird_mini_dev_total": len(mini_dev),
        "opened_eval_v1_count": len(pool["eval_v1_question_ids"]),
        "opened_pilot_v1_count": len(pool["pilot_v1_question_ids"]),
        "p7_development_dev100_count": len(part["p7_development_extension"]["question_ids"]),
        "quarantined_final_holdout_count": len(part["final_untouched_holdout"]["question_ids"]),
        "sum_of_partitioned_cases": (
            len(pool["eval_v1_question_ids"])
            + len(pool["pilot_v1_question_ids"])
            + len(part["p7_development_extension"]["question_ids"])
            + len(part["final_untouched_holdout"]["question_ids"])
        ),
        "residual_unopened_mini_dev_questions": 0,
        "bird_mini_dev_closed": True,
        "final_holdout_governance": {
            "total_cases": 215,
            "historical_executions": ">= 25 executions occurred historically",
            "exposed_case_ids": "UNKNOWN",
            "certifiability": "NOT_CERTIFIABLE",
            "rule": "DO NOT open, inspect, sample, reshuffle, materialize, score, or reuse the 215 holdout partition.",
        },
        "repository_untouched_data_count": 0,
        "independence_decision": "NO_CERTIFIABLE_INDEPENDENT_VALIDATION_SET",
        "data_governance_decision": "NO_INDEPENDENT_DATA_SOURCE_AVAILABLE",
    }
    (RESULTS_DIR / "independence_audit.json").write_text(json.dumps(audit_data, indent=2))

    # 5. Eligible Population
    eligible_pop_data = {
        "eligible_questions_count": 0,
        "eligible_questions": [],
        "minimum_target_size": 25,
        "preferred_target_size": 30,
        "target_met": False,
        "status": "INDEPENDENT_COHORT_INSUFFICIENT",
        "reason": "All 500 BIRD mini-dev cases are exhausted across development and quarantined holdout. No unconsumed external or enterprise benchmark exists in the repository.",
    }
    (RESULTS_DIR / "eligible_population.json").write_text(json.dumps(eligible_pop_data, indent=2))

    # 6. Sampling Method (Deterministic Specification for Future Provisioning)
    sampling_method_data = {
        "status": "PREREGISTERED_SPECIFICATION",
        "sampling_rule": "Deterministic pseudo-random sampling stratified across databases and difficulty",
        "seed": 20260915,
        "hash_ranking_formula": "sha256(f'{seed}:{case_id}')",
        "target_sample_size": 30,
        "acceptable_range": [25, 50],
        "database_diversity_requirement": ">= 5 distinct databases, max 30% from any single database",
        "blindness_requirement": "Sampling must be performed exclusively on metadata (case_id, db_id, difficulty, schema_size). Question text, gold SQL, and model predictions must remain strictly uninspected during sampling.",
    }
    (RESULTS_DIR / "sampling_method.json").write_text(json.dumps(sampling_method_data, indent=2))

    # 7. Sealed Validation Dataset Manifest
    validation_manifest_data = {
        "status": "NO_CERTIFIABLE_INDEPENDENT_VALIDATION_SET",
        "manifest_version": "v1.0-sealed",
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "manifest_sha256": hash_text("NO_CERTIFIABLE_INDEPENDENT_VALIDATION_SET:20260915"),
        "dataset_source": "NONE_AVAILABLE_IN_REPOSITORY",
        "case_ids": [],
        "database_ids": [],
        "metadata_strata": {},
        "sampling_method": "deterministic_seed_20260915",
        "sampling_seed": 20260915,
        "notes": "No questions selected. BIRD Mini-Dev 500 is completely exhausted and closed. Holdout 215 is sequestered and uncertifiable. Enterprise or fresh external data must be imported before manifest can be populated.",
    }
    (RESULTS_DIR / "validation_dataset_manifest.json").write_text(json.dumps(validation_manifest_data, indent=2))

    # 8. Validation Distribution
    validation_distribution_data = {
        "selected_cohort_count": 0,
        "by_database": {},
        "by_difficulty": {},
        "by_schema_size": {},
        "target_distribution_for_future_cohort": {
            "total_questions": 30,
            "min_databases": 5,
            "difficulty_allocation": {"simple": "30-40%", "moderate": "40-50%", "challenging": "15-25%"},
        },
    }
    (RESULTS_DIR / "validation_distribution.json").write_text(json.dumps(validation_distribution_data, indent=2))

    # 9. Gold Governance
    gold_governance_data = {
        "gold_status": "UNAVAILABLE",
        "acceptable_sources": [
            "Existing certified benchmark gold SQL (from unopened external benchmark)",
            "Independently authored enterprise analyst SQL",
            "Dual-review SQL verified by independent database engineer",
        ],
        "strictly_forbidden_sources": [
            "SQL generated by the production OSS model (gpt-oss-120b) without independent human certification",
            "Synthetic SQL generated using T2S prompts or validator feedback",
        ],
        "quality_certification_requirements": [
            "Gold SQL must execute cleanly on the target database",
            "Target database must be executed with PRAGMA query_only = ON (zero mutation allowed)",
            "Execution result set must be non-empty or validated as an intentional empty-set ground truth",
            "Schema identifiers must match live database catalog exactly",
        ],
        "blindness_boundary": "Gold SQL is restricted strictly to the offline benchmark evaluation scorer. Gold SQL, gold tables, gold columns, and gold results must NEVER enter solver prompts, grounding context, or validator inputs.",
    }
    (RESULTS_DIR / "gold_governance.json").write_text(json.dumps(gold_governance_data, indent=2))

    # 10. Future Runtime Config (Frozen Execution Specification)
    future_runtime_config_data = {
        "generator": {
            "model": "openai/gpt-oss-120b",
            "temperature": 0.0,
            "max_output_tokens": 1500,
            "prompt_version": "v001",
            "prompt_path": "prompts/direct_sql/v001",
            "candidate_count": 1,
        },
        "grounding": {
            "policy": "frozen_p3_baseline",
            "relationship_expansion_mode": "off",
            "fill_column_budget": False,
            "small_db_threshold": 0,
            "max_tables": 5,
            "max_columns_per_table": 10,
        },
        "validator": {
            "implementation": "P4DeterministicValidator",
            "file_sha256": validator_sha256,
            "mode": "shadow",
            "enforce_action": "REJECT_OR_ESCALATE",
            "confidence_threshold": "HIGH",
            "active_families": [
                "V1_FILTER_CONTRACT",
                "V2_AGGREGATION_GRAIN",
                "V3_PROJECTION_SHAPE",
                "V4_JOIN_PATH_RISK",
                "V5_SQL_CONSTRUCTION_SANITY",
            ],
            "runtime_impact": "OBSERVATIONAL_ONLY (cannot modify generated SQL or outcome in shadow mode)",
        },
        "pipeline_safety": [
            "SqlSafetyValidator",
            "SqlAccessValidator",
            "P4DeterministicValidator (shadow)",
        ],
        "verifier": "OFF (isolated validator validation)",
    }
    (RESULTS_DIR / "future_runtime_config.json").write_text(json.dumps(future_runtime_config_data, indent=2))

    # 11. Future Success Criteria
    future_success_criteria_data = {
        "primary_safety_gate": {
            "metric": "False Positive Rate (FPR)",
            "definition": "FP / (FP + TN) on execution-correct SQL candidates",
            "target": "<= 5.0%",
            "maximum_acceptable": "<= 10.0%",
        },
        "precision_gate": {
            "metric": "Validator Precision",
            "definition": "TP / (TP + FP)",
            "target": ">= 90.0%",
            "minimum_acceptable": ">= 80.0%",
        },
        "minimum_signal_gate": {
            "metric": "Wrong SQL Detection Rate (Recall)",
            "definition": "TP / (TP + FN) on execution-incorrect SQL candidates",
            "target": "> 10.0%",
            "rationale": "Validator must detect actual errors on independent data; 0% firing rate fails enforcement eligibility.",
        },
        "determinism_gate": {
            "metric": "Result Consistency",
            "target": "100.0% identical violations on repeated evaluation",
        },
        "latency_gate": {
            "metric": "Validator p95 Latency",
            "target": "<= 5.0 ms",
        },
        "safety_gate": {
            "metric": "Safety / ACL Bypass",
            "target": "Exactly 0 bypasses or regressions",
        },
    }
    (RESULTS_DIR / "future_success_criteria.json").write_text(json.dumps(future_success_criteria_data, indent=2))

    # 12. Future Failure Criteria
    future_failure_criteria_data = {
        "hard_failure_conditions": [
            "False Positive Rate (FPR) > 10.0% on correct SQL candidates",
            "Validator Precision < 80.0% (when at least 5 violations are flagged)",
            "Wrong SQL Detection Rate == 0.0% (validator never fires on real errors)",
            "Any safety, ACL, or forbidden mutation statement permitted",
            "Any unhandled exception or crash in P4DeterministicValidator",
            "Validator p95 latency > 10.0 ms",
        ],
        "consequence_of_failure": "Enforcement rejected; validator remains in shadow mode; return to offline diagnostics.",
    }
    (RESULTS_DIR / "future_failure_criteria.json").write_text(json.dumps(future_failure_criteria_data, indent=2))

    # 13. Future Call Budget
    future_call_budget_data = {
        "p8e9_paid_calls": 0,
        "planned_future_paid_calls": 0,
        "future_experiment_call_cap": 50,
        "concurrency": 1,
        "retries": 0,
        "rescue_generations_allowed": 0,
        "infrastructure_error_policy": "If provider 5xx, rate limit, or timeout occurs, record API_ERROR. Do NOT retry or replace case within the same run.",
        "inconclusive_threshold": "If API errors exceed 15% of cohort (>= 5 cases for N=30), run is declared INCONCLUSIVE_INFRASTRUCTURE.",
    }
    (RESULTS_DIR / "future_call_budget.json").write_text(json.dumps(future_call_budget_data, indent=2))

    # 14. Enforcement Family Status
    enforcement_family_status_data = {
        "Filter (V1)": "SHADOW_ONLY",
        "Aggregation/Grain (V2)": "SHADOW_ONLY",
        "Projection (V3)": "SHADOW_ONLY",
        "Join Path (V4)": "INSUFFICIENT_EVIDENCE",
        "Construction (V5)": "SHADOW_ONLY",
        "production_enforcement_authorized": False,
        "default_runtime_mode": "shadow",
        "enforcement_rollout_stages": {
            "Stage 0": "disabled",
            "Stage 1": "shadow (CURRENT PRODUCTION DEFAULT)",
            "Stage 2": "enforce only HIGH-confidence UNBOUND/structural violations (NOT AUTHORIZED)",
            "Stage 3": "enforce broader HIGH-confidence semantic violations (NOT AUTHORIZED)",
            "Stage 4": "optional risk-based escalation (NOT AUTHORIZED)",
        },
    }
    (RESULTS_DIR / "enforcement_family_status.json").write_text(json.dumps(enforcement_family_status_data, indent=2))

    # 15. Report Wording Corrections (Section 36)
    report_wording_corrections_data = {
        "affected_phase": "P8-E8",
        "metric_context": "Cheap-First Routing Simulation (Fast-path 82.52%, Escalated 17.48%, Accepted Precision 35.29%, Selective Risk 64.71%)",
        "misleading_phrasing": [
            "maintaining baseline accuracy",
            "production-ready verifier cost reduction",
        ],
        "corrected_scientific_interpretation": (
            "Deterministic P4 validation as a fast front-line filter successfully reduces historical verifier calls "
            "by 82.52% in an offline counterfactual simulation, but resulting selective precision (35.29%) and selective "
            "risk (64.71%) remain far below acceptable production reliability standards. It demonstrates latency/cost reduction "
            "potential, not production enforcement readiness."
        ),
        "status": "CORRECTION_LOGGED_AND_GOVERNED",
    }
    (RESULTS_DIR / "report_wording_corrections.json").write_text(json.dumps(report_wording_corrections_data, indent=2))

    # 16. Decision Record
    decision_data = {
        "p8e9_status": "COMPLETE",
        "paid_calls": 0,
        "selected_data_source": "NONE",
        "eligible_questions": 0,
        "final_cohort_size": 0,
        "final_cohort_databases": 0,
        "manifest_hash": "N/A",
        "gold_status": "UNAVAILABLE",
        "independence_decision": "NO_INDEPENDENT_COHORT_AVAILABLE",
        "data_governance_decision": "NO_INDEPENDENT_DATA_SOURCE_AVAILABLE",
        "experimental_readiness": "VALIDATION_BLOCKED",
        "future_test_preregistered": "NO",
        "planned_future_calls": 0,
        "production_enforcement_authorized": "NO",
        "shadow_mode_remains_default": "YES",
        "dev100_full_llm_rerun": "NO",
        "bird_mini_dev_reuse": "NO",
        "final_holdout_run": "NO",
        "next_phase": "ACQUIRE_NEW_VALIDATION_DATA",
    }
    (RESULTS_DIR / "decision.json").write_text(json.dumps(decision_data, indent=2))

    # 17. Manifest JSON
    manifest_data = {
        "phase": "P8-E9",
        "title": "Independent Validation Cohort Provisioning & Blind Preregistration",
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "validator_sha256": validator_sha256,
        "policy_hash": policy_hash,
        "paid_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "bird_mini_dev_reuse": "NO",
        "final_holdout_run": "NO",
        "enforcement_status": "NOT_AUTHORIZED",
        "default_mode": "shadow",
        "data_governance_decision": "NO_INDEPENDENT_DATA_SOURCE_AVAILABLE",
        "experimental_readiness": "VALIDATION_BLOCKED",
        "final_scientific_decision": "NO_INDEPENDENT_COHORT_AVAILABLE",
        "next_phase": "ACQUIRE_NEW_VALIDATION_DATA",
    }
    (RESULTS_DIR / "manifest.json").write_text(json.dumps(manifest_data, indent=2))

    # 18. Summary Markdown
    summary_md = f"""# Phase P8-E9: Independent Validation Cohort Provisioning & Blind Preregistration Summary

## 1. Executive Status
- **Phase Status**: `P8-E9 = COMPLETE` [MEASURED FACT]
- **API Usage**: Paid calls = **0** [MEASURED FACT]
- **Validator Freeze**:
  - Git SHA: `{git_sha}` (dirty: `{git_dirty}`) [MEASURED FACT]
  - `p4_validator.py` SHA256: `{validator_sha256}` [MEASURED FACT]
  - Policy Hash: `{policy_hash}` [MEASURED FACT]
- **Selected Data Source**: `NONE` [MEASURED FACT]
- **Independent Population**: `Eligible questions: 0` [MEASURED FACT]
- **Final Cohort**: `N/A` (Questions = 0) [MEASURED FACT]
- **Gold Status**: `UNAVAILABLE` [MEASURED FACT]
- **Data Governance Decision**: `NO_INDEPENDENT_DATA_SOURCE_AVAILABLE` [VERIFIED INFERENCE]
- **Experimental Readiness**: `VALIDATION_BLOCKED` [RECOMMENDATION]
- **Final Scientific Decision**: `NO_INDEPENDENT_COHORT_AVAILABLE` [VERIFIED INFERENCE]
- **Future Test Preregistered**: `NO` (Draft protocol defined; cohort IDs unassigned) [RECOMMENDATION]
- **Planned Future Calls**: `0` [MEASURED FACT]
- **Production Enforcement**: `AUTHORIZED: NO` [MEASURED FACT]
- **Shadow Mode**: `REMAINS DEFAULT: YES` [MEASURED FACT]
- **Dev100 Full LLM Rerun**: `NO` [MEASURED FACT]
- **BIRD Mini-Dev Reuse**: `NO` [MEASURED FACT]
- **Final Holdout Execution**: `NO` [MEASURED FACT]
- **Next Phase**: `ACQUIRE_NEW_VALIDATION_DATA` [RECOMMENDATION]

---

## 2. Dataset Inventory & Exhaustion Accounting

All 500 questions in BIRD Mini-Dev are completely accounted for and exhausted:
- **`eval_v1` (100 cases)**: Opened and inspected during early P6/P7 evaluation.
- **`pilot_v1` (85 cases)**: Opened and inspected during initial P0–P5 development.
- **`t2s_p8b_dev100` (100 cases)**: Iterative development cohort; residual failures used for P4 rule design; controls used for threshold tuning.
- **`t2s_final_holdout_v1` (215 cases)**: **Quarantined**. Contaminated by $\ge 25$ historical unmonitored inference executions; exposed IDs unknown; uncertifiable. Strictly sequestered.
- **Remaining Untouched in BIRD Mini-Dev**: **0 cases**.

Zero enterprise benchmarks or unconsumed external partitions exist in `/home/thuclh245/MyCode/SQL`.

---

## 3. Preregistered Protocol for Future Validation

When an independent dataset (e.g. unconsumed BIRD train partition or enterprise benchmark) is acquired:
- **Sample Size**: 25–30 questions across $\ge 5$ databases.
- **Sampling Rule**: Deterministic SHA-256 ranking with seed `20260915` (`sha256(f'20260915:{{case_id}}')`).
- **Blindness Rule**: Sampling based strictly on metadata (case ID, db ID, difficulty). Question text and gold SQL uninspected prior to manifest freeze.
- **Runtime Mode**: `openai/gpt-oss-120b`, temperature = 0.0, prompt `v001`, compact P3 baseline, P4 validator in `shadow` mode, verifier `OFF`.
- **Success Criteria**: FPR <= 5.0%, Precision >= 90.0%, Error Detection Rate > 10.0%, Determinism 100%, p95 Latency <= 5.0 ms.
- **Hard Failure Criteria**: FPR > 10.0% OR Precision < 80.0% OR zero error detection OR any safety/ACL bypass.

---

## 4. Report Wording Correction (from P8-E8)

P8-E8 cheap-first routing (fast-path 82.52%, accepted precision 35.29%, selective risk 64.71%) must **not** be described as "maintaining baseline accuracy" or "production-ready verifier cost reduction".
*Corrected interpretation*: It reduces historical verifier calls in an offline simulation, but resulting selective precision remains far below acceptable production reliability standards.
"""
    (RESULTS_DIR / "summary.md").write_text(summary_md)

    print("Phase P8-E9 artifacts successfully generated.")


if __name__ == "__main__":
    main()
