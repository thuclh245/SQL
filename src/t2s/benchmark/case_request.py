"""Dựng ``QueryRequest`` từ case benchmark; evidence chỉ đi qua lớp đánh giá."""

from typing import Literal

from t2s.contracts import QueryRequest

BenchmarkEvidenceMode = Literal["none", "inline", "structured"]


def build_query_request_from_benchmark_case(
    question: str,
    evidence: str | None,
    evidence_mode: BenchmarkEvidenceMode = "none",
) -> QueryRequest:
    """Build a request from a benchmark case, keeping evidence in the harness.

    Benchmark evidence is dataset-supplied context and reaches the solver only
    through this evaluation-layer function. Production requests construct
    ``QueryRequest`` themselves and leave ``evidence`` empty unless a governed
    source fills it, so no benchmark text can reach a production prompt.

    ``evidence_mode`` is explicit rather than implied because it changes what the
    model sees: ``inline`` reproduces the historical runs that appended evidence
    to the question text, while ``structured`` carries it as its own field for
    prompt versions that render an evidence block. Comparing the two is only
    meaningful if the choice is recorded per run.
    """
    if not evidence:
        return QueryRequest(question=question, database_dialect="sqlite")
    if evidence_mode == "none":
        return QueryRequest(question=question, database_dialect="sqlite")
    if evidence_mode == "structured":
        return QueryRequest(
            question=question,
            evidence=[evidence],
            database_dialect="sqlite",
        )
    return QueryRequest(
        question=f"{question}\n\nEvidence: {evidence}",
        database_dialect="sqlite",
    )
