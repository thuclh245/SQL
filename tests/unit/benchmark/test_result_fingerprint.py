"""Determinism and canonicalization tests for :func:`compute_result_fingerprint`.

Fingerprints must be:
- stable across repeated evaluations of the same rows,
- shared implementation between candidate and gold rows,
- sensitive to duplicate rows (scorer semantics can require it),
- insensitive to dict-vs-tuple input shape,
- deterministic across NULL / boolean / numeric normalization.

Fixtures use generic synthetic identifiers (customers, orders, departments).
No benchmark question, gold SQL, or protected literal is used.
"""

from decimal import Decimal

from t2s.benchmark.scoring import (
    EMPTY_RESULT_FINGERPRINT,
    compute_result_fingerprint,
)


def test_fingerprint_is_deterministic_across_repeated_calls() -> None:
    rows = [("alice", 3), ("bob", 5), ("carol", 8)]
    assert compute_result_fingerprint(rows) == compute_result_fingerprint(rows)


def test_fingerprint_matches_between_candidate_and_gold_when_rows_match() -> None:
    candidate_rows = [{"customer_name": "alice", "total": 3}]
    gold_rows = [("alice", 3)]
    # Candidate emits dict rows (runtime shape); gold emits tuples (executor shape).
    # Both must fingerprint identically when the values match, because a shared
    # fingerprint powers reproducibility comparisons across the two sides.
    assert compute_result_fingerprint(candidate_rows) == compute_result_fingerprint(gold_rows)


def test_fingerprint_preserves_duplicate_rows() -> None:
    with_duplicates = [("alice", 1), ("alice", 1)]
    deduplicated = [("alice", 1)]
    assert compute_result_fingerprint(with_duplicates) != compute_result_fingerprint(deduplicated)


def test_fingerprint_distinguishes_row_order() -> None:
    forward = [("alice", 1), ("bob", 2)]
    reversed_ = [("bob", 2), ("alice", 1)]
    assert compute_result_fingerprint(forward) != compute_result_fingerprint(reversed_)


def test_fingerprint_normalizes_null_and_boolean() -> None:
    a = [(None, True), (None, False)]
    b = [("<NULL>", "1"), ("<NULL>", "0")]
    assert compute_result_fingerprint(a) == compute_result_fingerprint(b)


def test_fingerprint_normalizes_numeric_representation() -> None:
    a = [(Decimal("3.0"), 1)]
    b = [(3, 1)]
    c = [("3", 1)]
    assert compute_result_fingerprint(a) == compute_result_fingerprint(b)
    assert compute_result_fingerprint(b) == compute_result_fingerprint(c)


def test_fingerprint_on_empty_result_is_stable() -> None:
    assert compute_result_fingerprint([]) == EMPTY_RESULT_FINGERPRINT
    assert compute_result_fingerprint([]) == compute_result_fingerprint([])


def test_fingerprint_sensitive_to_column_reordering_within_row() -> None:
    # Column order is part of the result contract; a row (customer, total) is
    # not the same as (total, customer).
    row_a = [("alice", 3)]
    row_b = [(3, "alice")]
    assert compute_result_fingerprint(row_a) != compute_result_fingerprint(row_b)
