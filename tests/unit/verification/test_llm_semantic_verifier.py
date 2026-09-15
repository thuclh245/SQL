from typing import Any
from unittest.mock import AsyncMock

import pytest

from t2s.solver.solver_response import StructuredChatResponse
from t2s.verification.contracts import (
    CheckStatus,
    VerificationDecision,
    VerificationInput,
)
from t2s.verification.llm_semantic_verifier import LlmSemanticVerifier


def _sample_valid_response_content(decision: str = "ACCEPT") -> dict[str, Any]:
    pass_chk = {
        "status": "PASS",
        "short_reason": "Verified",
        "question_evidence": "ev",
        "sql_evidence": "sql",
    }
    return {
        "projection": pass_chk,
        "aggregation_and_grain": pass_chk,
        "filters_and_values": pass_chk,
        "join_semantics": pass_chk,
        "ordering_and_limit": pass_chk,
        "null_semantics": pass_chk,
        "schema_reference": pass_chk,
        "decision": decision,
        "failed_checks": [],
        "unknown_checks": [],
        "confidence": 0.95,
    }


@pytest.mark.anyio
async def test_llm_verifier_successful_accept() -> None:
    mock_client = AsyncMock()
    mock_client.generate_structured_response.return_value = StructuredChatResponse(
        content=_sample_valid_response_content("ACCEPT"),
        model_name="gpt-5-mini",
        elapsed_ms=120,
    )

    verifier = LlmSemanticVerifier(chat_client=mock_client)
    inp = VerificationInput(
        question="List all schools in Alameda.",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE schools (name TEXT, county TEXT)",
        candidate_sql="SELECT name FROM schools WHERE county = 'Alameda';",
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.ACCEPT
    assert res.projection.status == CheckStatus.PASS
    assert len(res.failed_checks) == 0


@pytest.mark.anyio
async def test_llm_verifier_enforces_reject_on_failed_check() -> None:
    mock_client = AsyncMock()
    content = _sample_valid_response_content("ACCEPT")
    # Model said ACCEPT, but projection status is FAIL
    content["projection"]["status"] = "FAIL"
    content["projection"]["short_reason"] = "Missing required column"

    mock_client.generate_structured_response.return_value = StructuredChatResponse(
        content=content,
        model_name="gpt-5-mini",
        elapsed_ms=150,
    )

    verifier = LlmSemanticVerifier(chat_client=mock_client)
    inp = VerificationInput(
        question="What is the student name and GPA?",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE students (name TEXT, gpa REAL)",
        candidate_sql="SELECT name FROM students;",
    )
    res = await verifier.verify(inp)
    # Conservative enforcement forces REJECT when any check is FAIL
    assert res.decision == VerificationDecision.REJECT
    assert "projection" in res.failed_checks


@pytest.mark.anyio
async def test_llm_verifier_enforces_abstain_on_unknown_check() -> None:
    mock_client = AsyncMock()
    content = _sample_valid_response_content("ACCEPT")
    content["filters_and_values"]["status"] = "UNKNOWN"
    content["filters_and_values"]["short_reason"] = "Insufficient domain knowledge"

    mock_client.generate_structured_response.return_value = StructuredChatResponse(
        content=content,
        model_name="gpt-5-mini",
        elapsed_ms=130,
    )

    verifier = LlmSemanticVerifier(chat_client=mock_client)
    inp = VerificationInput(
        question="Which items are active?",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE items (id INT, status INT)",
        candidate_sql="SELECT id FROM items WHERE status = 1;",
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.ABSTAIN
    assert "filters_and_values" in res.unknown_checks


@pytest.mark.anyio
async def test_llm_verifier_fails_closed_on_provider_error() -> None:
    mock_client = AsyncMock()
    mock_client.generate_structured_response.side_effect = RuntimeError(
        "OpenAI connection timed out"
    )

    verifier = LlmSemanticVerifier(chat_client=mock_client)
    inp = VerificationInput(
        question="List all schools.",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE schools (id INT)",
        candidate_sql="SELECT id FROM schools;",
    )
    res = await verifier.verify(inp)
    # Fail-closed: returns ABSTAIN with error recorded, does not crash
    assert res.decision == VerificationDecision.ABSTAIN
    assert len(res.unknown_checks) == 7
    assert "Provider dependency failure" in res.projection.short_reason


@pytest.mark.anyio
async def test_llm_verifier_fails_closed_on_malformed_output() -> None:
    mock_client = AsyncMock()
    mock_client.generate_structured_response.return_value = StructuredChatResponse(
        content={"unexpected_key": 123},  # missing required fields
        model_name="gpt-5-mini",
        elapsed_ms=100,
    )

    verifier = LlmSemanticVerifier(chat_client=mock_client)
    inp = VerificationInput(
        question="List all schools.",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE schools (id INT)",
        candidate_sql="SELECT id FROM schools;",
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.ABSTAIN
    assert "Malformed verifier structured output" in res.projection.short_reason


def test_prompt_hash_computation() -> None:
    verifier = LlmSemanticVerifier(chat_client=AsyncMock())
    assert verifier.prompt_sha256 != ""
    assert len(verifier.prompt_sha256) == 64
