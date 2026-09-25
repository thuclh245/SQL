from t2s.evaluation.selective_scoring import (
    disputed_case_ids,
    results_match,
    score_case,
    summarise,
)

GOLD = [("AREA_1", 5), ("AREA_2", 3)]


def test_match_ignores_row_order_column_order_and_extra_columns() -> None:
    pred = [(3, "AREA_2", "x"), (5, "AREA_1", "y")]
    assert results_match(pred, GOLD)


def test_numbers_are_compared_after_rounding_and_text_numbers_normalised() -> None:
    assert results_match([("a", 1.0000001)], [("a", "1")])


def test_wrong_value_does_not_match() -> None:
    assert not results_match([("AREA_1", 5), ("AREA_2", 4)], GOLD)


def test_missing_column_does_not_match() -> None:
    assert not results_match([("AREA_1",), ("AREA_2",)], GOLD)


def test_relabel_accepts_one_to_one_renaming_only_when_enabled() -> None:
    pred = [("Khu vuc 1", 5), ("Khu vuc 2", 3)]
    assert not results_match(pred, GOLD)
    assert results_match(pred, GOLD, allow_relabel=True)


def test_relabel_rejects_many_to_one_renaming() -> None:
    gold = [("A", 1), ("B", 2), ("C", 3)]
    pred = [("X", 1), ("X", 2), ("Y", 3)]
    assert not results_match(pred, gold, allow_relabel=True)


def test_relabel_handles_rollup_null_as_total() -> None:
    gold = [("AREA_1", 5), ("AREA_2", 3), (None, 8)]
    pred = [("AREA_1", 5), ("AREA_2", 3), ("TOTAL", 8)]
    assert results_match(pred, gold, allow_relabel=True)


def test_silent_error_counts_only_delivered_wrong_answers() -> None:
    answer = {"id": "A", "expected_outcome": "answer"}
    unans = {"id": "U", "expected_outcome": "unanswerable"}
    scores = [
        score_case(answer, "answered", [("AREA_1", 5), ("AREA_2", 3)], GOLD),
        score_case({"id": "B", "expected_outcome": "answer"}, "answered", [("AREA_1", 9)], GOLD),
        score_case({"id": "C", "expected_outcome": "answer"}, "error", None, GOLD),
        score_case(unans, "answered", [("x",)], None),
        score_case({"id": "V", "expected_outcome": "unanswerable"}, "abstain", None, None),
    ]
    s = summarise(scores)
    assert [x.verdict for x in scores] == [
        "correct",
        "wrong",
        "error",
        "missed_decline",
        "declined_ok",
    ]
    assert s["silent_error_rate"] == round(2 / 3, 4)
    assert s["decline_recall"] == 0.5
    assert s["decline_precision"] == 1.0


def test_clean_gold_excludes_disputed_cases() -> None:
    cases = [
        {"id": "A", "review_flags": {"hidden_condition_in_gold": "x"}},
        {"id": "B", "convention_conflicts": [{"convention": "C"}]},
        {"id": "C", "review_flags": {"heuristic_join": "ok để chấm"}},
    ]
    assert disputed_case_ids(cases) == {"A", "B"}


def test_prediction_with_fewer_columns_is_only_lenient_correct() -> None:
    case = {"id": "M", "expected_outcome": "answer"}
    s = score_case(case, "answered", [("AREA_1",), ("AREA_2",)], GOLD)
    assert s.verdict == "subset_columns" and s.silent_wrong
    summary = summarise([s])
    assert summary["execution_accuracy"] == 0.0
    assert summary["execution_accuracy_lenient"] == 1.0


def test_grades_follow_canonical_a_to_f_taxonomy() -> None:
    from t2s.evaluation.selective_scoring import grade

    answer = {"id": "A", "expected_outcome": "answer"}
    amb = {"id": "M", "expected_outcome": "ambiguous"}
    assert grade(score_case(answer, "answered", [("AREA_1", 5), ("AREA_2", 3)], GOLD)) == "A"
    wide = [("AREA_1", 5, "x"), ("AREA_2", 3, "y")]
    assert grade(score_case(answer, "answered", wide, GOLD)) == "B1"
    assert grade(score_case(answer, "answered", [("K1", 5), ("K2", 3)], GOLD)) == "B3"
    assert grade(score_case(answer, "answered", [("AREA_1", 9)], GOLD)) == "D"
    assert grade(score_case(answer, "abstain", None, GOLD)) == "D-refuse"
    assert grade(score_case(amb, "clarify", None, None)) == "A"
    assert grade(score_case(amb, "answered", [("x",)], None, [[("x",)]])) == "C"
    s = summarise(
        [
            score_case(answer, "answered", [("AREA_1", 5), ("AREA_2", 3)], GOLD),
            score_case(amb, "answered", [("y",)], None),
        ]
    )
    assert s["semantic_safe_rate"] == 0.5 and s["letters"]["D"] == 1


def test_relabel_handles_tied_counts() -> None:
    gold = [("AREA_1", 5), ("AREA_2", 4), ("AREA_3", 4), ("AREA_4", 4)]
    pred = [("Khu vuc 2", 4), ("Khu vuc 1", 5), ("Khu vuc 3", 4), ("Khu vuc 4", 4)]
    assert results_match(pred, gold, allow_relabel=True)
    assert not results_match([("X", 5), ("X", 4), ("Y", 4), ("Z", 4)], gold, allow_relabel=True)


def test_pivoted_counts_are_an_equivalent_formulation() -> None:
    from t2s.evaluation.selective_scoring import grade

    case = {"id": "M", "expected_outcome": "answer"}
    gold = [("CRITICAL", 35), ("MAJOR", 25)]
    assert grade(score_case(case, "answered", [(35, 25)], gold)) == "B5"
    assert grade(score_case(case, "answered", [(35, 24)], gold)) == "D"
