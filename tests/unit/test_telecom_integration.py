"""Unit tests for Telecom enterprise components migrated from text2sql."""
from __future__ import annotations

import pytest
from t2s.verification.ast_policy_guard import AstPolicyGuard, PolicyCatalog, PolicyFinding
from t2s.benchmark.telecom_perturbations import TELECOM_PERTURBATIONS
from t2s.benchmark.sqlgrade_evaluator import SqlGradeEvaluator, SqlGradeResult
from t2s.grounding.steiner_join_graph import (
    GraphJoinEdge,
    SteinerJoinGraph,
    SteinerJoinPlan,
)
from t2s.grounding.tier0_domain_filter import (
    Tier0DomainFilter,
    Tier0FilterConfig,
    classify_layer,
)


def test_ast_policy_guard_blocks_writes():
    guard = AstPolicyGuard()
    findings = guard.validate("DROP TABLE users;")
    assert guard.is_blocked(findings)
    assert any(f.code == "READ_ONLY" for f in findings)


def test_ast_policy_guard_enforces_partition_filter():
    catalog = PolicyCatalog(
        tables={"cdr_voice": ["msisdn", "duration", "dt"]},
        partition_columns={"cdr_voice": "dt"},
    )
    guard = AstPolicyGuard(catalog=catalog, dialect="sqlite")

    # Missing partition filter -> BLOCKED
    bad_sql = "SELECT msisdn, SUM(duration) FROM cdr_voice WHERE msisdn = '0901234567';"
    bad_findings = guard.validate(bad_sql)
    assert guard.is_blocked(bad_findings)
    assert any(f.code == "PARTITION" for f in bad_findings)

    # Has partition filter -> PASS
    good_sql = "SELECT msisdn, SUM(duration) FROM cdr_voice WHERE dt = '2026-09-01' AND msisdn = '0901234567';"
    good_findings = guard.validate(good_sql)
    assert not guard.is_blocked(good_findings)
    assert not any(f.code == "PARTITION" for f in good_findings)


def test_ast_policy_guard_warns_on_nm_fanout():
    catalog = PolicyCatalog(
        tables={"cdr_voice": ["msisdn", "promo_id"], "promos": ["promo_id", "discount"]},
        nm_pairs={("cdr_voice", "promos")},
    )
    guard = AstPolicyGuard(catalog=catalog)

    # Without deduplication -> WARN
    fanout_sql = "SELECT c.msisdn, p.discount FROM cdr_voice c JOIN promos p ON c.promo_id = p.promo_id;"
    findings = guard.validate(fanout_sql)
    assert any(f.code == "FANOUT" and f.severity == "warn" for f in findings)

    # With DISTINCT -> No warning
    dedup_sql = "SELECT DISTINCT c.msisdn, p.discount FROM cdr_voice c JOIN promos p ON c.promo_id = p.promo_id;"
    dedup_findings = guard.validate(dedup_sql)
    assert not any(f.code == "FANOUT" for f in dedup_findings)


def test_steiner_join_graph_avoids_nm_shortcut():
    edges = [
        GraphJoinEdge("cdr_voice", "dim_sub", ("msisdn",), ("msisdn",), "fk", "N:1", 0.02, 1.0),
        GraphJoinEdge("dim_sub", "contract", ("sub_id",), ("sub_id",), "fk", "N:1", 0.0, 1.0),
        GraphJoinEdge("contract", "dim_offer", ("offer_id",), ("offer_id",), "fk", "N:1", 0.0, 1.0),
        # Shortcut N:M with high orphan rate
        GraphJoinEdge("cdr_voice", "dim_offer", ("promo_code",), ("promo_code",), "name", "N:M", 0.35, 0.6),
    ]

    graph = SteinerJoinGraph(edges)
    plan = graph.plan(["cdr_voice", "dim_offer"])

    assert plan.connected
    # Ensures it avoids the dangerous N:M shortcut
    assert all(e.cardinality != "N:M" for e in plan.edges)
    # Checks that bridge tables were found
    assert set(plan.bridge_tables) == {"contract", "dim_sub"}


def test_tier0_layer_classification():
    assert classify_layer("raw_cdr_network") == "raw"
    assert classify_layer("stg_billing") == "stg"
    assert classify_layer("dwh_subscribers") == "dwh"
    assert classify_layer("mart_monthly_revenue") == "mart"
    assert classify_layer("agg_daily_kpi") == "mart"


def test_tier0_filter_domain_and_layer_reduction():
    filter_engine = Tier0DomainFilter(
        Tier0FilterConfig(
            domain_keywords={
                "revenue": ["revenue", "billing", "cước", "doanh_thu"],
                "network": ["network", "cdr"],
            },
            preferred_layers={"mart", "dwh"},
        )
    )

    schemas = [
        "raw_network_cdr",
        "stg_billing",
        "dwh_billing",
        "mart_revenue",
        "mart_network",
        "misc_logs",
    ]
    table_to_schema = {f"t_{s}": s for s in schemas}

    res = filter_engine.filter_catalog(
        schema_names=schemas,
        table_to_schema=table_to_schema,
        target_domains={"revenue"},
    )

    # Allowed schemas should only be dwh_billing and mart_revenue
    assert res.allowed_schemas == {"dwh_billing", "mart_revenue"}
    assert res.reduction_ratio >= 0.60
    assert "raw_network_cdr" in res.dropped_schemas


def test_sqlgrade_evaluator_decision_tree():
    evaluator = SqlGradeEvaluator()

    # Mock execute_fn: returns identical results for gold and pred
    def mock_exec_exact(sql: str):
        return True, ["col1", "col2"], [(1, "A"), (2, "B")], ""

    # Mock perturb_runner that passes all perturbations
    def mock_perturb_pass(gold: str, pred: str, ordered: bool):
        return []

    res_a = evaluator.grade(
        gold_sql="SELECT col1, col2 FROM t;",
        pred_sql="SELECT col1, col2 FROM t;",
        execute_fn=mock_exec_exact,
        perturb_runner=mock_perturb_pass,
    )
    assert res_a.grade == "A"
    assert res_a.ex is True

    # Failed perturbation -> Grade F (Silent error)
    def mock_perturb_fail(gold: str, pred: str, ordered: bool):
        return ["msisdn_reassigned"]

    res_f = evaluator.grade(
        gold_sql="SELECT col1, col2 FROM t;",
        pred_sql="SELECT col1, col2 FROM t;",
        execute_fn=mock_exec_exact,
        perturb_runner=mock_perturb_fail,
    )
    assert res_f.grade == "F"
    assert "Sai ngầm" in res_f.reason
