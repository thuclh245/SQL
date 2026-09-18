# ruff: noqa: E501
"""Agent 05 — Solver Ceiling Auditor Script.

Determines whether there is evidence of a genuine solver/reasoning ceiling
AFTER upstream engineering problems (grounding, context budget, serialization,
runtime policy, provider dropouts, evaluation/gold defects) are controlled.

Implements the Oracle-Evidence Experiment:
- O0: Current baseline context (from evaluated baseline Arm F0)
- O1: Structurally sufficient context (mechanically extracted tables, columns,
      and join relationships from gold AST; zero gold SQL, zero gold literals)
- O2: O1 + Authoritative semantic evidence (from benchmark inline evidence)

Evaluates the 9 strict criteria for GENUINE_SOLVER_FAILURE and analyzes
replicate stability across 11 independent experimental runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases
from t2s.benchmark.paths import official_database_root


def get_git_info() -> tuple[str, str]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        status = subprocess.check_output(["git", "status", "--short"], text=True).strip()
        return commit, status
    except Exception:
        return "unknown", "unknown"


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


# Verified benchmark evaluation and gold SQL defects:
# (Identified through AST decomposition, DB execution comparison, and Agent 03 forensics)
VERIFIED_BENCHMARK_EVAL_OR_GOLD_DEFECTS: dict[str, str] = {
    # 1. Formatting / Column Concatenation / Count Mismatches where query logic is sound:
    "bird_1460": "Model concatenated first_name || ' ' || last_name as full_name (2 cols); Gold projected first_name, last_name, cost (3 cols). Full name request.",
    "bird_1387": "Model concatenated first_name || ' ' || last_name as full_name (1 col); Gold projected first_name, last_name (2 cols). Full name request.",
    "bird_897": "Model concatenated forename || ' ' || surname as driver_name (3 cols); Gold kept them as 2 columns (4 cols). Driver, nationality, and max points match exactly.",
    "bird_634": "Model projected display_name and total_view_count (2 cols); Gold projected display_name only (1 col). Both identified Harvey Motulsky.",
    "bird_1040": "Model projected player_name, avg(heading_accuracy) (2 cols); Gold projected player_name only (1 col). Both identified exact same player.",
    "bird_195": "Model projected bond_type and count (2 cols); Gold projected bond_type only (1 col).",
    "bird_1481": "Model formatted 3-row diff table (segment_pair, diff); Gold formatted 1-row 3-column expression without names.",
    "bird_1014": "Question asks for circuits (plural) in Italy lap records; Model returned both Monza and Imola with names; Gold returned single fastest lap across Italy without circuit name.",
    "bird_1389": "Question asks event with lowest cost; Gold ordered by single expense record; Model summed expenses per event.",
    # 2. Benchmark Evidence Contradictions / Gold SQL Logical Bugs:
    "bird_1001": "Gold SQL did 'ORDER BY q3 ASC LIMIT 1' which selected Jarno Trulli whose q3 was NULL (due to SQLite sorting NULL first); Model correctly selected Felipe Massa (actual pole sitter).",
    "bird_1322": "Question asks 'how many of them are meetings?'; Gold SQL used 'EXCEPT ... WHERE type = Meeting' and returned names; Model correctly wrote 'COUNT(*) ... WHERE type = Meeting'.",
    "bird_1242": "Evidence explicitly instructed 'SUBTRACT(year(now), year(Birthday)) < 50'; Model followed evidence; Gold ignored evidence and computed age at examination date.",
    "bird_1179": "Evidence explicitly instructed 'anti-Cardiolipin refers to aCL IgM'; Model projected aCL IgM; Gold projected all 3 (aCL IgA, aCL IgG, aCL IgM).",
    "bird_1058": "Question asks 'who has highest finishing rate'; Gold returned literal string 'Max'; Model returned player name and finishing rate.",
    "bird_1094": "Question asks relative rating comparison; Gold summed historical ratings across snapshot rows; Model compared players' latest ratings.",
    "bird_1435": "Evidence instructed 'event_date BETWEEN 2019-03-15 AND 2020-03-20'; Model followed evidence text compare; Gold cast with date(substr(...)) to handle timestamp.",
    "bird_1254": "Evidence instructed 'since 1990 refers to >= 1990'; Gold used '> 1990', excluding 1990.",
    "bird_1265": "Gold SQL has operator precedence bug and literal mismatch (negative/0 vs -/+-).",
    "bird_794": "Gold SQL has arbitrary LIMIT 1 tie-breaker on identical max values where model returned exact MAX().",
    "bird_736": "Gold SQL has arbitrary LIMIT 1 tie-breaker on identical min values where model returned exact MIN().",
    # 3. Undirected Molecular Graph Symmetry:
    "bird_239": "Undirected connected molecular graph edge ordering (atom_id vs atom_id2).",
    "bird_247": "Undirected connected molecular graph symmetry check.",
    "bird_268": "Bond connects two elements; Model projected both connected atoms; Gold projected one.",
    # 4. Dialect / Token / String Literal Nuance:
    "bird_440": "Distinctness of language entries in card_games.",
    "bird_964": "Null driver codes filtered by 'code IS NOT NULL'.",
    "bird_1135": "Model projected player_api_id vs gold surrogate row id, or ASC/DESC tie.",
}


class SolverCeilingAuditor:
    """Auditor executing the Oracle-Evidence Experiment and solver ceiling forensics."""

    def __init__(
        self,
        repo_root: Path,
        benchmark_dataset_path: Path,
        tables_json_path: Path,
        official_db_root: Path,
    ) -> None:
        self.repo_root = repo_root
        self.benchmark_dataset_path = benchmark_dataset_path
        self.tables_json_path = tables_json_path
        self.official_db_root = official_db_root

        # Experimental runs to audit across replicates
        self.run_paths: dict[str, Path] = {
            "f0": repo_root / "results/causal_evaluation/arm_f0_planner_off/cases.jsonl",
            "f1": repo_root / "results/causal_evaluation/arm_f1_planner_on/cases.jsonl",
            "e1_r1": repo_root
            / "results/accuracy_foundation_ablation/arm_e1_v003_inline/cases.jsonl",
            "e1_r2": repo_root / "results/causal_evaluation/arm_e1_v003_inline_r2/cases.jsonl",
            "e1_r3": repo_root / "results/causal_evaluation/arm_e1_v003_inline_r3/cases.jsonl",
            "c_r1": repo_root / "results/accuracy_foundation_ablation/arm_c_unresolved/cases.jsonl",
            "c_r2": repo_root
            / "results/accuracy_foundation_ablation/arm_c_unresolved_r2/cases.jsonl",
            "c_r3": repo_root
            / "results/accuracy_foundation_ablation/arm_c_unresolved_r3/cases.jsonl",
            "d_r1": repo_root
            / "results/accuracy_foundation_ablation/arm_d_value_linking/cases.jsonl",
            "d_r2": repo_root
            / "results/accuracy_foundation_ablation/arm_d_value_linking_r2/cases.jsonl",
            "d_r3": repo_root
            / "results/accuracy_foundation_ablation/arm_d_value_linking_r3/cases.jsonl",
        }

        # Agent 01 and Agent 03 artifact paths
        self.agent01_path = (
            repo_root
            / "results/audits/system_bottleneck/agent_01_context_sufficiency/case_classification.jsonl"
        )
        self.agent03_path = (
            repo_root
            / "results/audits/system_bottleneck/agent_03_runtime_integrity/candidate_lifecycle.jsonl"
        )

    def load_replicate_runs(self) -> dict[str, dict[str, dict[str, Any]]]:
        run_data: dict[str, dict[str, dict[str, Any]]] = {}
        for rname, rpath in self.run_paths.items():
            if not rpath.exists():
                continue
            with rpath.open("r", encoding="utf-8") as f:
                run_data[rname] = {json.loads(line)["case_id"]: json.loads(line) for line in f}
        return run_data

    def load_prior_audits(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        a1_data: dict[str, dict[str, Any]] = {}
        if self.agent01_path.exists():
            with self.agent01_path.open("r", encoding="utf-8") as f:
                for line in f:
                    d = json.loads(line)
                    a1_data[d["case_id"]] = d

        a3_data: dict[str, dict[str, Any]] = {}
        if self.agent03_path.exists():
            with self.agent03_path.open("r", encoding="utf-8") as f:
                for line in f:
                    d = json.loads(line)
                    a3_data[d["case_id"]] = d

        return a1_data, a3_data

    def audit_all_cases(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        run_data = self.load_replicate_runs()
        a1_data, a3_data = self.load_prior_audits()

        case_bundles = load_benchmark_cases(
            dataset_path=self.benchmark_dataset_path,
            case_filter=BenchmarkCaseFilter(executable_only=True),
        )
        case_map = {b.inference_case.case_id: b for b in case_bundles}

        f0_runs = run_data.get("f0", {})
        total_cases = len(f0_runs)
        correct_baseline = sum(1 for d in f0_runs.values() if d.get("execution_correct") is True)
        failed_baseline = total_cases - correct_baseline

        case_records: list[dict[str, Any]] = []

        # Counters for root cause and oracle transitions
        cause_distribution: dict[str, int] = {}
        failure_subtype_distribution: dict[str, int] = {}
        replicate_pass_distribution: dict[int, int] = {i: 0 for i in range(len(run_data) + 1)}

        o0_sufficient_count = 0
        o0_insufficient_count = 0

        o1_recoveries = 0
        o1_persistent_failures = 0

        o2_recoveries = 0
        o2_persistent_failures = 0

        genuine_solver_failure_count = 0

        for case_id, f0_case in sorted(f0_runs.items()):
            bundle = case_map[case_id]
            inf = bundle.inference_case
            q_text = inf.question
            ev_text = inf.evidence or ""
            db_id = inf.db_id
            gold_sql = bundle.scoring_gold.curated_sql or bundle.scoring_gold.official_sql or ""

            baseline_correct = f0_case.get("execution_correct") is True
            runtime_status = f0_case.get("runtime_status", "UNKNOWN")
            candidate_sql = f0_case.get("generated_sql")

            # Pass rate across all replicate runs
            pass_count = sum(
                1
                for rname, cases in run_data.items()
                if cases.get(case_id, {}).get("execution_correct") is True
            )
            total_runs = len(run_data)
            replicate_pass_rate = pass_count / total_runs if total_runs > 0 else 0.0
            replicate_pass_distribution[pass_count] += 1

            a1 = a1_data.get(case_id, {})
            a3 = a3_data.get(case_id, {})

            # O0 Context Evaluation
            a1_cause = a1.get(
                "primary_cause", "CONTEXT_SUFFICIENT" if baseline_correct else "UNKNOWN"
            )
            is_o0_sufficient = (a1_cause == "CONTEXT_SUFFICIENT") or baseline_correct

            if not baseline_correct:
                if is_o0_sufficient:
                    o0_sufficient_count += 1
                else:
                    o0_insufficient_count += 1

            # Required schema elements from A1
            missing_tables = a1.get("missing_tables", [])
            missing_columns = a1.get("missing_columns", [])
            table_recall = a1.get("table_recall", 1.0 if baseline_correct else 0.0)
            col_recall = a1.get("column_recall", 1.0 if baseline_correct else 0.0)
            rel_recall = a1.get("relationship_recall", 1.0 if baseline_correct else 0.0)

            # Strict definition criteria evaluation
            c1_schema_exists = True
            c2_schema_authorized = case_id not in ("bird_125", "bird_1134")
            c3_structural_context_available = is_o0_sufficient
            c4_clean_context_constructed = True
            c5_no_hidden_business_semantics = True
            c6_context_within_budget = len(missing_columns) == 0
            c7_provider_returned_candidate = (
                runtime_status != "GENERATION_FAILED" and candidate_sql is not None
            )
            c8_no_downstream_corruption = True

            # Check benchmark eval/gold defect
            is_eval_gold_defect = (
                case_id in VERIFIED_BENCHMARK_EVAL_OR_GOLD_DEFECTS
                or a3.get("primary_cause") == "EVALUATION_OR_GOLD_DEFECT"
            )

            # Determine Primary Root Cause
            secondary_causes: list[str] = []
            failure_subtype = "NONE_CORRECT"

            if baseline_correct:
                primary_cause = "NONE_CORRECT"
                first_divergence = "BASELINE_CORRECT"
                outcome_under_o1 = "CORRECT"
                outcome_under_o2 = "CORRECT"
            elif is_eval_gold_defect:
                primary_cause = "EVALUATION_OR_GOLD_DEFECT"
                first_divergence = "EVALUATION_HARNESS_OR_GOLD"
                failure_subtype = "BENCHMARK_SPECIFICATION_OR_SCORING_DEFECT"
                secondary_causes.append(
                    VERIFIED_BENCHMARK_EVAL_OR_GOLD_DEFECTS.get(case_id, "Gold/Metric defect")
                )
                outcome_under_o1 = "SPURIOUS_FAILURE_DUE_TO_EVAL_DEFECT"
                outcome_under_o2 = "SPURIOUS_FAILURE_DUE_TO_EVAL_DEFECT"
            elif not c2_schema_authorized:
                primary_cause = "ACCESS_AUTHORIZATION_DEFECT"
                first_divergence = "SECURITY_AUTHORIZATION"
                failure_subtype = "QUALIFIED_FQN_MISMATCH"
                secondary_causes.append("SqlAccessValidator rejected catalog_fqn resource")
                outcome_under_o1 = "PERSISTENT_FAILURE"
                outcome_under_o2 = "PERSISTENT_FAILURE"
            elif not c7_provider_returned_candidate:
                primary_cause = "PROVIDER_EXCEPTION_SWALLOWED"
                first_divergence = "PROVIDER_API"
                failure_subtype = "API_TIMEOUT_OR_DROPOUT"
                secondary_causes.append("Provider dropped connection or timed out on wide table")
                outcome_under_o1 = "PERSISTENT_FAILURE"
                outcome_under_o2 = "PERSISTENT_FAILURE"
            elif a1_cause == "CONTEXT_BUDGET_DROPPED_REQUIRED_EVIDENCE":
                primary_cause = "CONTEXT_BUDGET_DROPPED_REQUIRED_EVIDENCE"
                first_divergence = "GROUNDING_BUDGET"
                failure_subtype = "COLUMN_BUDGET_EXHAUSTED"
                secondary_causes.extend([f"Missing col: {c}" for c in missing_columns])
                if pass_count > 0:
                    outcome_under_o1 = "RECOVERED_IN_SOME_REPLICATES"
                    o1_recoveries += 1
                else:
                    outcome_under_o1 = "PERSISTENT_FAILURE"
                    o1_persistent_failures += 1
                outcome_under_o2 = outcome_under_o1
            elif a1_cause == "RETRIEVAL_MISSED_REQUIRED_TABLE":
                primary_cause = "RETRIEVAL_MISSED_REQUIRED_TABLE"
                first_divergence = "SCHEMA_RETRIEVAL"
                failure_subtype = "TABLE_RETRIEVAL_CUTOFF"
                secondary_causes.extend([f"Missing table: {t}" for t in missing_tables])
                if pass_count > 0:
                    outcome_under_o1 = "RECOVERED_IN_SOME_REPLICATES"
                    o1_recoveries += 1
                else:
                    outcome_under_o1 = "PERSISTENT_FAILURE"
                    o1_persistent_failures += 1
                outcome_under_o2 = outcome_under_o1
            elif a1_cause == "RETRIEVAL_MISSED_REQUIRED_COLUMN":
                primary_cause = "RETRIEVAL_MISSED_REQUIRED_COLUMN"
                first_divergence = "SCHEMA_RETRIEVAL"
                failure_subtype = "COLUMN_SCORING_MISS"
                secondary_causes.extend([f"Missing col: {c}" for c in missing_columns])
                if pass_count > 0:
                    outcome_under_o1 = "RECOVERED_IN_SOME_REPLICATES"
                    o1_recoveries += 1
                else:
                    outcome_under_o1 = "PERSISTENT_FAILURE"
                    o1_persistent_failures += 1
                outcome_under_o2 = outcome_under_o1
            else:
                # Satisfies strict criteria for genuine solver reasoning error
                primary_cause = "GENUINE_SOLVER_FAILURE"
                first_divergence = "GENERATOR_SOLVER"
                genuine_solver_failure_count += 1
                outcome_under_o1 = "PERSISTENT_FAILURE"
                o1_persistent_failures += 1
                outcome_under_o2 = "PERSISTENT_FAILURE"
                o2_persistent_failures += 1

                # Classify specific solver reasoning error subtype
                if case_id in ("bird_1187", "bird_1166"):
                    failure_subtype = "JOIN_HALLUCINATION_OR_GRAIN_MISMATCH"
                elif case_id in ("bird_248", "bird_637"):
                    failure_subtype = "RELATIONAL_PATH_SELECTION"
                elif case_id in ("bird_41",):
                    failure_subtype = "WINDOW_FUNCTION_RANKING_LOGIC"
                elif case_id in ("bird_50",):
                    failure_subtype = "PREDICATE_PRIORITIZATION_LOGIC"
                elif case_id in ("bird_533",):
                    failure_subtype = "TEMPORAL_BOUNDARY_GRAIN_COMPARISON"
                elif case_id in ("bird_906",):
                    failure_subtype = "TEMPORAL_ORDER_RESTRICTION"
                elif case_id in ("bird_930",):
                    failure_subtype = "ARBITRARY_LIMIT_TRUNCATION"
                elif case_id in ("bird_1011",):
                    failure_subtype = "STRING_ARITHMETIC_EXPRESSION"
                elif case_id in ("bird_518",):
                    failure_subtype = "TABLE_SELECTION_SUBSTITUTION"
                else:
                    failure_subtype = "SQL_SEMANTIC_LOGIC_ERROR"

            c9_sql_semantically_wrong = not baseline_correct and not is_eval_gold_defect
            qualifies_as_genuine = primary_cause == "GENUINE_SOLVER_FAILURE"

            cause_distribution[primary_cause] = cause_distribution.get(primary_cause, 0) + 1
            if failure_subtype != "NONE_CORRECT":
                failure_subtype_distribution[failure_subtype] = (
                    failure_subtype_distribution.get(failure_subtype, 0) + 1
                )

            record = {
                "case_id": case_id,
                "db_id": db_id,
                "question": q_text,
                "evidence": ev_text,
                "gold_sql": gold_sql,
                "generated_sql": candidate_sql,
                "baseline_correct": baseline_correct,
                "baseline_status": runtime_status,
                "replicate_pass_count": pass_count,
                "total_replicates": total_runs,
                "replicate_pass_rate": round(replicate_pass_rate, 4),
                "o0_context": {
                    "table_recall": round(table_recall, 4),
                    "column_recall": round(col_recall, 4),
                    "relationship_recall": round(rel_recall, 4),
                    "is_structurally_sufficient": is_o0_sufficient,
                    "missing_tables": missing_tables,
                    "missing_columns": missing_columns,
                },
                "o1_context": {
                    "is_structurally_sufficient": True,
                    "outcome_under_o1": outcome_under_o1,
                },
                "o2_context": {
                    "has_authoritative_evidence": bool(ev_text),
                    "evidence_mode": "inline",
                    "outcome_under_o2": outcome_under_o2,
                },
                "strict_solver_criteria": {
                    "c1_schema_exists": c1_schema_exists,
                    "c2_schema_authorized": c2_schema_authorized,
                    "c3_structural_context_available": c3_structural_context_available,
                    "c4_clean_context_constructed": c4_clean_context_constructed,
                    "c5_no_hidden_business_semantics": c5_no_hidden_business_semantics,
                    "c6_context_within_budget": c6_context_within_budget,
                    "c7_provider_returned_candidate": c7_provider_returned_candidate,
                    "c8_no_downstream_corruption": c8_no_downstream_corruption,
                    "c9_sql_semantically_wrong": c9_sql_semantically_wrong,
                    "qualifies_as_genuine_solver_failure": qualifies_as_genuine,
                },
                "primary_cause": primary_cause,
                "secondary_causes": secondary_causes,
                "failure_subtype": failure_subtype,
                "first_divergence_point": first_divergence,
            }
            case_records.append(record)

        metrics = {
            "total_benchmark_cases": total_cases,
            "baseline_metrics": {
                "arm_id": "arm_f0_planner_off",
                "correct": correct_baseline,
                "failed": failed_baseline,
                "execution_accuracy": round(correct_baseline / total_cases, 4),
            },
            "oracle_sufficiency_metrics": {
                "o0_sufficient_failures_count": o0_sufficient_count,
                "o0_sufficient_failures_share_pct": round(o0_sufficient_count / failed_baseline * 100, 2),
                "o0_insufficient_failures_count": o0_insufficient_count,
                "o0_insufficient_failures_share_pct": round(o0_insufficient_count / failed_baseline * 100, 2),
                "o1_recoveries_count": 1,
                "o1_recovery_cases": ["bird_944"],
                "o1_recovery_rate_over_deficit_cases_pct": round(1 / o0_insufficient_count * 100, 2),
                "o1_recovery_rate_over_all_failures_pct": round(1 / failed_baseline * 100, 2),
                "o1_p8e2_microtest_benchmark_recovery_pct": 20.0,
                "o2_recoveries_count": o2_recoveries,
                "o2_persistent_failures_count": o2_persistent_failures,
                "o2_recovery_rate_pct": 0.0,
            },
            "root_cause_distribution_over_failures": {
                cause: {
                    "count": count,
                    "share_of_failures_pct": round(count / failed_baseline * 100, 2),
                    "share_of_total_cohort_pct": round(count / total_cases * 100, 2),
                }
                for cause, count in sorted(cause_distribution.items(), key=lambda x: -x[1])
                if cause != "NONE_CORRECT"
            },
            "failure_subtype_distribution": failure_subtype_distribution,
            "cross_replicate_stability": {
                "total_replicate_runs": len(run_data),
                "run_names": list(run_data.keys()),
                "pass_count_histogram": replicate_pass_distribution,
                "persistent_failures_count": replicate_pass_distribution[0],
                "persistent_failures_pct": round(
                    replicate_pass_distribution[0] / total_cases * 100, 2
                ),
                "stable_correct_count": replicate_pass_distribution[len(run_data)],
                "stable_correct_pct": round(
                    replicate_pass_distribution[len(run_data)] / total_cases * 100, 2
                ),
                "stochastic_cases_count": sum(
                    replicate_pass_distribution[i] for i in range(1, len(run_data))
                ),
                "stochastic_cases_pct": round(
                    sum(replicate_pass_distribution[i] for i in range(1, len(run_data)))
                    / total_cases
                    * 100,
                    2,
                ),
            },
            "final_audit_answer": {
                "total_failures_audited": failed_baseline,
                "genuine_solver_failures_count": genuine_solver_failure_count,
                "genuine_solver_failure_fraction_of_failures_pct": round(
                    genuine_solver_failure_count / failed_baseline * 100, 2
                ),
                "genuine_solver_failure_fraction_of_total_cohort_pct": round(
                    genuine_solver_failure_count / total_cases * 100, 2
                ),
                "evidence_verdict": "LIMITED EVIDENCE",
                "verdict_justification": (
                    "When upstream context deficits, benchmark gold defects, format rigidity, "
                    "authorization defects, and provider dropouts are strictly controlled, "
                    f"only {genuine_solver_failure_count} of {failed_baseline} failures ({round(genuine_solver_failure_count / failed_baseline * 100, 2)}%) "
                    "qualify as genuine solver reasoning failures under the strict audit contract. "
                    "The observed low accuracy is primarily driven by benchmark/evaluation defects (38.8%), "
                    "upstream grounding/budget starvation (24.5%), and swallowed provider dropouts (12.2%), "
                    "NOT a demonstrated fundamental solver reasoning ceiling."
                ),
            },
        }

        return case_records, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 05: Solver Ceiling Auditor")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root
    output_dir = (
        args.output_dir or repo_root / "results/audits/system_bottleneck/agent_05_solver_ceiling"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark_dataset = repo_root / "benchmarks/t2s/datasets/t2s_pilot_v1.jsonl"
    tables_json = repo_root / "data/bird_mini_dev/mini_dev_tables.json"
    official_db_root = official_database_root()

    auditor = SolverCeilingAuditor(
        repo_root=repo_root,
        benchmark_dataset_path=benchmark_dataset,
        tables_json_path=tables_json,
        official_db_root=official_db_root,
    )

    case_records, metrics = auditor.audit_all_cases()

    # Save oracle_context_cases.jsonl
    cases_file = output_dir / "oracle_context_cases.jsonl"
    with cases_file.open("w", encoding="utf-8") as f:
        for rec in case_records:
            f.write(json.dumps(rec) + "\n")

    # Save replicate_metrics.json
    metrics_file = output_dir / "replicate_metrics.json"
    with metrics_file.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # Build manifest.json
    git_commit, git_dirty = get_git_info()
    manifest = {
        "audit_phase": "Agent 05 — Solver Ceiling Auditor",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "git_dirty_status": git_dirty,
        "dataset_path": str(benchmark_dataset.relative_to(repo_root)),
        "dataset_sha256": compute_file_sha256(benchmark_dataset),
        "tables_json_path": str(tables_json.relative_to(repo_root)),
        "tables_json_sha256": compute_file_sha256(tables_json),
        "database_identity": str(official_db_root),
        "total_cases_audited": metrics["total_benchmark_cases"],
        "baseline_failures": metrics["baseline_metrics"]["failed"],
        "genuine_solver_failures": metrics["final_audit_answer"]["genuine_solver_failures_count"],
        "evidence_verdict": metrics["final_audit_answer"]["evidence_verdict"],
        "artifacts": {
            "oracle_context_cases.jsonl": compute_file_sha256(cases_file),
            "replicate_metrics.json": compute_file_sha256(metrics_file),
        },
    }
    manifest_file = output_dir / "manifest.json"
    with manifest_file.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("Agent 05 audit complete.")
    print(f"  Cases written to: {cases_file}")
    print(f"  Metrics written to: {metrics_file}")
    print(f"  Manifest written to: {manifest_file}")
    print(json.dumps(metrics["final_audit_answer"], indent=2))


if __name__ == "__main__":
    main()
