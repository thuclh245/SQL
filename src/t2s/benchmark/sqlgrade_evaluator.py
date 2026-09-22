"""SqlGrade Evaluator: Decision Tree A-F for Text-to-SQL.

Grades:
  A: Fully Correct (Matches gold, passes perturbations, column set matches) -> 0 min human effort
  B: Correct with Form Discrepancy (Matches gold, passes perturbations, extra columns or limit/order delta) -> <1 min
  C: Partial / Accidental Match (Matches gold on base but FAILS perturbation, or soft-F1 >= theta) -> 5-15 min
  D: Clearly Incorrect (Runs, no match, soft-F1 < theta) -> Rewrite
  E: Execution / Syntax Error (Parse failure, table/col not found, runtime error) -> Discard immediately
  F: DANGEROUS (Violates partition filter / security policy, or SILENT ERROR on perturbation) -> Severe risk

KPIs:
  - Usable Rate = (A + B) / Total
  - Assisted Rate = (A + B + C) / Total
  - Danger Rate = F / Total
"""
from __future__ import annotations

import datetime as _dt
import itertools
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

import sqlglot
from sqlglot import exp

from t2s.verification.ast_policy_guard import AstPolicyGuard, PolicyCatalog, PolicyFinding

NULL_SENTINEL = "\x00NULL"
DEFAULT_THETA_SOFT_F1 = 0.80
DANGEROUS_POLICY_CODES = {"PARTITION", "READ_ONLY"}


def norm_value(v: Any) -> Any:
    if v is None:
        return NULL_SENTINEL
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, int):
        return float(v)
    if isinstance(v, float):
        if v != v:
            return NULL_SENTINEL
        r = round(v, 6)
        return 0.0 if r == 0 else r
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace").strip()
    s = str(v).strip()
    try:
        return round(float(s), 6)
    except ValueError:
        return s


def norm_table(cols: list[str], rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return [tuple(norm_value(c) for c in r) for r in rows]


def _canon(rows: list[tuple[Any, ...]], ordered: bool) -> tuple[tuple[Any, ...], ...]:
    if ordered:
        return tuple(rows)
    return tuple(sorted(rows, key=lambda r: tuple(str(x) for x in r)))


def exact_match(gold_rows: list[tuple[Any, ...]], pred_rows: list[tuple[Any, ...]], ordered: bool) -> bool:
    if len(gold_rows) != len(pred_rows):
        return False
    if not gold_rows:
        return True
    ng, np_ = len(gold_rows[0]), len(pred_rows[0])
    if ng != np_:
        return False
    if _canon(gold_rows, ordered) == _canon(pred_rows, ordered):
        return True
    if ng > 7:
        return False
    for perm in itertools.permutations(range(ng)):
        permuted = [tuple(r[i] for i in perm) for r in pred_rows]
        if _canon(gold_rows, ordered) == _canon(permuted, ordered):
            return True
    return False


def subset_match(gold_rows: list[tuple[Any, ...]], pred_rows: list[tuple[Any, ...]], ordered: bool) -> tuple[bool, int]:
    if not gold_rows or not pred_rows:
        return (len(gold_rows) == len(pred_rows), 0)
    ng, np_ = len(gold_rows[0]), len(pred_rows[0])
    if np_ <= ng or len(gold_rows) != len(pred_rows):
        return (False, 0)
    if np_ > 12 or ng > 6:
        return (False, 0)
    for combo in itertools.combinations(range(np_), ng):
        projected = [tuple(r[i] for i in combo) for r in pred_rows]
        for perm in itertools.permutations(range(ng)):
            permuted = [tuple(r[i] for i in perm) for projected_row in projected for r in [projected_row]]
            if _canon(gold_rows, ordered) == _canon(permuted, ordered):
                return (True, np_ - ng)
    return (False, 0)


def soft_f1(gold_rows: list[tuple[Any, ...]], pred_rows: list[tuple[Any, ...]]) -> float:
    cg = Counter(gold_rows)
    cp = Counter(pred_rows)
    intersect = sum((cg & cp).values())
    tot_g = len(gold_rows)
    tot_p = len(pred_rows)
    if tot_g == 0 and tot_p == 0:
        return 1.0
    if tot_g == 0 or tot_p == 0:
        return 0.0
    prec = intersect / tot_p
    rec = intersect / tot_g
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


@dataclass
class SqlGradeResult:
    grade: str   # 'A' | 'B' | 'C' | 'D' | 'E' | 'F'
    reason: str
    ex: bool = False
    soft_f1: float = 0.0
    extra_cols: int = 0
    findings: list[PolicyFinding] = field(default_factory=list)
    failed_perturbations: list[str] = field(default_factory=list)


class SqlGradeEvaluator:
    """Evaluates candidate SQL using deterministic AST policy and A-F grading."""

    def __init__(self, catalog: PolicyCatalog | None = None, theta: float = DEFAULT_THETA_SOFT_F1) -> None:
        self.catalog = catalog or PolicyCatalog()
        self.guard = AstPolicyGuard(self.catalog)
        self.theta = theta

    def grade(
        self,
        gold_sql: str,
        pred_sql: str,
        execute_fn: Callable[[str], tuple[bool, list[str], list[tuple[Any, ...]], str]],
        perturb_runner: Callable[[str, str, bool], list[str]] | None = None,
        dialect: str = "sqlite",
    ) -> SqlGradeResult:
        """
        execute_fn: sql -> (ok, cols, rows, error_msg)
        """
        # 1. Static Policy Check (0 GPU)
        findings = self.guard.validate(pred_sql, dialect=dialect)
        if self.guard.is_blocked(findings):
            codes = {f.code for f in findings if f.severity == "block"}
            if codes & DANGEROUS_POLICY_CODES:
                return SqlGradeResult("F", f"Vi phạm chính sách an toàn/chi phí: {sorted(codes)}", findings=findings)
            return SqlGradeResult("E", f"Bị chặn trước khi thực thi: {sorted(codes)}", findings=findings)

        # 2. Execution
        g_ok, g_cols, g_rows, g_err = execute_fn(gold_sql)
        if not g_ok:
            return SqlGradeResult("E", f"Gold SQL lỗi thực thi: {g_err}")

        p_ok, p_cols, p_rows, p_err = execute_fn(pred_sql)
        if not p_ok:
            return SqlGradeResult("E", f"Candidate SQL lỗi thực thi: {p_err}", findings=findings)

        # Check ordered expectation
        try:
            tree = sqlglot.parse_one(gold_sql, dialect=dialect)
            ordered = bool(tree and tree.find(exp.Order))
        except Exception:
            ordered = False

        gr = norm_table(g_cols, g_rows)
        pr = norm_table(p_cols, p_rows)

        ex = exact_match(gr, pr, ordered)
        sub_ok, extra = (False, 0) if ex else subset_match(gr, pr, ordered)
        f1_score = 1.0 if ex else soft_f1(gr, pr)

        # 3. Perturbation testing (Check accidental correctness)
        failed_perturbs: list[str] = []
        if (ex or sub_ok) and perturb_runner is not None:
            failed_perturbs = perturb_runner(gold_sql, pred_sql, ordered)

        # 4. A-F Decision Tree
        if ex or sub_ok:
            if failed_perturbs:
                # Accidental match or silent error
                return SqlGradeResult(
                    grade="F",
                    reason=f"Sai ngầm - trượt kiểm thử nhiễu loạn: {failed_perturbs}",
                    ex=ex,
                    soft_f1=f1_score,
                    failed_perturbations=failed_perturbs,
                    findings=findings,
                )
            if ex:
                return SqlGradeResult(
                    grade="A",
                    reason="Đúng hoàn toàn (khớp gold và qua kiểm thử nhiễu loạn)",
                    ex=True,
                    soft_f1=1.0,
                    findings=findings,
                )
            # sub_ok
            return SqlGradeResult(
                grade="B",
                reason=f"Đúng kết quả, lệch hình thức: thừa {extra} cột",
                ex=False,
                soft_f1=f1_score,
                extra_cols=extra,
                findings=findings,
            )

        if f1_score >= self.theta:
            return SqlGradeResult(
                grade="C",
                reason=f"Đúng một phần (soft-F1={f1_score:.2f} >= {self.theta})",
                ex=False,
                soft_f1=f1_score,
                findings=findings,
            )

        return SqlGradeResult(
            grade="D",
            reason=f"Sai rõ ràng (soft-F1={f1_score:.2f} < {self.theta})",
            ex=False,
            soft_f1=f1_score,
            findings=findings,
        )
