"""Shared builders for E05 scoring tests.

Everything here is GENERIC and synthetic (E05 §20): no benchmark-specific
questions, only tiny controlled fixtures that certify scorer semantics.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from t2s.benchmark.scoring import compute_result_fingerprint
from t2s.evaluation.scoring.protocols import CaseEvidence, ResultTable


def table(columns: tuple[str, ...], rows: list[tuple[Any, ...]]) -> ResultTable:
    return ResultTable(columns=columns, rows=tuple(rows))


def evidence(
    *,
    case_id: str = "case-1",
    replicate_id: str = "r1",
    question: str | None = "How many widgets?",
    candidate_sql: str | None = "SELECT 1",
    gold_sql: str | None = "SELECT 1",
    candidate_result: ResultTable | None = None,
    gold_result: ResultTable | None = None,
    db_path: str | None = None,
    with_fingerprints: bool = True,
) -> CaseEvidence:
    cand_fp = (
        compute_result_fingerprint(list(candidate_result.rows))
        if candidate_result is not None and with_fingerprints
        else None
    )
    gold_fp = (
        compute_result_fingerprint(list(gold_result.rows))
        if gold_result is not None and with_fingerprints
        else None
    )
    return CaseEvidence(
        case_id=case_id,
        replicate_id=replicate_id,
        db_id="synthetic",
        question=question,
        evidence_context="schema: t(a,b,c)",
        candidate_sql=candidate_sql,
        gold_sql=gold_sql,
        runtime_status="SUCCESS",
        candidate_execution_ok=candidate_result is not None,
        gold_execution_ok=gold_result is not None,
        candidate_result=candidate_result,
        gold_result=gold_result,
        candidate_fingerprint=cand_fp,
        gold_fingerprint=gold_fp,
        db_path=db_path,
    )


def make_sales_db(path: Path, rows: list[tuple[int, str, int]]) -> Path:
    """Create a tiny generic sales fixture: sales(id, region, amount)."""

    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sales(id INTEGER, region TEXT, amount INTEGER)")
    conn.executemany("INSERT INTO sales VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return path
