"""Benchmark-side adapter for the convention checks.

The checks themselves live in ``t2s.verified_context.conventions`` so that the
benchmark scripts (validator, builder, audit) and the runtime verifier use the
same code.  This module keeps the case-dict interface the scripts were written
against.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conventions" / "conventions.yaml"
sys.path.insert(0, str(ROOT.parents[2] / "src"))

from t2s.verified_context import conventions as _conv  # noqa: E402

CHECKS = _conv.CHECKS
is_executable = _conv.is_executable
parse = _conv.parse
referenced_tables = _conv.referenced_tables
run_check = _conv.run_check


def load_registry() -> dict:
    return _conv.load_registry(REGISTRY)


def applies(conv: dict, case: dict, sql: str | None = None) -> bool:
    """Applicability from the case's question and declared tables, never from gold.
    Without SQL, an "if you use X" rule (sql_references) does not apply to a case."""
    if sql is None and (conv.get("applies_when") or {}).get("sql_references"):
        return False
    question = " ".join(case.get(k, "") or "" for k in ("question_explicit", "question_natural", "question"))
    return _conv.applies(conv, question=question, tables=case.get("required_tables", []), sql=sql)
