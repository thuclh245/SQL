import json
from pathlib import Path

from scripts.build_p8e1r_artifacts import (
    extract_actual_gold_join_edges,
    resolve_gold_columns_hierarchical,
)
from t2s.benchmark.scoring import evaluate_candidate_vs_gold

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = PROJECT_ROOT / "results" / "p8e1r_metric_integrity"
OFFICIAL_DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"


def test_p8e1r_artifacts_exist_and_valid() -> None:
    expected_files = [
        "manifest.json",
        "qualified_column_bindings.jsonl",
        "qualified_column_metrics.json",
        "unresolved_column_bindings.json",
        "gold_join_edges.jsonl",
        "join_edge_metrics.json",
        "provenance_safe_metrics.json",
        "control_regression_audit.json",
        "difficulty_distribution.json",
        "difficulty_root_causes.json",
        "difficulty_p3_mechanisms.json",
        "structural_complexity.jsonl",
        "structural_failure_rates.json",
        "remediation_by_difficulty.json",
        "remediation_by_structure.json",
        "context_growth_by_difficulty.json",
        "evaluator_validation.json",
        "corrected_runtime_metrics.json",
        "holdout_governance_correction.json",
        "spending_gate.json",
        "summary.md",
    ]
    for fname in expected_files:
        fpath = RESULTS_DIR / fname
        assert fpath.exists(), f"Missing required artifact: {fname}"
        if fname.endswith(".json"):
            data = json.loads(fpath.read_text())
            assert isinstance(data, (dict, list))
        elif fname.endswith(".jsonl"):
            lines = [json.loads(line) for line in fpath.read_text().splitlines() if line.strip()]
            assert len(lines) == 100


def test_qualified_column_binding_distinguishes_same_name_in_different_tables() -> None:
    # If gold requires cards.name, but context only has sets.name,
    # table-qualified resolution requires cards.name and rejects sets.name.
    sql = (
        "SELECT cards.name FROM cards JOIN sets ON cards.setCode = sets.code "
        "WHERE sets.name = 'Magic'"
    )
    resolved_cols, unres = resolve_gold_columns_hierarchical(sql, "card_games")
    assert "cards.name" in resolved_cols
    assert "sets.name" in resolved_cols
    assert len(unres) == 0


def test_actual_join_edge_extraction_canonicalizes_edges() -> None:
    sql = "SELECT s.name FROM schools AS s JOIN frpm AS f ON s.CDSCode = f.CDSCode"
    edges = extract_actual_gold_join_edges(sql, "california_schools")
    assert len(edges) == 1
    # Canonical sorted pair
    assert edges[0] == (("frpm", "cdscode"), ("schools", "cdscode"))


def test_evaluator_validation_bird_11_true_positive() -> None:
    b11_db = OFFICIAL_DB_ROOT / "california_schools" / "california_schools.sqlite"
    cand_sql = (
        "SELECT s.CDSCode FROM schools AS s JOIN frpm AS f ON s.CDSCode = f.CDSCode "
        'WHERE (COALESCE(f."Enrollment (K-12)", 0) + COALESCE(f."Enrollment (Ages 5-17)", 0)) > 500'
    )
    gold_sql = (
        "SELECT T2.CDSCode FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode "
        "WHERE T2.`Enrollment (K-12)` + T2.`Enrollment (Ages 5-17)` > 500"
    )
    is_match, cand_res, gold_res = evaluate_candidate_vs_gold(cand_sql, gold_sql, b11_db)
    assert is_match is True
    assert cand_res.ok is True
    assert gold_res.ok is True
    assert len(cand_res.rows) == 7806
    assert len(gold_res.rows) == 7806


def test_control_regression_audit_zero_regressions() -> None:
    data = json.loads((RESULTS_DIR / "control_regression_audit.json").read_text())
    assert data["qualified_evidence_regressions_count"] == 0
    assert data["control_questions_evaluated"] == 24


def test_spending_gate_authorizes_paid_micro_experiment() -> None:
    data = json.loads((RESULTS_DIR / "spending_gate.json").read_text())
    assert data["spending_gate_decision"] == "PAID_MICRO_EXPERIMENT_READY"
    assert data["all_criteria_passed"] is True
    assert len(data["preregistered_micro_experiment"]["selected_targets"]) == 15
    assert len(data["preregistered_micro_experiment"]["selected_controls"]) == 5
    assert data["preregistered_micro_experiment"]["total_calls"] == 20
