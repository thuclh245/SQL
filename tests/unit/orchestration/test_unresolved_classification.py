"""Structural classification of solver-reported uncertainty."""

from t2s.contracts import (
    ColumnContext,
    GenerationTrace,
    GroundingContext,
    GroundingIssue,
    SqlCandidate,
    TableContext,
)
from t2s.orchestration.unresolved_classification import (
    UnresolvedClassification,
    UnresolvedClassifier,
)


def _context(
    sql_identifiers: list[str] | None = None,
    unresolved: list[GroundingIssue] | None = None,
) -> GroundingContext:
    return GroundingContext(
        scope_id="scope",
        tables=[
            TableContext(
                fqn=f"svc.db.main.{identifier}",
                sql_identifier=identifier,
                columns=[ColumnContext(name="id", data_type="integer")],
            )
            for identifier in (sql_identifiers or ["accounts"])
        ],
        unresolved=unresolved or [],
    )


def _candidate(
    referenced_tables: list[str] | None = None,
    unresolved: list[str] | None = None,
) -> SqlCandidate:
    return SqlCandidate(
        sql="SELECT 1",
        dialect="postgres",
        referenced_tables=referenced_tables or ["accounts"],
        unresolved=unresolved or [],
        generation_trace=GenerationTrace(
            run_id="r", model_name="m", prompt_version="v001"
        ),
    )


def test_candidate_with_tie_break_caveat_remains_viable() -> None:
    """The archetypal false abstention: a note about ordering, not a blocker."""
    assessment = UnresolvedClassifier().assess_candidate(
        _context(),
        _candidate(unresolved=["No explicit tie-breaker rule was supplied for equal values."]),
    )

    assert assessment.classification == UnresolvedClassification.NON_BLOCKING_CAVEAT
    assert assessment.is_candidate_viable is True
    assert assessment.has_solver_unresolved_notes is True


def test_candidate_with_no_notes_is_viable() -> None:
    assessment = UnresolvedClassifier().assess_candidate(_context(), _candidate())

    assert assessment.is_candidate_viable is True
    assert assessment.has_solver_unresolved_notes is False


def test_candidate_referencing_ungrounded_relation_is_not_viable() -> None:
    assessment = UnresolvedClassifier().assess_candidate(
        _context(sql_identifiers=["accounts"]),
        _candidate(referenced_tables=["accounts", "never_grounded"]),
    )

    assert assessment.classification == UnresolvedClassification.GROUNDING_INSUFFICIENT
    assert assessment.is_candidate_viable is False
    assert "referenced_but_not_grounded: never_grounded" in assessment.evidence


def test_unresolved_sql_identifier_blocks_regardless_of_candidate() -> None:
    assessment = UnresolvedClassifier().assess_candidate(
        _context(
            unresolved=[
                GroundingIssue(
                    code="unresolved_sql_identifier",
                    message="Relation has no executable SQL identifier.",
                )
            ]
        ),
        _candidate(),
    )

    assert assessment.classification == UnresolvedClassification.GROUNDING_INSUFFICIENT
    assert assessment.is_candidate_viable is False


def test_missing_candidate_is_structural_uncertainty() -> None:
    assessment = UnresolvedClassifier().assess_candidate(_context(), None)

    assert assessment.classification == UnresolvedClassification.STRUCTURAL_UNCERTAINTY
    assert assessment.is_candidate_viable is False


def test_reference_matching_the_catalog_fqn_is_accepted() -> None:
    """Models sometimes echo the catalog FQN rather than the SQL identifier."""
    assessment = UnresolvedClassifier().assess_candidate(
        _context(sql_identifiers=["accounts"]),
        _candidate(referenced_tables=["svc.db.main.accounts"]),
    )

    assert assessment.is_candidate_viable is True


def test_classification_ignores_the_wording_of_the_note() -> None:
    """Two candidates differing only in prose must be classified identically.

    This is the guard against reintroducing phrase matching: alarming wording on a
    structurally sound statement must not change the verdict.
    """
    classifier = UnresolvedClassifier()
    mild = classifier.assess_candidate(_context(), _candidate(unresolved=["Minor note."]))
    alarming = classifier.assess_candidate(
        _context(),
        _candidate(unresolved=["It is impossible to determine this; no column exists."]),
    )

    assert mild.classification == alarming.classification
    assert mild.is_candidate_viable == alarming.is_candidate_viable is True


def test_strict_abstention_posture_blocks_on_any_caveat() -> None:
    """The opposite posture, used where an unreviewed answer is the costlier risk."""
    from t2s.orchestration.escalation_policy import EscalationPolicy

    strict = EscalationPolicy(release_candidates_with_caveats=False)
    permissive = EscalationPolicy(release_candidates_with_caveats=True)
    context = _context()
    candidate = _candidate(unresolved=["No explicit tie-breaker rule was supplied."])

    assert strict.assess_candidate_viability(context, candidate).is_candidate_viable is False
    assert permissive.assess_candidate_viability(context, candidate).is_candidate_viable is True


def test_strict_abstention_still_accepts_a_candidate_with_no_caveats() -> None:
    from t2s.orchestration.escalation_policy import EscalationPolicy

    strict = EscalationPolicy(release_candidates_with_caveats=False)

    assert strict.assess_candidate_viability(_context(), _candidate()).is_candidate_viable is True
