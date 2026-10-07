# 04 — Context and Evidence Grounding

## 1. Goal

Supply the solver with the **smallest sufficient, authorized and evidence-rich context**. Grounding is successful when the required schema/business/value evidence is present with limited irrelevant noise.

## 2. Sources

### OpenMetadata

Potential assets include names, types, descriptions, tags/glossary, sample data, query history, profiler metrics, lineage and frequently joined columns/tables. Availability is configuration/connector dependent and must be audited in the company environment. OpenMetadata is a metadata source, not a guarantee that all business semantics are correct or complete. [S18–S21]

### Query history

Use as behavioral evidence: previous validated NL–SQL pairs, common joins and recurring expressions. Frequency is a prior, not proof of correctness. Logs outside OpenMetadata should be exposed through a separate `QueryLogPort` rather than overloaded into a catalog adapter.

### Database evidence

Safe probes, `EXPLAIN`, existence checks and profiles can resolve value formats and ambiguous column semantics. PV-SQL/VET provide external evidence that execution-grounded feedback can improve reliability in training-free settings. [S8–S9]

## 3. Retrieval strategy

Start simple and escalate:

1. authorized scope filter;
2. hierarchical domain/database -> table -> column retrieval;
3. hybrid lexical+dense ranking;
4. join/connectivity augmentation only for plausible bridge paths;
5. if evidence remains incomplete, bounded schema exploration tools.

AutoLink supports the hypothesis that iterative exploration can improve schema linking in large schemas, but the company workload must decide whether the added agent complexity is worthwhile. [S7]

## 4. Value and time grounding

- Resolve literal surfaces to actual values/columns.
- Normalize dates/times deterministically where possible.
- Treat ambiguous bindings as uncertainty, not a forced guess.
- For high-cardinality fields, prefer exact safe existence probes over fuzzy LSH when the warehouse permits.

Internal evidence [I2] shows literal validity is a strong failure predictor, but it is **correlation**, not evidence that a value-grounding component will automatically add 43pp EX.

## 5. Join evidence

Priority of evidence is contextual, but a useful ranking is:

1. declared constraints/keys;
2. curated semantic/business rules;
3. validated historical queries;
4. observed join counts;
5. inferred name/type similarity.

Observed frequency can help ranking but `frequent != correct for this question`.

## 6. Prompt context policy

Descriptions are primarily retrieval evidence. Only descriptions for selected tables/columns should enter the solver context. Internal evidence [I5] showed blind description injection harmed the prior benchmark while increasing cost.

## 7. Grounding output contract

A suggested logical contract (not necessarily a physical class):

```text
GroundingContext
- authorized_scope
- selected_tables / columns
- relationships + provenance
- glossary/business hits
- value_bindings + unresolved/ambiguous
- similar validated queries
- profiles / sampled evidence
- retrieval warnings
- evidence provenance + timestamps
```

All confidence-like fields here are local signals; they are not final correctness probabilities.
