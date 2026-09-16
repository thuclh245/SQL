import pytest
from pydantic import ValidationError

from t2s.evaluation.verifier_evaluation import VerifierCandidateRecord
from t2s.verification.contracts import (
    CheckStatus,
    SemanticCheckResult,
    VerificationDecision,
    VerificationInput,
    VerificationResult,
)
from t2s.verification.llm_semantic_verifier import build_verification_result_json_schema


def test_verification_input_serialization() -> None:
    inp = VerificationInput(
        question="Which school had the highest SAT score?",
        evidence="SAT refers to sat_avg",
        dialect="sqlite",
        authorized_schema="TABLE schools (id INT, sat_avg INT)",
        candidate_sql="SELECT id FROM schools ORDER BY sat_avg DESC LIMIT 1;",
        authorized_tables=["schools"],
    )
    serialized = inp.model_dump()
    assert serialized["question"] == "Which school had the highest SAT score?"
    assert serialized["dialect"] == "sqlite"
    assert "schools" in serialized["authorized_tables"]
    # Verify no gold keys exist in input
    assert "gold_sql" not in serialized
    assert "execution_correct" not in serialized


def test_gold_isolation_in_candidate_record() -> None:
    record = VerifierCandidateRecord(
        candidate_id="p7b_ctrl_bird_100",
        source_run_id="p7b_control_r1",
        case_id="bird_100",
        db_id="california_schools",
        question="How many schools?",
        evidence="",
        dialect="sqlite",
        grounding_context={
            "formatted_schema": "TABLE schools (id INT)",
            "authorized_tables": ["schools"],
        },
        candidate_sql="SELECT COUNT(*) FROM schools;",
        runtime_origin="EXECUTED",
        evaluator_correctness_label=True,
        gold_sql="SELECT COUNT(id) FROM schools;",
    )
    # Convert to input for verifier
    verifier_input = record.to_verification_input()

    input_dict = verifier_input.model_dump()
    assert "gold_sql" not in input_dict
    assert "evaluator_correctness_label" not in input_dict
    assert "runtime_origin" not in input_dict
    assert not hasattr(verifier_input, "gold_sql")
    assert not hasattr(verifier_input, "evaluator_correctness_label")


def test_verification_result_strict_schema() -> None:
    schema_envelope = build_verification_result_json_schema()
    assert schema_envelope["name"] == "verification_result"
    assert schema_envelope["strict"] is True

    schema = schema_envelope["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())

    # Check that $defs also enforce additionalProperties: False and required
    for _def_name, def_schema in schema.get("$defs", {}).items():
        if def_schema.get("type") == "object":
            assert def_schema["additionalProperties"] is False
            assert set(def_schema["required"]) == set(def_schema["properties"].keys())


def test_verification_decision_parsing() -> None:
    pass_check = SemanticCheckResult(status=CheckStatus.PASS, short_reason="OK")
    res = VerificationResult(
        projection=pass_check,
        aggregation_and_grain=pass_check,
        filters_and_values=pass_check,
        join_semantics=pass_check,
        ordering_and_limit=pass_check,
        null_semantics=pass_check,
        schema_reference=pass_check,
        decision=VerificationDecision.ACCEPT,
    )
    assert res.decision == VerificationDecision.ACCEPT
    assert res.decision.value == "ACCEPT"

    fail_check = SemanticCheckResult(status=CheckStatus.FAIL, short_reason="Wrong column")
    res_fail = VerificationResult(
        projection=fail_check,
        aggregation_and_grain=pass_check,
        filters_and_values=pass_check,
        join_semantics=pass_check,
        ordering_and_limit=pass_check,
        null_semantics=pass_check,
        schema_reference=pass_check,
        decision=VerificationDecision.REJECT,
        failed_checks=["projection"],
    )
    assert res_fail.decision == VerificationDecision.REJECT
    assert res_fail.failed_checks == ["projection"]


def test_invalid_decision_fails_validation() -> None:
    pass_check = SemanticCheckResult(status=CheckStatus.PASS, short_reason="OK")
    with pytest.raises(ValidationError):
        VerificationResult(
            projection=pass_check,
            aggregation_and_grain=pass_check,
            filters_and_values=pass_check,
            join_semantics=pass_check,
            ordering_and_limit=pass_check,
            null_semantics=pass_check,
            schema_reference=pass_check,
            decision="MAYBE",  # type: ignore[arg-type]
        )
