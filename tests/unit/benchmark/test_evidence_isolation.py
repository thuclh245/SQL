"""Benchmark evidence must stay inside the evaluation layer.

Dataset evidence is an answer-side hint. If it could reach a production request,
measured accuracy would depend on information no real caller supplies.
"""

from pathlib import Path

from t2s.benchmark.runtime_factory import build_query_request_from_benchmark_case
from t2s.contracts import GroundingContext, QueryRequest, TableContext
from t2s.contracts.grounding_context import ColumnContext
from t2s.solver import DirectSqlPromptBuilder

PROMPT_DIRECTORY = Path(__file__).resolve().parents[3] / "prompts" / "direct_sql"


def _grounding_context() -> GroundingContext:
    return GroundingContext(
        scope_id="scope",
        tables=[
            TableContext(
                fqn="svc.db.main.accounts",
                sql_identifier="accounts",
                columns=[ColumnContext(name="tier", data_type="text")],
            )
        ],
    )


def test_production_query_request_carries_no_evidence_by_default() -> None:
    """Nothing in the production path fills evidence implicitly."""
    assert QueryRequest(question="How many accounts?").evidence == []


def test_structured_mode_keeps_evidence_out_of_the_question_text() -> None:
    request = build_query_request_from_benchmark_case(
        question="How many accounts?",
        evidence="tier is stored as a short code",
        evidence_mode="structured",
    )

    assert request.question == "How many accounts?"
    assert request.evidence == ["tier is stored as a short code"]


def test_inline_mode_reproduces_the_historical_concatenation() -> None:
    """Preserved verbatim so earlier runs stay comparable."""
    request = build_query_request_from_benchmark_case(
        question="How many accounts?",
        evidence="tier is stored as a short code",
        evidence_mode="inline",
    )

    assert request.evidence == []
    assert request.question.endswith("Evidence: tier is stored as a short code")


def test_case_without_evidence_produces_a_clean_request() -> None:
    request = build_query_request_from_benchmark_case(question="How many accounts?", evidence=None)

    assert request.question == "How many accounts?"
    assert request.evidence == []


def test_prompt_renders_evidence_only_when_the_request_supplies_it() -> None:
    builder = DirectSqlPromptBuilder(prompt_directory=PROMPT_DIRECTORY, prompt_version="v003")

    without_evidence = builder.build_solver_messages(
        query_request=QueryRequest(question="How many accounts?"),
        grounding_context=_grounding_context(),
        target_dialect="sqlite",
    )[1]["content"]
    with_evidence = builder.build_solver_messages(
        query_request=QueryRequest(
            question="How many accounts?",
            evidence=["tier is stored as a short code"],
        ),
        grounding_context=_grounding_context(),
        target_dialect="sqlite",
    )[1]["content"]

    assert "tier is stored as a short code" not in without_evidence
    assert "tier is stored as a short code" in with_evidence
    # Evidence is a block of its own, never folded into the question.
    assert "<user_question>\nHow many accounts?\n</user_question>" in with_evidence


def test_value_bindings_render_with_database_spelling(tmp_path: Path) -> None:
    from t2s.contracts.grounding_context import ValueBinding

    builder = DirectSqlPromptBuilder(prompt_directory=PROMPT_DIRECTORY, prompt_version="v003")
    context = _grounding_context()
    context.value_bindings = [
        ValueBinding(
            phrase="ENTERPRISE",
            column_fqn="svc.db.main.accounts.tier",
            value="enterprise",
            match_type="case_insensitive",
            evidence_score=0.9,
        )
    ]

    rendered = builder.build_solver_messages(
        query_request=QueryRequest(question="How many ENTERPRISE accounts?"),
        grounding_context=context,
        target_dialect="sqlite",
    )[1]["content"]

    assert "'enterprise'" in rendered
    assert "svc.db.main.accounts.tier" in rendered


def test_empty_value_bindings_still_produce_a_valid_prompt() -> None:
    builder = DirectSqlPromptBuilder(prompt_directory=PROMPT_DIRECTORY, prompt_version="v003")

    messages = builder.build_solver_messages(
        query_request=QueryRequest(question="How many accounts?"),
        grounding_context=_grounding_context(),
        target_dialect="sqlite",
    )

    assert messages[0]["content"]
    assert "Grounded values observed in the database:" in messages[1]["content"]
