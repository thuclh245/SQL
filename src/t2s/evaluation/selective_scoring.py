"""Outcome-aware evaluation for selective Text-to-SQL.

Execution accuracy alone rewards a system for always answering.  Here every
case has an expected outcome (answer / unanswerable / ambiguous) and every
prediction an outcome (answered / abstain / clarify / error), and the headline
metric is the *silent error rate*: of the results a user actually receives,
how many are wrong.

Results are compared by meaning, not by hash: row order, column order and
column names are ignored, extra columns are allowed, and numbers are compared
after rounding.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

MAX_MAPPINGS = 5000

Row = Sequence[Any]


def norm_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float, Decimal)):
        f = float(value)
        return f"{round(f, 2):.2f}".rstrip("0").rstrip(".") if f == f else "NaN"
    text = str(value).strip()
    try:
        return norm_value(float(text)) if text and text[0] in "-0123456789" else text
    except ValueError:
        return text


def _normalise(rows: Sequence[Row]) -> list[tuple[str, ...]]:
    return [tuple(norm_value(v) for v in r) for r in rows]


def results_match(pred: Sequence[Row], gold: Sequence[Row], *, allow_relabel: bool = False) -> bool:
    """True if some injective mapping of gold columns onto predicted columns makes the
    two row multisets equal.  Extra predicted columns are allowed.

    With ``allow_relabel`` a categorical gold column may map onto a predicted column
    through a consistent one-to-one value renaming (area_code ↔ area_name, NULL ↔
    'TOTAL' on roll-up rows), provided every other column matches exactly."""
    p, g = _normalise(pred), _normalise(gold)
    if len(p) != len(g):
        return False
    if not g:
        return True
    g_width, p_width = len(g[0]), len(p[0]) if p else 0
    if p_width < g_width:
        return False
    p_cols = [Counter(r[i] for r in p) for i in range(p_width)]
    candidates: list[list[tuple[int, bool]]] = []
    for j in range(g_width):
        g_col = Counter(r[j] for r in g)
        options = [(i, False) for i in range(p_width) if p_cols[i] == g_col]
        if not options and allow_relabel:
            profile = sorted(g_col.values())
            options = [(i, True) for i in range(p_width) if sorted(p_cols[i].values()) == profile]
        if not options:
            return False
        candidates.append(options)
    target = Counter(g)
    for n, mapping in enumerate(itertools.product(*candidates)):
        if n >= MAX_MAPPINGS:
            break
        idx = [i for i, _ in mapping]
        if len(set(idx)) != len(idx):
            continue
        projected = [tuple(r[i] for i in idx) for r in p]
        relabel = [j for j, (_, r) in enumerate(mapping) if r]
        if not relabel:
            if Counter(projected) == target:
                return True
        elif len(relabel) < g_width and _relabel_match(projected, g, relabel):
            return True
    return False


def _relabel_match(
    pred: list[tuple[str, ...]], gold: list[tuple[str, ...]], cols: list[int]
) -> bool:
    """Rows are aligned on the exactly-matched columns; each relabelled column must then
    carry a one-to-one renaming of the gold values."""
    keep = [j for j in range(len(gold[0])) if j not in cols]

    def key(row: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(row[j] for j in keep)

    g_groups: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
    p_groups: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
    for r in gold:
        g_groups.setdefault(key(r), []).append(r)
    for r in pred:
        p_groups.setdefault(key(r), []).append(r)
    if {k: len(v) for k, v in g_groups.items()} != {k: len(v) for k, v in p_groups.items()}:
        return False
    for j in cols:
        forward: dict[str, str] = {}
        for k, rows in g_groups.items():
            if len(rows) != 1:
                continue
            gv, pv = rows[0][j], p_groups[k][0][j]
            if forward.setdefault(gv, pv) != pv:
                return False
        if len(set(forward.values())) != len(forward):
            return False
        for k, rows in g_groups.items():
            want = Counter(forward.get(r[j], "\0missing") for r in rows)
            if want != Counter(r[j] for r in p_groups[k]):
                return False
    return True


def numbers_match(pred: Sequence[Row], gold: Sequence[Row]) -> bool:
    """Looser check: the multiset of numeric values per row matches (labels ignored).
    Used to tell "same numbers, different presentation" apart from wrong numbers."""

    def numeric(rows: Sequence[Row]) -> Counter[tuple[str, ...]]:
        out: Counter[tuple[str, ...]] = Counter()
        for r in rows:
            vals = sorted(
                norm_value(v)
                for v in r
                if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)
            )
            out[tuple(vals)] += 1
        return out

    return len(pred) == len(gold) and bool(gold) and numeric(pred) == numeric(gold)


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    expected: str
    predicted: str
    verdict: str  # correct | wrong | error | declined_ok | declined_wrong_kind | missed_decline
    silent_wrong: bool
    numbers_only: bool = False
    extra_columns: bool = False


def score_case(
    case: dict[str, Any],
    predicted: str,
    pred_rows: Sequence[Row] | None,
    gold_rows: Sequence[Row] | None,
    option_rows: Sequence[Sequence[Row]] = (),
) -> CaseScore:
    """``predicted`` is the pipeline status: answered | abstain | clarify | error."""
    expected = case["expected_outcome"]
    cid = case["id"]
    if expected == "answer":
        if predicted == "answered":
            assert pred_rows is not None and gold_rows is not None
            if results_match(pred_rows, gold_rows):
                wider = bool(gold_rows) and len(pred_rows[0]) > len(gold_rows[0])
                return CaseScore(cid, expected, predicted, "correct", False, extra_columns=wider)
            if results_match(pred_rows, gold_rows, allow_relabel=True):
                return CaseScore(cid, expected, predicted, "correct_relabel", False)
            if pred_rows and results_match(gold_rows, pred_rows, allow_relabel=True):
                # Mọi cột của model đều khớp gold, nhưng gold có thêm cột câu hỏi có thể
                # không yêu cầu. Chỉ tính trong EX "lỏng", vẫn coi là sai khi chấm chặt.
                return CaseScore(cid, expected, predicted, "subset_columns", True)
            return CaseScore(
                cid, expected, predicted, "wrong", True, numbers_match(pred_rows, gold_rows)
            )
        if predicted == "error":
            return CaseScore(cid, expected, predicted, "error", False)
        return CaseScore(cid, expected, predicted, "declined_answerable", False)
    want = "abstain" if expected == "unanswerable" else "clarify"
    if predicted == want:
        return CaseScore(cid, expected, predicted, "declined_ok", False)
    if predicted in ("abstain", "clarify"):
        return CaseScore(cid, expected, predicted, "declined_wrong_kind", False)
    if predicted == "answered":
        if (
            expected == "ambiguous"
            and pred_rows is not None
            and any(results_match(pred_rows, opt) for opt in option_rows)
        ):
            return CaseScore(cid, expected, predicted, "answered_one_reading", False)
        return CaseScore(cid, expected, predicted, "missed_decline", True)
    return CaseScore(cid, expected, predicted, "error", False)


CORRECT = ("correct", "correct_relabel")

# Cờ review cho biết gold có thể sai hoặc lệch câu hỏi; EX trên tập "sạch" bỏ các case này.
DISPUTED_FLAGS = ("question_gold_mismatch", "hidden_condition_in_gold", "pending_de_definition")


def disputed_case_ids(cases: Sequence[dict[str, Any]]) -> set[str]:
    return {
        c["id"]
        for c in cases
        if c.get("convention_conflicts") or set(c.get("review_flags") or {}) & set(DISPUTED_FLAGS)
    }


def summarise(scores: Sequence[CaseScore], disputed: set[str] | None = None) -> dict[str, Any]:
    disputed = disputed or set()
    total = len(scores)
    answer = [s for s in scores if s.expected == "answer"]
    clean = [s for s in answer if s.case_id not in disputed]
    non_answer = [s for s in scores if s.expected != "answer"]
    delivered = [s for s in scores if s.predicted == "answered"]
    declined = [s for s in scores if s.predicted in ("abstain", "clarify")]
    silent = sum(s.silent_wrong for s in delivered)
    correct_answers = sum(s.verdict in CORRECT for s in answer)
    good_declines = sum(s.expected != "answer" for s in declined)
    return {
        "cases": total,
        "answer_cases": len(answer),
        "execution_accuracy": _ratio(correct_answers, len(answer)),
        "execution_accuracy_strict": _ratio(
            sum(s.verdict == "correct" for s in answer), len(answer)
        ),
        "execution_accuracy_lenient": _ratio(
            sum(s.verdict in (*CORRECT, "subset_columns") for s in answer), len(answer)
        ),
        "execution_accuracy_clean_gold": _ratio(
            sum(s.verdict in CORRECT for s in clean), len(clean)
        ),
        "clean_gold_cases": len(clean),
        "numbers_only_matches": sum(s.numbers_only for s in answer),
        "coverage": _ratio(len(delivered), total),
        "silent_error_rate": _ratio(silent, len(delivered)),
        "precision_at_coverage": _ratio(len(delivered) - silent, len(delivered)),
        "execution_errors": sum(s.predicted == "error" for s in scores),
        "decline_precision": _ratio(good_declines, len(declined)),
        "decline_recall": _ratio(
            sum(s.predicted in ("abstain", "clarify") for s in non_answer), len(non_answer)
        ),
        "decline_exact": sum(s.verdict == "declined_ok" for s in non_answer),
        "false_declines": sum(s.verdict == "declined_answerable" for s in answer),
        "verdicts": dict(Counter(s.verdict for s in scores)),
        **grade_summary(scores, disputed),
    }


# Thang A–F chuẩn của dự án (docs/t2s_docs_v2/05, ADR-004), suy ra tự động từ verdict.
# E (lucky match) cần kiểm thử đột biến dữ liệu nên không tự phát hiện được: các case A/B
# trên gold bị tranh chấp được đánh dấu "E?" để audit. Từ chối đúng ở case không trả lời
# được / mơ hồ là hành vi đúng nên tính A; từ chối sai ở case trả lời được là D-refuse
# (không đưa kết quả sai, nhưng không làm được việc).
GRADE_OF = {
    "correct": "A",
    "correct_relabel": "B3",
    "subset_columns": "F-subset",
    "wrong": "D",
    "error": "D-error",
    "declined_answerable": "D-refuse",
    "declined_ok": "A",
    "declined_wrong_kind": "B-kind",
    "answered_one_reading": "C",
    "missed_decline": "D-missed",
}


def grade(score: CaseScore) -> str:
    g = GRADE_OF[score.verdict]
    if g == "A" and score.extra_columns:
        return "B1"
    return g


def grade_summary(scores: Sequence[CaseScore], disputed: set[str] | None = None) -> dict[str, Any]:
    disputed = disputed or set()
    grades = [grade(s) for s in scores]
    letters = Counter(g[0] for g in grades)
    total = len(scores)
    safe = letters["A"] + letters["B"]
    audited = total - letters["F"]
    return {
        "grades": dict(sorted(Counter(grades).items())),
        "letters": {k: letters[k] for k in "ABCDEF"},
        "semantic_safe_rate": _ratio(safe, total),
        "conditional_safe_rate": _ratio(safe, audited),
        "ambiguity_rate": _ratio(letters["C"], total),
        "true_error_rate": _ratio(letters["D"], total),
        "unknown_rate": _ratio(letters["F"], total),
        "lucky_match_suspects": sorted(
            s.case_id
            for s, g in zip(scores, grades, strict=True)
            if g[0] in "AB" and s.case_id in disputed and s.expected == "answer"
        ),
    }


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None
