"""Unit and architectural tests for residual heuristics, governance enforcement, and n8n boundaries.

Enforces:
1. Governance policy enforced in code: validator_mode='enforce' requires explicit authorization.
2. Shadow mode invariant: semantic heuristics never block runtime execution in shadow mode.
3. Metamorphic paraphrase tests: structural invariants are invariant to language,
   whereas linguistic heuristics diverge.
4. Mutation tests: structural invariants are invariant to synthetic table/column renaming.
5. n8n boundary security: DTO boundary forbids raw SQL injection, AST validator blocks mutations.
"""

import pytest
from pydantic import ValidationError

from t2s.configuration import Settings
from t2s.contracts import QueryRequest
from t2s.errors import UnsafeSqlError
from t2s.runtime.runtime_contracts import ValidatorMode, ValidatorRuntimeAction
from t2s.runtime.sql_risk_controller import SqlRiskController
from t2s.verification import (
    SqlAstParser,
    SqlSafetyValidator,
    SqlSemanticRiskValidator,
    ValidationInput,
)


# 1. Governance Enforced in Code
def test_governance_enforcement_blocks_enforce_mode_without_authorization() -> None:
    """Settings must fail closed if validator_mode='enforce' without authorization."""
    with pytest.raises(ValueError, match="PRODUCTION_ENFORCEMENT_AUTHORIZED=False"):
        Settings(validator_mode="enforce", production_enforcement_authorized=False)


def test_governance_enforcement_permits_enforce_mode_with_explicit_authorization() -> None:
    """Settings must allow validator_mode='enforce' only when authorized."""
    settings = Settings(validator_mode="enforce", production_enforcement_authorized=True)
    assert settings.validator_mode == "enforce"
    assert settings.production_enforcement_authorized is True


def test_governance_default_mode_is_shadow() -> None:
    """Default validator mode must be 'shadow' and authorization must default to False."""
    settings = Settings()
    assert settings.validator_mode == "shadow"
    assert settings.production_enforcement_authorized is False


# 2. Shadow Mode Invariant
def test_shadow_mode_never_blocks_even_on_heuristic_violations() -> None:
    """In shadow mode, SqlRiskController must never return NEEDS_SEMANTIC_REVIEW."""
    controller = SqlRiskController()
    payload = ValidationInput(
        question="What percentage of orders are high value?",
        candidate_sql="SELECT COUNT(*) FROM orders",
    )
    outcome = controller.evaluate(payload, mode=ValidatorMode.SHADOW)
    assert outcome.invoked is True
    assert outcome.effective_runtime_action == ValidatorRuntimeAction.ACCEPT
    assert outcome.shadow_divergence is True


# 3. Metamorphic Tests: Structural Invariance vs Linguistic Divergence
def test_metamorphic_structural_rule_is_language_invariant() -> None:
    """Structural rules must flag identically regardless of question language."""
    validator = SqlSemanticRiskValidator()
    sql_unbound = "SELECT * FROM users WHERE status = :status_code"
    sql_empty_in = "SELECT * FROM users WHERE id IN ()"

    questions = [
        "What users have active status?",
        "Show me all users filtered by status please.",
        "Những người dùng nào đang có trạng thái kích hoạt?",
    ]

    for q in questions:
        res_unbound = validator.validate(ValidationInput(question=q, candidate_sql=sql_unbound))
        codes_unbound = {v.code for v in res_unbound.violations}
        assert "UNBOUND_BIND_PARAMETER" in codes_unbound, f"Failed for question: {q}"

        res_empty = validator.validate(ValidationInput(question=q, candidate_sql=sql_empty_in))
        codes_empty = {v.code for v in res_empty.violations}
        assert "EMPTY_IN_CLAUSE" in codes_empty, f"Failed for question: {q}"


def test_metamorphic_linguistic_heuristic_diverges_on_vietnamese() -> None:
    """Demonstrates that English regex heuristics fail to detect violations in Vietnamese.

    Proves these rules are linguistic heuristics (Category C / D) and must remain SHADOW-only.
    """
    validator = SqlSemanticRiskValidator()
    sql = "SELECT COUNT(*) FROM payments WHERE amount > 100"

    q_english = "What percentage of payments are high value?"
    res_en = validator.validate(ValidationInput(question=q_english, candidate_sql=sql))
    en_violations = {v.code for v in res_en.violations}
    assert "PERCENTAGE_STRUCTURE_SUSPICIOUS" in en_violations

    q_vietnamese = "Tỷ lệ phần trăm các khoản thanh toán có giá trị cao là bao nhiêu?"
    res_vi = validator.validate(ValidationInput(question=q_vietnamese, candidate_sql=sql))
    vi_violations = {v.code for v in res_vi.violations}
    # Linguistic regex does NOT match Vietnamese, proving it is an English-specific heuristic!
    assert "PERCENTAGE_STRUCTURE_SUSPICIOUS" not in vi_violations


# 4. Mutation Tests for Hidden Literals
def test_mutation_table_and_column_names_preserve_structural_invariants() -> None:
    """Renaming tables and columns to synthetic Greek names must preserve structural checks."""
    validator = SqlSemanticRiskValidator()

    # Original business names
    sql_orig = "SELECT a.val, b.val FROM orders a CROSS JOIN customers b"
    res_orig = validator.validate(ValidationInput(question="List metrics", candidate_sql=sql_orig))
    assert "CROSS_JOIN_MIXES_INDEPENDENT_METRICS" in {v.code for v in res_orig.violations}

    # Mutated synthetic names
    sql_mutated = (
        "SELECT a.synthetic_c1, b.synthetic_c2 FROM entity_alpha a CROSS JOIN entity_beta b"
    )
    res_mut = validator.validate(
        ValidationInput(question="List metrics", candidate_sql=sql_mutated)
    )
    assert "CROSS_JOIN_MIXES_INDEPENDENT_METRICS" in {v.code for v in res_mut.violations}


# 5. n8n Boundary Security
def test_n8n_request_dto_strictly_forbids_raw_sql() -> None:
    """QueryRequest must reject extra fields like raw_sql or overrides from n8n callers."""
    with pytest.raises(ValidationError):
        QueryRequest.model_validate(
            {
                "question": "How many orders?",
                "raw_sql": "DROP TABLE users;",
            }
        )


def test_n8n_path_safety_validator_blocks_mutations() -> None:
    """SqlSafetyValidator must block DML and DDL mutations that an external caller might attempt."""
    parser = SqlAstParser()
    safety = SqlSafetyValidator()

    mutations = [
        "DROP TABLE customers",
        "DELETE FROM orders WHERE id = 1",
        "UPDATE accounts SET balance = 0",
        "INSERT INTO audit_log VALUES (1)",
        "ALTER TABLE users ADD COLUMN is_admin BOOLEAN",
    ]

    for sql in mutations:
        parsed = parser.parse_single_statement(sql=sql, dialect="postgres")
        with pytest.raises(UnsafeSqlError):
            safety.validate_read_only_sql(parsed)
