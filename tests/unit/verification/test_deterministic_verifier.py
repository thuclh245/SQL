import pytest

from t2s.verification.contracts import (
    CheckStatus,
    VerificationDecision,
    VerificationInput,
)
from t2s.verification.deterministic_verifier import DeterministicSqlVerifier


@pytest.mark.anyio
async def test_deterministic_verifier_accepts_valid_query() -> None:
    verifier = DeterministicSqlVerifier()
    inp = VerificationInput(
        question="List the names of all schools in Alameda.",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE schools (school_name TEXT, county TEXT)",
        candidate_sql="SELECT school_name FROM schools WHERE county = 'Alameda';",
        authorized_tables=["schools"],
        authorized_columns={"schools": ["school_name", "county"]},
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.ACCEPT
    assert res.schema_reference.status == CheckStatus.PASS
    assert res.aggregation_and_grain.status == CheckStatus.PASS
    assert len(res.failed_checks) == 0


@pytest.mark.anyio
async def test_deterministic_verifier_detects_unauthorized_table() -> None:
    verifier = DeterministicSqlVerifier()
    inp = VerificationInput(
        question="List all user names.",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE users (name TEXT)",
        candidate_sql="SELECT name FROM passwords;",
        authorized_tables=["users"],
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.REJECT
    assert res.schema_reference.status == CheckStatus.FAIL
    assert "schema_reference" in res.failed_checks
    assert "passwords" in res.schema_reference.short_reason


@pytest.mark.anyio
async def test_deterministic_verifier_detects_unknown_column() -> None:
    verifier = DeterministicSqlVerifier()
    inp = VerificationInput(
        question="List schools.",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE schools (id INT, name TEXT)",
        candidate_sql="SELECT secret_ssn FROM schools;",
        authorized_tables=["schools"],
        authorized_columns={"schools": ["id", "name"]},
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.REJECT
    assert res.schema_reference.status == CheckStatus.FAIL
    assert "secret_ssn" in res.schema_reference.short_reason


@pytest.mark.anyio
async def test_deterministic_verifier_detects_missing_aggregation_for_count() -> None:
    verifier = DeterministicSqlVerifier()
    inp = VerificationInput(
        question="How many students are enrolled in the school?",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE students (id INT, name TEXT)",
        candidate_sql="SELECT name FROM students;",
        authorized_tables=["students"],
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.REJECT
    assert res.aggregation_and_grain.status == CheckStatus.FAIL
    assert "aggregation_and_grain" in res.failed_checks


@pytest.mark.anyio
async def test_deterministic_verifier_detects_missing_order_for_extrema() -> None:
    verifier = DeterministicSqlVerifier()
    inp = VerificationInput(
        question="What is the highest test score in the class?",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE scores (student_id INT, score INT)",
        candidate_sql="SELECT score FROM scores;",
        authorized_tables=["scores"],
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.REJECT
    assert res.ordering_and_limit.status == CheckStatus.FAIL
    assert "ordering_and_limit" in res.failed_checks


@pytest.mark.anyio
async def test_deterministic_verifier_handles_syntax_error_fail_closed() -> None:
    verifier = DeterministicSqlVerifier()
    inp = VerificationInput(
        question="What are the schools?",
        evidence="",
        dialect="sqlite",
        authorized_schema="TABLE schools (id INT)",
        candidate_sql="SELECT FROM WHERE ;",
        authorized_tables=["schools"],
    )
    res = await verifier.verify(inp)
    assert res.decision == VerificationDecision.REJECT
    assert "schema_reference" in res.failed_checks
