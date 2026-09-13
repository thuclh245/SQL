# Phase Exit Report - P3 Grounding Baseline

## Objective
Implement a deterministic baseline that converts `QueryRequest` plus authorized metadata scope into a compact `GroundingContext` for P4 without generating SQL.

## Initial Audit
- P2 catalog identity is stable through `table_fqn` and hydration via `CatalogPort`.
- P2 relationship lookup is bidirectional and stores composite FK column lists.
- P4 consumes `GroundingContext` and requires executable `sql_identifier`.
- Existing `RelationshipEvidence` was scalar and required a contract note for composite FK support.

## Architecture
- `SchemaRetriever` retrieves explicit `SchemaCandidate` objects with score and matched fields.
- `RetrievalRanker` aggregates table and column candidates into ranked table candidates.
- `RelationshipExpander` adds bounded one-hop declared relationships.
- `GroundingContextBuilder` performs authorization scoping, retrieval, ranking, canonical hydration, budgeted column selection, relationship evidence construction, and unresolved identifier reporting.
- `GroundingEvaluator` measures grounding quality independently of SQL correctness.

## Retrieval Baseline
The baseline is lexical and runnable without vector infrastructure. It searches P2-built table and column search documents using normalized Unicode tokens, including underscore splitting for names like `is_active`.

## Ranking Strategy
Ranking is transparent and deterministic. It combines retrieval overlap, matched table name, matched column name, title, description/search text, tags, glossary terms, and a small table-document boost.

## Authorization Integration
`GroundingContextBuilder` calls `AuthorizationService.get_authorized_resources()` before retrieval. The retriever receives only `allowed_table_fqns`, so unauthorized table documents are filtered before ranking and cannot reach model context.

## Catalog Hydration
Search documents are not trusted as final context. Ranked candidates are hydrated through `CatalogPort.get_tables_by_fqn()` before building `TableContext`.

## Column Selection
Column context is bounded by per-table and total-column budgets. Selected columns include lexical matches, primary keys, and relationship columns required for joins.

## Relationship Expansion
Relationship expansion is bounded to one hop from initially ranked tables. It uses `CatalogPort.get_relationships()` so incoming and outgoing declared FKs are both visible. Related tables are only added when authorized and either already ranked or relationship text matches the question.

## Composite FK Design
`RelationshipEvidence` now uses `from_columns: list[str]` and `to_columns: list[str]`. Single-column FKs remain simple one-item lists, and read-only `from_column` / `to_column` properties preserve simple access. Decision note: `reports/decisions/20260913_composite_relationship_evidence.md`.

## Grounding Budget
Authoritative configuration defined in `src/t2s/grounding/grounding_budget.py` (`GroundingBudget`):
- `max_candidate_tables`: 50 (retriever candidate limit passed to `SchemaRetriever.retrieve_schema_candidates`)
- `max_hydrated_tables`: 8 (maximum hydrated table candidate cap; passed as `max_tables` to `RetrievalRanker.rank_table_candidates` and `RelationshipExpander.expand_one_hop_relationships`)
- `max_columns_per_table`: 12 (maximum selected columns per individual table)
- `max_total_columns`: 60 (global cap across all tables in `GroundingContext`)
- `max_relationships`: 16 (maximum 1-hop relationship edges expanded)

*Note on Parameter Mapping*: In `RetrievalRanker.rank_table_candidates(..., max_tables=...)`, the parameter name is `max_tables`, which receives `grounding_budget.max_hydrated_tables` (default 8). The independent review report referenced `max_tables: default 4` as a typographical summary note; the authoritative codebase defines `max_hydrated_tables = 8`.

These are intentionally conservative starter values for baseline measurement, not production-tuned limits.

## Evaluation Dataset
The included fixture dataset has 2 labeled cases:
- English single-table: `List active customers`
- Vietnamese join: `Doanh thu theo khách hàng`

The broader unit fixture also covers duplicate short names, unauthorized metadata, incoming/outgoing FK lookup, composite FK preservation, context budget enforcement, and unresolved `sql_identifier`.

## Metrics
Fixture results from `tests/unit/grounding/test_grounding_baseline.py::test_vietnamese_and_english_evaluation_fixture_measures_recall`:

| Metric | Value |
|---|---:|
| Dataset size (N) | 2 |
| Table Recall@K | 1.00 |
| Column Recall@K | 1.00 |
| Average selected tables | 2.00 |
| Average selected columns | 6.00 |
| Average grounding latency | 0.6405 ms |
| False-negative classifications | none in fixture |

**Important Scope Qualification**:
These metrics (`Table Recall@K = 1.00`, `Column Recall@K = 1.00`) were evaluated strictly on a minimal unit test fixture of size $N=2$. They validate the structural correctness of the evaluation harness mechanics and fixture assertions, and do **NOT** represent production-level retrieval accuracy or statistical confidence across arbitrary enterprise schemas.

## False-Negative Analysis
No false negatives occurred in the included fixture. Expected future miss categories are table retrieval miss, column retrieval miss, relationship expansion miss, identifier unresolved, metadata missing, and ranking issue.

## Files Changed
- `src/t2s/contracts/grounding_context.py`
- `src/t2s/solver/prompt_builder.py`
- `src/t2s/grounding/`
- `src/t2s/evaluation/`
- `tests/fixtures/grounding_fixtures.py`
- `tests/unit/grounding/test_grounding_baseline.py`
- `reports/decisions/20260913_composite_relationship_evidence.md`

## Tests
- Search candidate retrieval
- Ranking order and duplicate short-name FQNs
- Canonical hydration
- Authorization filtering
- Column selection and budgets
- Relationship expansion in outgoing and incoming directions
- Composite FK representation
- Unresolved `sql_identifier`
- Vietnamese and English grounding fixture evaluation
- P4 prompt regression against the relationship contract

## Commands/results
```bash
.venv/bin/python -m pytest -vv
# 93 passed in 0.74s

.venv/bin/python -m ruff check .
# All checks passed!

.venv/bin/python -m mypy src workers
# Success: no issues found in 73 source files
```

## Known Limitations
- No OpenSearch query adapter read path was added; the retrieval port is ready for one, and the baseline is verified with deterministic in-memory search.
- No vector, embedding, translation, query-history, sample-value, or database-probing logic is included.
- Vietnamese support depends on metadata/search terms already containing Vietnamese or mixed-language descriptors.
- The fixture dataset is deliberately small and should be expanded before using metrics as a product-quality claim.

## Non-Blocking Baseline Debt
As established in the independent review (`reports/reviews/p3_grounding_baseline_review.md`), the following items are acknowledged baseline limitations and recorded as non-blocking technical debt (not blockers for P5):

- **`P3-MED-01` (Column-Score Accumulation Bias in RetrievalRanker)**:
  `RetrievalRanker` sums column candidate scores across all matching columns (`sum(candidate.retrieval_score for candidate in table_candidates)`). In wide tables (e.g. 50+ columns) containing common tokens (such as `status`, `created_at`), aggregate scores can outscore narrower tables with exact table-name hits. Mitigated currently by table budgeting and key boosts (+5.0 for PK/FKs); score saturation/dampening deferred to future ranking iterations.
- **`P3-MED-02` (Vietnamese Diacritic Sensitivity in Lexical Tokenizer)**:
  `tokenize_search_text` uses Unicode word matching (`\w+`) without Unicode normalization / accent stripping (NFD fold). Unaccented queries (e.g. `khach hang`) do not match accented catalog metadata (`khách hàng`). Baseline relies on metadata/search terms matching query accent form; normalization fold deferred to search indexing enhancements.
- **`P3-MED-03` (Minimal Benchmark Dataset Size $N=2$)**:
  The evaluation benchmark suite currently includes only 2 fixture cases (`english-single-table`, `vietnamese-join`). While verifying harness execution and recall math, expanding to an empirical benchmark corpus ($N \ge 50$) is deferred to future benchmarking phases.
- **`P3-DEBT-01` (Dual-Sided Relationship Evidence Attachment)**:
  `_group_relationships_by_table_fqn` attaches discovered relationship evidence to both source and target `TableContext.relationships`, causing minor prompt verbosity that the downstream SQL solver handles gracefully.

## Deferred Improvements
- Add a live OpenSearch-backed `SchemaSearchPort` adapter.
- Expand labeled grounding fixtures by domain and difficulty slice.
- Compare lexical baseline against hybrid/vector retrieval once embedding infrastructure is real.
- Add richer failure analysis artifacts when benchmark size grows.

## Exit Criteria Checklist
- [x] question -> candidate retrieval works
- [x] candidates are hydrated from canonical catalog
- [x] authorization is enforced before model context
- [x] table FQN and sql_identifier remain distinct
- [x] unresolved sql_identifier is never fabricated
- [x] columns are selected with bounded context
- [x] declared relationships can expand in both directions
- [x] composite FK evidence is lossless
- [x] GroundingContext is compatible with P4
- [x] Table Recall@K is measured
- [x] Column Recall@K is measured
- [x] false negatives are inspected
- [x] regression suite passes
- [x] Ruff passes
- [x] Mypy passes
- [x] no SQL generation or agentic logic is introduced

## Independent Review Outcome
- **Independent review verdict**: `PASS`
- **Review Report Reference**: `reports/reviews/p3_grounding_baseline_review.md`
- **Date**: 2026-09-13
- **Summary**: P3 establishes an architecturally sound, deterministic schema grounding baseline that strictly respects authorization boundaries, preserves canonical catalog truth, maintains `table_fqn` vs `sql_identifier` separation, cleanly handles composite foreign keys, and enforces context budgets. All non-blocking findings (`P3-MED-01`, `P3-MED-02`, `P3-MED-03`, `P3-DEBT-01`) are cataloged as baseline debt for future optimization and do not block P5.

## Final Status
`PASS`
