"""E04 <-> E05 integration path (E05 §1, §14).

E04's ``CaseRunRecord`` declares that it structurally satisfies the E05
consumption protocol :class:`t2s.evaluation.scoring.protocols.CaseRunEvidence`
(``e05.case_evidence.v1``). These tests verify that an E04 record can be scored
directly by the E05 deterministic scorer and semantic auditor with no adapter,
and that the missing-evidence policy (candidate SQL absent => F) holds through
the real record type.

The E04 package is a parallel WIP track; when it is absent (an E05-only
checkout) these tests skip rather than fail, mirroring the repo's
optional-artifact test convention.
"""

from __future__ import annotations

import pytest

contract = pytest.importorskip("t2s.benchmark.case_evidence.contract")

from t2s.evaluation.scoring.deterministic import score_case_deterministic  # noqa: E402
from t2s.evaluation.scoring.protocols import CaseRunEvidence  # noqa: E402
from t2s.evaluation.scoring.semantic_audit import deterministic_semantic_audit  # noqa: E402
from t2s.evaluation.scoring.taxonomy import Grade  # noqa: E402
from t2s.evaluation.scoring.versions import CONSUMED_CASE_RECORD_PROTOCOL_VERSION  # noqa: E402


def _record(**overrides: object) -> object:
    base = dict(
        experiment_id="exp1",
        run_id="run1",
        replicate_id="r1",
        case_id="c1",
        db_id="synthetic",
        question="How many widgets?",
        candidate_sql="SELECT 1",
        runtime_status="SUCCESS",
        candidate_execution_ok=True,
        gold_execution_ok=True,
        candidate_fingerprint="deadbeef",
        gold_fingerprint="deadbeef",
    )
    base.update(overrides)
    return contract.CaseRunRecord(**base)


def test_e04_version_string_matches_e05_consumed_protocol() -> None:
    assert contract.E05_CONSUMED_PROTOCOL_VERSION == CONSUMED_CASE_RECORD_PROTOCOL_VERSION


def test_e04_record_is_structural_case_run_evidence() -> None:
    record = _record()
    assert isinstance(record, CaseRunEvidence)


def test_e04_record_scores_directly_grade_a_on_fingerprint_match() -> None:
    record = _record()
    scoring = score_case_deterministic(record)  # type: ignore[arg-type]
    assert scoring.strict_ex is True
    assert scoring.fingerprint_match is True
    audit = deterministic_semantic_audit(record, scoring)  # type: ignore[arg-type]
    assert audit.classification is Grade.A


def test_e04_record_missing_candidate_sql_is_grade_f() -> None:
    record = _record(candidate_sql=None, candidate_fingerprint=None)
    scoring = score_case_deterministic(record)  # type: ignore[arg-type]
    assert "candidate_sql_missing" in scoring.determination_blockers
    audit = deterministic_semantic_audit(record, scoring)  # type: ignore[arg-type]
    assert audit.classification is Grade.F
