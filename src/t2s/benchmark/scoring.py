import hashlib
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class EvaluationExecutionResult:
    ok: bool
    rows: list[tuple[Any, ...]]
    error: str | None = None


# Backward-compatible alias
GoldExecutionResult = EvaluationExecutionResult


def execute_evaluation_sql(
    sql: str,
    db_path: Path | str,
    timeout_seconds: int = 30,
    maximum_result_rows: int | None = None,
) -> EvaluationExecutionResult:
    resolved_path = Path(db_path).resolve()
    uri = f"file:{resolved_path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=timeout_seconds)
        try:
            connection.execute("PRAGMA query_only = ON")
            cursor = connection.cursor()
            cursor.execute(sql)
            if maximum_result_rows is not None:
                rows = cursor.fetchmany(maximum_result_rows)
            else:
                rows = cursor.fetchall()
            return EvaluationExecutionResult(ok=True, rows=rows)
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        return EvaluationExecutionResult(ok=False, rows=[], error=str(exc))


def execute_gold_sql(gold_sql: str, db_path: Path, maximum_result_rows: int | None = 50000) -> EvaluationExecutionResult:
    return execute_evaluation_sql(gold_sql, db_path, timeout_seconds=30, maximum_result_rows=maximum_result_rows)


def evaluate_candidate_vs_gold(
    candidate_sql: str,
    gold_sql: str,
    db_path: Path | str,
    timeout_seconds: int = 30,
    maximum_result_rows: int | None = None,
) -> tuple[bool, EvaluationExecutionResult, EvaluationExecutionResult]:
    """Symmetrically execute and score candidate SQL against gold SQL for benchmark evaluation."""
    cand_res = execute_evaluation_sql(
        candidate_sql,
        db_path,
        timeout_seconds=timeout_seconds,
        maximum_result_rows=maximum_result_rows,
    )
    gold_res = execute_evaluation_sql(
        gold_sql,
        db_path,
        timeout_seconds=timeout_seconds,
        maximum_result_rows=maximum_result_rows,
    )
    if not cand_res.ok or not gold_res.ok:
        return False, cand_res, gold_res
    correct = score_execution_accuracy(
        generated_rows=cand_res.rows,
        gold_rows=gold_res.rows,
        gold_sql=gold_sql,
    )
    return correct, cand_res, gold_res


def score_execution_accuracy(
    generated_rows: list[dict[str, Any]] | list[tuple[Any, ...]],
    gold_rows: list[tuple[Any, ...]],
    gold_sql: str,
) -> bool:
    predicted_rows = [
        tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in generated_rows
    ]
    if _query_requires_order(gold_sql):
        return _normalize_rows(predicted_rows) == _normalize_rows(gold_rows)
    return sorted(_normalize_rows(predicted_rows)) == sorted(_normalize_rows(gold_rows))


def _query_requires_order(sql: str) -> bool:
    try:
        parsed_expression = sqlglot.parse_one(sql, dialect="sqlite")
    except sqlglot.errors.SqlglotError:
        return False
    return parsed_expression.find(exp.Order) is not None


def _normalize_rows(rows: list[tuple[Any, ...]]) -> list[tuple[str, ...]]:
    return [tuple(_normalize_value(value) for value in row) for row in rows]


EMPTY_RESULT_FINGERPRINT = hashlib.sha256(b"").hexdigest()


def compute_result_fingerprint(
    rows: list[tuple[Any, ...]] | list[dict[str, Any]],
) -> str:
    """Deterministic sha256 fingerprint of a query result, shared by candidate and gold.

    Canonicalization contract:
    - Row order is preserved as returned by the executor. Two executions of the
      same query that return rows in different orders produce different fingerprints;
      operators compare *semantic* equivalence with :func:`score_execution_accuracy`.
    - Duplicate rows are preserved.
    - Cells are normalized via :func:`_normalize_value` (``<NULL>`` for NULL,
      ``"1"/"0"`` for booleans, ``Decimal.normalize`` for numerics, ``str(...)``
      otherwise).
    - Cell separator is ``\\x1f`` (unit separator, control byte unlikely to appear
      inside normalized cells); row separator is ``\\n``; payload is UTF-8.
    - Column names are NOT included: fingerprints compare result values only, so a
      candidate and a gold execution with different column aliases still match when
      their row contents match.
    - The dict-vs-tuple shape of the input is normalized: for dict rows, cell order
      follows ``row.values()`` (i.e. the executor's returned column order).

    Fingerprints are for reproducibility auditing, not scoring; A-F semantic
    audits still require the raw candidate SQL and gold reference.
    """
    tuple_rows: list[tuple[Any, ...]] = [
        tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in rows
    ]
    normalized_rows = _normalize_rows(tuple_rows)
    if not normalized_rows:
        return EMPTY_RESULT_FINGERPRINT
    payload = "\n".join("\x1f".join(row) for row in normalized_rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_value(value: Any) -> str:
    if value is None:
        return "<NULL>"
    if isinstance(value, bool):
        return "1" if value else "0"
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    normalized_decimal = decimal_value.normalize()
    if normalized_decimal == normalized_decimal.to_integral():
        try:
            return str(normalized_decimal.quantize(Decimal("1")))
        except InvalidOperation:
            return format(normalized_decimal, "f")
    return format(normalized_decimal, "f")


class GradeAF:
    A = "A"  # Exact Match
    B = "B"  # Practical / Semantic Match (extra column projection, deduplication differences)
    C = "C"  # Near Miss (partial overlap, limit/top-k difference, null ordering)
    D = "D"  # Divergent (wrong data / semantic error)
    F = "F"  # Failure (execution error, syntax error, safety rejection)


def evaluate_grade_af(
    cand_rows: list[tuple[Any, ...]] | list[dict[str, Any]] | None,
    gold_rows: list[tuple[Any, ...]] | None,
    execution_success: bool,
    strict_ex: bool,
) -> tuple[str, str]:
    """Grade a candidate query execution from A to F with explicit reasoning.

    Rubric:
    - Grade A (Exact Match):
      Execution succeeded and candidate results match gold results exactly (strict EX is True).
    - Grade B (Practical / Semantic Match):
      Execution succeeded. Gold rows can be found in candidate rows when considering superset of
      projected columns (extra descriptive columns) or DISTINCT deduplication variations,
      preserving row-level business correctness.
    - Grade C (Near Miss):
      Execution succeeded. Significant overlap (Jaccard similarity >= 0.5, or gold rows are a
      subset of candidate rows due to missing LIMIT/filter, or candidate rows are a subset of gold).
    - Grade D (Semantic Divergence):
      Execution succeeded, but produced divergent data (Jaccard similarity < 0.5 or 0 rows returned
      when gold has rows).
    - Grade F (Failure):
      SQL failed to execute or failed to generate.
    """
    if not execution_success or cand_rows is None:
        return GradeAF.F, "Execution or generation failed"

    if gold_rows is None:
        return GradeAF.F, "Gold reference execution failed or missing"

    if strict_ex:
        return GradeAF.A, "Exact match with gold reference"

    # Normalize rows to string tuples
    norm_cand = _normalize_rows(
        [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cand_rows]
    )
    norm_gold = _normalize_rows(gold_rows)

    if not norm_cand and not norm_gold:
        return GradeAF.A, "Both candidate and gold returned 0 rows"

    if not norm_cand and norm_gold:
        return GradeAF.D, "Candidate returned 0 rows while gold returned data"

    if norm_cand and not norm_gold:
        return GradeAF.D, "Candidate returned rows while gold returned 0 rows"

    # Check for deduplicated exact match (Grade B)
    unique_cand = set(norm_cand)
    unique_gold = set(norm_gold)
    if unique_cand == unique_gold:
        return GradeAF.B, f"Matches gold when deduplicated (cand: {len(norm_cand)} rows, gold: {len(norm_gold)} rows)"

    # Check for single scalar numeric match within practical tolerance (Grade B/C)
    if len(norm_cand) == 1 and len(norm_gold) == 1 and len(norm_cand[0]) == 1 and len(norm_gold[0]) == 1:
        c_raw = norm_cand[0][0]
        g_raw = norm_gold[0][0]
        try:
            c_num = float(c_raw)
            g_num = float(g_raw)
            denom = max(abs(g_num), abs(c_num), 1e-6)
            rel_diff = abs(c_num - g_num) / denom
            if rel_diff <= 0.02:
                return GradeAF.B, f"Practically identical scalar numeric result ({c_num:.4g} vs gold {g_num:.4g}, relative diff: {rel_diff:.2%})"
            # Check percentage ratio vs decimal (e.g. 0.45 vs 45%)
            if abs(c_num * 100 - g_num) / max(abs(g_num), 1e-6) <= 0.02:
                return GradeAF.B, f"Matches gold percentage as decimal ratio ({c_num:.4g} vs gold {g_num:.4g})"
            if abs(c_num - g_num * 100) / max(abs(c_num), 1e-6) <= 0.02:
                return GradeAF.B, f"Matches gold decimal ratio as percentage ({c_num:.4g} vs gold {g_num:.4g})"
            if rel_diff <= 0.10:
                return GradeAF.C, f"Near miss scalar numeric approximation ({c_num:.4g} vs gold {g_num:.4g}, relative diff: {rel_diff:.2%})"
        except (ValueError, TypeError):
            pass

    # Check for Column Superset Match (Grade B):
    # Candidate projected more columns (e.g. (School, Rate) vs gold (Rate,))
    cand_col_count = len(norm_cand[0]) if norm_cand else 0
    gold_col_count = len(norm_gold[0]) if norm_gold else 0

    if cand_col_count > gold_col_count and len(norm_cand) == len(norm_gold):
        import itertools
        col_indices = list(range(cand_col_count))
        matched_projection = False
        for combo in itertools.permutations(col_indices, gold_col_count):
            sub_cand = [tuple(row[i] for i in combo) for row in norm_cand]
            if sorted(sub_cand) == sorted(norm_gold):
                matched_projection = True
                break
        if matched_projection:
            return GradeAF.B, f"Candidate projected extra columns ({cand_col_count} vs gold {gold_col_count}) with identical core data"

    # Also check column superset when candidate or gold has duplicate rows
    if cand_col_count > gold_col_count and len(unique_cand) == len(unique_gold):
        import itertools
        col_indices = list(range(cand_col_count))
        matched_projection = False
        for combo in itertools.permutations(col_indices, gold_col_count):
            sub_cand_set = {tuple(row[i] for i in combo) for row in unique_cand}
            if sub_cand_set == unique_gold:
                matched_projection = True
                break
        if matched_projection:
            return GradeAF.B, f"Candidate projected extra columns ({cand_col_count} vs gold {gold_col_count}) with identical deduplicated core data"

    # Check Row Overlap (Jaccard similarity on string representations of cells or rows)
    # 1. Exact row set intersection (if column counts match)
    if cand_col_count == gold_col_count:
        intersection = unique_cand.intersection(unique_gold)
        union = unique_cand.union(unique_gold)
        jaccard = len(intersection) / len(union) if union else 0.0

        if jaccard >= 0.5:
            return GradeAF.C, f"Near miss: row overlap Jaccard similarity is {jaccard:.1%}"
        if unique_gold.issubset(unique_cand):
            return GradeAF.C, f"Near miss: gold rows ({len(unique_gold)}) are a strict subset of candidate ({len(unique_cand)})"
        if unique_cand.issubset(unique_gold) and len(unique_cand) > 0:
            return GradeAF.C, f"Near miss: candidate rows ({len(unique_cand)}) are a strict subset of gold ({len(unique_gold)})"

    # 2. Value-level set overlap (flat set of normalized cell values)
    cand_values = {val for row in norm_cand for val in row if val != "<NULL>"}
    gold_values = {val for row in norm_gold for val in row if val != "<NULL>"}
    if gold_values:
        val_intersection = cand_values.intersection(gold_values)
        val_jaccard = len(val_intersection) / len(cand_values.union(gold_values)) if (cand_values or gold_values) else 0.0
        val_recall = len(val_intersection) / len(gold_values)

        if val_recall >= 0.7 or val_jaccard >= 0.5:
            return GradeAF.C, f"Near miss: cell value recall is {val_recall:.1%}, Jaccard is {val_jaccard:.1%}"

    return GradeAF.D, "Semantic divergence: results do not align with gold data"

