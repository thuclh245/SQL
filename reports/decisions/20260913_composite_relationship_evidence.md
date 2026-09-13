# Decision

## Problem
P3 grounding must preserve declared composite foreign keys so P4 receives every join column needed for SQL generation.

## Existing Contract
`RelationshipEvidence` represented joins with scalar `from_column` and `to_column` fields. That was sufficient for single-column FKs but lossy for composite FKs from P2.

## Proposed Change
Replace scalar relationship fields with `from_columns: list[str]` and `to_columns: list[str]`. Keep read-only `from_column` and `to_column` properties for simple single-column access.

## Why Current Contract Fails
P2 stores `CatalogForeignKey.from_column_names` and `to_column_names` as lists. Collapsing them into a single string would silently drop part of a composite join.

## Alternatives Considered
- Serialize composite keys into `evidence_summary`: rejected because P4 prompt construction needs structured join columns.
- Add a second composite relationship model: rejected because parallel relationship contracts would invite divergence.

## Migration Impact
P4 prompt construction now prints `from_columns` and `to_columns`. Existing single-column fixture relationships use one-item lists.

## Test Evidence
- `tests/unit/grounding/test_grounding_baseline.py::test_composite_fk_relationship_evidence_is_lossless`
- `tests/unit/solver/test_prompt_builder.py`
- Full suite: `.venv/bin/python -m pytest -vv` -> 93 passed.

## Decision Needed
Adopt list-based relationship evidence as the shared P3/P4 grounding contract.
