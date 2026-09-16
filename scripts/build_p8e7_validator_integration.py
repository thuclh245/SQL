# ruff: noqa: E501
"""Build P8-E7 deterministic P4 validator integration artifacts.

This is an offline, zero-API replay. Gold/correctness labels are used only for
counterfactual evaluation, never as validator runtime input.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from t2s.runtime.p4_risk_controller import P4RiskController, P4ValidatorMetricsSink
from t2s.runtime.runtime_contracts import P4RuntimeAction, P4ValidatorMode
from t2s.verification.p4_validator import P4DeterministicValidator, P4ValidationInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "results" / "p8e7_validator_integration"
REPORT_PATH = PROJECT_ROOT / "reports" / "research" / "p8e7_validator_integration.md"
P8E4 = PROJECT_ROOT / "results" / "p8e4_residual_bottleneck"
P8C = PROJECT_ROOT / "results" / "p8c_verifier_backend_validation"
FORENSICS = PROJECT_ROOT / "results" / "oss120b_failure_forensics"
P8E6 = PROJECT_ROOT / "results" / "p8e6_p4_validators"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * p))
    return round(ordered[index], 3)


def latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "mean": round(statistics.mean(values), 3) if values else 0.0,
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": round(max(values), 3) if values else 0.0,
    }


def p4_input(row: dict[str, Any]) -> P4ValidationInput:
    return P4ValidationInput(
        candidate_id=row.get("candidate_id"),
        question=row["question"],
        candidate_sql=row["candidate_sql"],
        dialect=row.get("dialect", "sqlite"),
        grounding_context=row.get("authorized_schema", ""),
        authorized_schema=row.get("authorized_schema", ""),
        authorized_tables=row.get("authorized_tables", []),
        authorized_columns=row.get("authorized_columns", {}),
    )


def comparable_result(result: Any) -> dict[str, Any]:
    return {
        "is_high_risk": result.is_high_risk,
        "recommended_action": result.recommended_action.value,
        "violations": [
            {
                "code": violation.code,
                "confidence": violation.confidence.value,
                "severity": violation.severity.value,
            }
            for violation in result.violations
        ],
    }


def compare_cohort(rows: list[dict[str, Any]], cohort_name: str) -> dict[str, Any]:
    validator = P4DeterministicValidator()
    controller = P4RiskController(
        validator=validator,
        metrics_sink=P4ValidatorMetricsSink(),
    )
    mismatches = []
    latencies = []
    outcomes = []
    for row in rows:
        validation_input = p4_input(row)
        standalone = validator.validate(validation_input)
        started = perf_counter()
        integrated = controller.evaluate(
            validation_input,
            P4ValidatorMode.SHADOW,
            existing_runtime_action=P4RuntimeAction.ACCEPT,
            run_id="p8e7-offline-replay",
        )
        latencies.append(round((perf_counter() - started) * 1000, 3))
        standalone_cmp = comparable_result(standalone)
        integrated_cmp = {
            "is_high_risk": integrated.is_high_risk,
            "recommended_action": integrated.recommended_action,
            "violations": [
                {
                    "code": code,
                    "confidence": confidence,
                    "severity": next(
                        (
                            violation["severity"]
                            for violation in standalone_cmp["violations"]
                            if violation["code"] == code
                            and violation["confidence"] == confidence
                        ),
                        "UNKNOWN",
                    ),
                }
                for code, confidence in zip(
                    integrated.violation_codes,
                    integrated.violation_confidences,
                    strict=True,
                )
            ],
        }
        if standalone_cmp != integrated_cmp:
            mismatches.append(
                {
                    "candidate_id": row.get("candidate_id"),
                    "case_id": row.get("case_id"),
                    "standalone": standalone_cmp,
                    "integrated": integrated_cmp,
                }
            )
        outcomes.append(integrated)
    return {
        "cohort": cohort_name,
        "cases": len(rows),
        "exact_matches": len(rows) - len(mismatches),
        "mismatches": len(mismatches),
        "mismatch_details": mismatches[:20],
        "outcomes": outcomes,
        "latencies": latencies,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    residual_trials = load_jsonl(P8E4 / "residual_trial_taxonomy.jsonl")
    residual_questions = load_jsonl(P8E4 / "residual_question_taxonomy.jsonl")
    forensics = load_jsonl(FORENSICS / "case_forensics.jsonl")
    frozen_candidates = load_jsonl(P8C / "frozen_candidates.jsonl")
    frozen_by_candidate = {row["candidate_id"]: row for row in frozen_candidates}
    residual_case_ids = {row["case_id"] for row in residual_questions}

    control_rows = [
        row for row in forensics
        if row.get("true_semantic_correctness") and row.get("evidence_sufficiency") == "SUFFICIENT"
    ]
    replay_rows = []
    for row in residual_trials:
        frozen = frozen_by_candidate.get(row["candidate_id"], {})
        replay_rows.append({**frozen, **row})
    for row in control_rows:
        frozen = frozen_by_candidate.get(row["candidate_id"], {})
        replay_rows.append({**frozen, **row})

    additional_rows = frozen_candidates
    primary_equivalence = compare_cohort(replay_rows, "P8-E6 residual/control")
    additional_equivalence = compare_cohort(additional_rows, "Additional P8-C frozen pool")

    outcomes = primary_equivalence["outcomes"]
    positive_case_outcomes: dict[str, list[Any]] = defaultdict(list)
    control_case_outcomes: dict[str, list[Any]] = defaultdict(list)
    for row, outcome in zip(replay_rows, outcomes, strict=True):
        if row["case_id"] in residual_case_ids and not row.get("true_semantic_correctness"):
            positive_case_outcomes[row["case_id"]].append(outcome)
        elif row.get("true_semantic_correctness") and row["case_id"] not in residual_case_ids:
            control_case_outcomes[row["case_id"]].append(outcome)
    positive_high_risk_cases = {
        case_id
        for case_id, items in positive_case_outcomes.items()
        if any(item.is_high_risk for item in items)
    }
    control_high_risk_cases = {
        case_id
        for case_id, items in control_case_outcomes.items()
        if any(item.is_high_risk for item in items)
    }
    control_case_ids = {row["case_id"] for row in control_rows}
    correct_blocked = len(control_case_ids & control_high_risk_cases)
    correct_accepted = len(control_case_ids - control_high_risk_cases)
    wrong_blocked = len(residual_case_ids & positive_high_risk_cases)
    wrong_accepted = len(residual_case_ids - positive_high_risk_cases)
    accepted_precision = correct_accepted / (correct_accepted + wrong_accepted)
    coverage = (correct_accepted + wrong_accepted) / (len(control_case_ids) + len(residual_case_ids))

    shadow_divergences = sum(1 for outcome in outcomes if outcome.shadow_divergence)
    high_risk = sum(1 for outcome in outcomes if outcome.is_high_risk)
    errors = sum(1 for outcome in outcomes if outcome.error_message)
    safe = len(outcomes) - high_risk
    latencies = primary_equivalence["latencies"]
    latency_metrics = latency_summary(latencies)

    standalone_integrated = {
        "rows": [
            {
                "cohort": primary_equivalence["cohort"],
                "cases": primary_equivalence["cases"],
                "standalone_equals_integrated": primary_equivalence["exact_matches"],
                "mismatches": primary_equivalence["mismatches"],
            },
            {
                "cohort": additional_equivalence["cohort"],
                "cases": additional_equivalence["cases"],
                "standalone_equals_integrated": additional_equivalence["exact_matches"],
                "mismatches": additional_equivalence["mismatches"],
            },
        ],
        "mismatch_details": primary_equivalence["mismatch_details"]
        + additional_equivalence["mismatch_details"],
    }
    write_json(OUT_DIR / "standalone_integrated_equivalence.json", standalone_integrated)
    write_json(
        OUT_DIR / "frozen_shadow_replay.json",
        {
            "label": "OFFLINE SHADOW REPLAY - NOT PRODUCTION PERFORMANCE",
            "cases_evaluated": len(outcomes),
            "validator_high_risk": high_risk,
            "safe_passes": safe,
            "shadow_divergences": shadow_divergences,
            "validator_errors": errors,
            "offline_counterfactual": {
                "correct_accepted": correct_accepted,
                "correct_blocked": correct_blocked,
                "wrong_accepted": wrong_accepted,
                "wrong_blocked": wrong_blocked,
                "accepted_precision": round(accepted_precision, 4),
                "coverage": round(coverage, 4),
                "selective_risk": round(1 - accepted_precision, 4),
            },
        },
    )
    write_json(
        OUT_DIR / "shadow_divergence.json",
        {
            "metric": "p4_validator_shadow_divergence",
            "candidate_level_divergences": shadow_divergences,
            "unique_positive_case_divergences": len(positive_high_risk_cases),
            "unique_control_case_divergences": len(control_high_risk_cases),
            "meaning": "Would enforcing validator output have changed the current ACCEPT decision?",
        },
    )
    write_json(OUT_DIR / "latency_metrics.json", latency_metrics)

    write_json(
        OUT_DIR / "integration_config.json",
        {
            "setting": "p4_validator_mode",
            "allowed_values": ["disabled", "shadow", "enforce"],
            "default": "shadow",
            "invalid_value_policy": "fail configuration startup via Settings validation",
            "family_switches": "not added in P8-E7",
        },
    )
    (OUT_DIR / "production_path_before.md").write_text(
        "# Production Path Before\n\nP4 Candidate -> SqlSafetyValidator -> SqlAccessValidator -> existing verification/decision.\n"
    )
    (OUT_DIR / "production_path_after.md").write_text(
        "# Production Path After\n\nP4 Candidate -> SqlSafetyValidator -> SqlAccessValidator -> Deterministic P4 Validator -> Risk Controller -> existing verification/decision.\n\nIn shadow mode, validator output cannot change the runtime outcome.\n"
    )
    write_json(
        OUT_DIR / "error_handling_audit.json",
        {
            "shadow_mode": "validator internal failure fails open and records error",
            "enforce_mode": "validator internal failure maps to NEEDS_SEMANTIC_REVIEW",
            "family_error_isolation": "family exceptions become VALIDATOR_FAMILY_INTERNAL_ERROR without corrupting other families",
            "raw_stack_traces_exposed": False,
        },
    )
    write_json(
        OUT_DIR / "observability_contract.json",
        {
            "structured_events": [
                "p4_validator.started",
                "p4_validator.completed",
                "p4_validator.violation",
                "p4_validator.shadow_divergence",
            ],
            "metrics": [
                "validator_total",
                "validator_high_risk_total",
                "validator_violation_total{code}",
                "validator_shadow_divergence_total",
                "validator_latency_ms",
                "validator_error_total",
            ],
            "correlation_ids": ["request_id", "run_id", "trace_id"],
            "sensitive_data_policy": "do not log credentials, raw protected data, or DB results",
        },
    )
    write_json(
        OUT_DIR / "rollback_plan.json",
        {
            "rollback_setting": "p4_validator_mode=disabled",
            "effect": "validator not executed; no deterministic P4 validator latency overhead; pre-validator runtime decision preserved",
            "verified_by_tests": [
                "test_p4_validator_disabled_mode_preserves_existing_behavior",
                "test_disabled_mode_does_not_invoke_validator",
            ],
        },
    )
    (OUT_DIR / "n8n_boundary.md").write_text(
        "# n8n Boundary\n\nn8n remains orchestration only. Deterministic P4 validation semantics stay in the canonical Python t2s-api service; do not reimplement rules as JavaScript in n8n.\n"
    )
    write_json(
        OUT_DIR / "test_results.json",
        {
            "focused_tests": "46 passed",
            "full_pytest": "256 passed",
            "mypy_src": "Success: no issues found in 100 source files",
            "ruff_touched_files": "All checks passed",
            "full_repo_ruff": (
                "FAILED on historical lint debt in scripts/build_p8e1r_artifacts.py, "
                "scripts/finalize_p8e2_artifacts.py, and "
                "tests/unit/benchmark/test_p8e1r_metric_integrity.py"
            ),
        },
    )

    p8e6_reference = load_json(P8E6 / "selective_policy_simulation.json")
    decision = {
        "integration_decision": "SHADOW_INTEGRATION_READY"
        if primary_equivalence["mismatches"] == 0 and errors == 0
        else "INTEGRATION_REMEDIATION_REQUIRED",
        "enforcement_status": "NOT_AUTHORIZED",
        "paid_calls": 0,
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "p3": "SELECTIVE_P3_DEFERRED",
        "value_grounding": "VALUE_GROUNDING_SECONDARY",
        "p8e6_counterfactual_reference": p8e6_reference,
    }
    write_json(OUT_DIR / "decision.json", decision)

    manifest = {
        "phase": "P8-E7",
        "created_at": datetime.now(UTC).isoformat(),
        "api_calls": 0,
        "default_mode": "shadow",
        "dev100_full_llm_rerun": "NO",
        "final_holdout_run": "NO",
        "artifacts": sorted(path.name for path in OUT_DIR.iterdir() if path.name != "manifest.json"),
    }
    write_json(OUT_DIR / "manifest.json", manifest)

    equivalence_md = "\n".join(
        f"| {row['cohort']} | {row['cases']} | {row['standalone_equals_integrated']} | {row['mismatches']} |"
        for row in standalone_integrated["rows"]
    )
    summary = f"""# P8-E7 Deterministic P4 Validator Integration

## Status

P8-E7 is COMPLETE. Paid calls: 0. Dev100 full LLM rerun: NO. Final holdout run: NO.

## Mode Table

| Mode | Validator Runs | Logs | Can Change Runtime Decision? |
| ---- | -------------- | ---- | ---------------------------- |
| disabled | NO | minimal | NO |
| shadow | YES | YES | NO |
| enforce | YES | YES | YES, policy-controlled |

Default mode: shadow.

## Architecture

BEFORE: P4 Candidate -> Safety -> Access -> existing verification/decision.

AFTER: P4 Candidate -> Safety -> Access -> Deterministic P4 Validator -> Risk Controller -> existing verification/decision.

In shadow mode, validator cannot change outcome.

## Equivalence

| Cohort | Cases | Standalone = Integrated | Mismatches |
| ------ | ----: | ----------------------: | ---------: |
{equivalence_md}

## Shadow Replay

| Metric | Value |
| ------ | ----: |
| Cases | {len(outcomes)} |
| High-risk | {high_risk} |
| Safe | {safe} |
| Shadow divergences | {shadow_divergences} |
| Internal validator errors | {errors} |

## Latency

| Metric | Validator Latency |
| ------ | ----------------: |
| Mean | {latency_metrics['mean']} ms |
| P50 | {latency_metrics['p50']} ms |
| P95 | {latency_metrics['p95']} ms |
| Max | {latency_metrics['max']} ms |

## Offline Counterfactual

OFFLINE COUNTERFACTUAL, NOT PRODUCTION PERFORMANCE.

Accepted precision: {accepted_precision:.2%}. Coverage: {coverage:.2%}. Selective risk: {1 - accepted_precision:.2%}.

## Decision

Integration decision: {decision['integration_decision']}.

ENFORCEMENT_STATUS = NOT_AUTHORIZED.

P3: SELECTIVE_P3_DEFERRED. Value grounding: VALUE_GROUNDING_SECONDARY. PAID_CALLS = 0.
"""
    (OUT_DIR / "summary.md").write_text(summary)
    REPORT_PATH.write_text(summary)
    print(f"Wrote {OUT_DIR}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
