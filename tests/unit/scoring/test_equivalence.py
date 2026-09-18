"""Result-equivalence semantics: A + B1-B5 + D + null/dup/order handling."""

from __future__ import annotations

from t2s.evaluation.scoring.equivalence import (
    OutputContract,
    compute_result_equivalence,
    sql_forms_differ,
)
from t2s.evaluation.scoring.taxonomy import BSubtype
from tests.unit.scoring.conftest import table


def test_exact_match_is_level_exact_no_relaxations() -> None:
    gold = table(("n",), [(1,), (2,)])
    cand = table(("n",), [(1,), (2,)])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT n FROM t ORDER BY n")
    assert outcome.equivalent
    assert outcome.level == "EXACT"
    assert outcome.relaxations == ()


def test_b1_harmless_extra_columns() -> None:
    gold = table(("region",), [("east",), ("west",)])
    cand = table(("region", "amount"), [("east", 10), ("west", 20)])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT region FROM t")
    assert outcome.equivalent
    assert BSubtype.B1_EXTRA_COLUMNS in outcome.relaxations


def test_b2_column_order_variance() -> None:
    gold = table(("region", "amount"), [("east", 10)])
    cand = table(("amount", "region"), [(10, "east")])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT region, amount FROM t")
    assert outcome.equivalent
    assert BSubtype.B2_COLUMN_ORDER in outcome.relaxations


def test_b3_label_equivalence_only_with_explicit_map() -> None:
    gold = table(("sex",), [("Male",), ("Female",)])
    cand = table(("sex",), [("M",), ("F",)])
    # Without a map -> not equivalent (no guessing).
    assert not compute_result_equivalence(cand, gold, gold_sql="SELECT sex FROM t").equivalent
    # With an explicit map -> B3.
    contract = OutputContract(
        value_equivalence=(frozenset({"M", "Male"}), frozenset({"F", "Female"}))
    )
    outcome = compute_result_equivalence(
        cand, gold, contract=contract, gold_sql="SELECT sex FROM t"
    )
    assert outcome.equivalent
    assert BSubtype.B3_LABEL_EQUIVALENT in outcome.relaxations


def test_b4_row_order_variance_when_order_not_required() -> None:
    gold = table(("n",), [(1,), (2,), (3,)])
    cand = table(("n",), [(3,), (1,), (2,)])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT n FROM t")
    assert outcome.equivalent
    assert BSubtype.B4_ROW_ORDER in outcome.relaxations


def test_order_sensitive_question_not_treated_order_insensitive() -> None:
    gold = table(("n",), [(1,), (2,), (3,)])
    cand = table(("n",), [(3,), (2,), (1,)])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT n FROM t ORDER BY n ASC")
    assert not outcome.equivalent


def test_b5_equivalent_form_detected_on_sql() -> None:
    assert sql_forms_differ("SELECT a, b FROM t", "SELECT b, a FROM t") is True
    assert sql_forms_differ("SELECT a FROM t", "select a from t") is False


def test_projection_exact_contract_blocks_extra_columns() -> None:
    gold = table(("region",), [("east",)])
    cand = table(("region", "amount"), [("east", 10)])
    outcome = compute_result_equivalence(
        cand, gold, contract=OutputContract(projection_exact=True), gold_sql="SELECT region FROM t"
    )
    assert not outcome.equivalent


def test_wrong_values_are_not_equivalent() -> None:
    gold = table(("n",), [(1,), (2,)])
    cand = table(("n",), [(1,), (99,)])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT n FROM t")
    assert not outcome.equivalent


def test_duplicate_rows_significant_by_default() -> None:
    gold = table(("n",), [(1,), (1,), (2,)])
    cand = table(("n",), [(1,), (2,)])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT n FROM t")
    assert not outcome.equivalent


def test_null_and_numeric_normalization_matches() -> None:
    gold = table(("a", "b"), [(1.0, None), (2, "x")])
    cand = table(("a", "b"), [(2.0, "x"), (1, None)])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT a, b FROM t")
    assert outcome.equivalent  # B4 row order


def test_column_count_over_bound_falls_back_safely() -> None:
    # 9 candidate columns exceeds MAX_COLUMNS_FOR_MAPPING_SEARCH=8; must not crash
    # and must not falsely claim equivalence.
    gold = table(("x",), [(1,)])
    cand = table(tuple(f"c{i}" for i in range(9)), [tuple(range(9))])
    outcome = compute_result_equivalence(cand, gold, gold_sql="SELECT x FROM t")
    assert not outcome.equivalent
    assert outcome.detail == "column_count_exceeds_mapping_bound"
