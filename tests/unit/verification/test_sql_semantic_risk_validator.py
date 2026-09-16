import pytest
from pydantic import ValidationError

from t2s.verification.sql_semantic_risk_validator import (
    SqlSemanticRiskValidator,
    ValidationInput,
    ValidatorFamily,
)


def validate(question: str, sql: str):
    return SqlSemanticRiskValidator().validate(
        ValidationInput(question=question, candidate_sql=sql)
    )


def test_filter_contract_flags_unrequested_null_guard() -> None:
    result = validate(
        "What is the complete address of the school with the lowest excellence rate?",
        "SELECT s.Street FROM schools s JOIN satscores ss ON s.CDSCode = ss.cds "
        "WHERE ss.NumTstTakr IS NOT NULL ORDER BY ss.NumGE1500 / ss.NumTstTakr LIMIT 1",
    )

    assert "EXTRA_UNREQUESTED_NULL_OR_DENOMINATOR_FILTER" in {
        violation.code for violation in result.violations
    }
    assert result.is_high_risk


def test_aggregation_flags_percentage_without_division() -> None:
    result = validate(
        "What percentage of cards have no content warning?",
        "SELECT COUNT(*) FROM cards WHERE hasContentWarning = 0",
    )

    assert "PERCENTAGE_STRUCTURE_SUSPICIOUS" in {violation.code for violation in result.violations}


def test_projection_mismatch_for_rate_question() -> None:
    result = validate(
        "What is the eligible meal rate for the top 5 schools?",
        "SELECT school, free_count / enrollment AS rate FROM frpm LIMIT 5",
    )

    assert "EXTRA_ENTITY_COLUMN_FOR_RATE_QUESTION" in {
        violation.code for violation in result.violations
    }


def test_join_path_flags_cross_join_metric_mixing() -> None:
    result = validate(
        "List the number of schools for each city.",
        "SELECT c.city, c.n, t.total FROM city_counts c CROSS JOIN totals t",
    )

    assert "CROSS_JOIN_MIXES_INDEPENDENT_METRICS" in {
        violation.code for violation in result.violations
    }


def test_construction_flags_unbound_parameter() -> None:
    result = validate("List schools in a city.", "SELECT * FROM schools WHERE city = :city")

    assert "UNBOUND_BIND_PARAMETER" in {violation.code for violation in result.violations}


def test_correct_query_not_flagged() -> None:
    result = validate(
        "How many schools are in each city?",
        "SELECT City, COUNT(*) FROM schools GROUP BY City",
    )

    assert result.violations == []
    assert not result.is_high_risk


@pytest.mark.parametrize("field", ["gold_sql", "gold_answer", "gold_tables"])
def test_gold_leakage_fields_are_forbidden(field: str) -> None:
    payload = {
        "question": "How many schools are there?",
        "candidate_sql": "SELECT COUNT(*) FROM schools",
        field: "forbidden",
    }

    with pytest.raises(ValidationError):
        ValidationInput.model_validate(payload)


def test_deterministic_output() -> None:
    payload = ValidationInput(
        question="What percentage of cards have no content warning?",
        candidate_sql="SELECT COUNT(*) FROM cards",
    )
    validator = SqlSemanticRiskValidator()

    first = validator.validate(payload).model_dump(mode="json")
    second = validator.validate(payload).model_dump(mode="json")

    assert first == second


def test_family_error_is_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = SqlSemanticRiskValidator()

    def boom(*args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("boom")

    monkeypatch.setattr(validator, "_filter_violations", boom)
    result = validator.validate(
        ValidationInput(
            question="What percentage of cards have no content warning?",
            candidate_sql="SELECT COUNT(*) FROM cards",
        )
    )

    assert "VALIDATOR_FAMILY_INTERNAL_ERROR" in {violation.code for violation in result.violations}
    assert "PERCENTAGE_STRUCTURE_SUSPICIOUS" in {violation.code for violation in result.violations}


def test_family_can_be_evaluated_independently() -> None:
    payload = ValidationInput(
        question="List the number of schools for each city.",
        candidate_sql="SELECT c.city, c.n, t.total FROM city_counts c CROSS JOIN totals t",
    )

    result = SqlSemanticRiskValidator().validate(
        payload,
        families={ValidatorFamily.JOIN_PATH_RISK},
    )

    assert [violation.validator for violation in result.violations] == [
        ValidatorFamily.JOIN_PATH_RISK
    ]
