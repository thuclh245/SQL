# Accuracy Foundation and Value Linking

**Scope**: fix evaluation/runtime defects that distort measured accuracy, make grounded
literal values available to the solver, and measure whether accuracy actually moves.

**Non-scope**: semantic planning, result-aware verification, multi-candidate generation,
retrieval redesign. See *Remaining Risks* for work found in the tree that belongs to
those capabilities.

---

## Current-State Audit

The audit read live code first and treated historical reports as claims to re-verify.
Two findings materially revise earlier summaries of this system.

**The benchmark harness was never running against empty databases.**
`benchmarks/t2s/databases/official` is a symlink to a populated BIRD mini-dev tree, and
`verify_benchmark_database_integrity` in [invariants.py](../../src/t2s/benchmark/invariants.py)
already enforces per-table row counts against a manifest and refuses a database whose
relations are all empty. Benchmark accuracy numbers were therefore computed against real
data. Only the **production runtime** was pointed at a schema-only copy.

**`gold_execution_success: false` on 56 of 100 cases was not a gold failure.**
[runner.py](../../src/t2s/benchmark/runner.py) executes gold SQL only when
`runtime_status == COMPLETED`, so the flag reads "not attempted" for every case where the
pipeline abstained. The 56/44 split exactly mirrors the abstention rate rather than
indicating broken gold.

---

## Confirmed Root Causes

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| A | Runtime/eval DB points at schema-only databases | **PARTIALLY_CONFIRMED** | Production `.env` pointed at a 0-row database (5 tables, all empty, 24 KB). Evaluation did not: it used the populated symlink plus row-count integrity checks. |
| B | Prompt v002 reduced excessive UNRESOLVED | **CONFIRMED** | 3+3 replicate experiment in [p7b summary](../../results/p7b_prompt_calibration/summary.md): UNRESOLVED 44.7%→6.3%, EX 19.6%→30.6%. Independently re-measured in this pass (see Ablation). |
| C | Some evaluation configs still frozen on v001 | **CONFIRMED** | `configs/final_holdout/t2s_final_holdout_v1.json` is `status: FROZEN` on `prompts/direct_sql/v001`; `Settings.runtime_prompt_version` also defaulted to `v001`. |
| D | UNRESOLVED discards otherwise valid SQL | **CONFIRMED** | `EscalationPolicy` escalated on any non-empty `sql_candidate.unresolved`; the orchestrator's same-context guard then returned `UNRESOLVED` while still holding the candidate, and the runtime dropped it. In the 100-case run, 53 of 54 UNRESOLVED cases carried `escalation_reason: solver_unresolved` with `same_context_stop: true`. |
| E | API execution carries little or no business evidence | **CONFIRMED** | `QueryRequest` had no evidence field at all. Benchmark evidence was concatenated into the question string in `build_query_request_from_benchmark_case`; production had no evidence path whatsoever. |
| F | `GroundingContext.value_bindings` exists but is never populated | **CONFIRMED** | Field declared in [grounding_context.py](../../src/t2s/contracts/grounding_context.py); no assignment anywhere in `src/`. The `{value_bindings}` prompt slot rendered empty on every request. |
| G | `glossary_hits` and `validated_examples` are empty | **CONFIRMED** | No producer exists for either. Left empty deliberately — see *Evidence Plumbing*. |
| H | `max_sample_values_per_column` exists but drives nothing | **CONFIRMED** | Present only as a key inside the frozen holdout JSON. Not a field on `GroundingBudget`, and referenced by no code. |

---

## Runtime Database Configuration

The production runtime pointed at
`data/bird_mini_dev/schema_only_databases/debit_card_specializing/debit_card_specializing.sqlite`
— five tables, zero rows. `.env.example` recommended exactly this path in its worked
example, so the misconfiguration was the documented default rather than an accident.

Such a database is invisible to every gate: the catalog loads, grounding succeeds,
generation succeeds, safety and authorization pass, execution succeeds, and the answer is
`NULL`. That reads as a model-quality finding when it is a configuration fault.

**Added**: [`database_readiness.py`](../../src/t2s/database/database_readiness.py) with
SQLite and PostgreSQL inspectors, invoked from `build_runtime_from_settings` at startup.

The check is deliberately weak. It asserts only that *some* user relation holds *some*
row, sampling with `SELECT 1 ... LIMIT 1` rather than counting. An individual empty table
is normal in production and never fails the check; a database where every sampled relation
is empty is not one anyone meant to query. Verdicts are `READY`, `UNREACHABLE`,
`NO_USER_RELATIONS` or `NO_DATA_ROWS`.

It is governed by `RUNTIME_REQUIRE_POPULATED_EXECUTION_DATABASE` (default `true`, fail
closed at startup with an actionable message). No developer path is hardcoded into source;
`.env.example` now warns that the bundled schema-only copies are for catalog work only.

Evaluation keeps its stronger, manifest-based integrity check. That check compares exact
per-table row counts and belongs in the harness, not in the production request path.

---

## Prompt Version Findings

v001 instructs: *"If critical evidence is missing, keep SQL conservative and record the gap
in unresolved."* v002 replaces that with an explicit contract: *"If you can produce a
defensible executable SQL query, unresolved MUST be []. Place working interpretations,
caveats, tie-breaking choices, and NULL handling in assumptions."*

The historical P7-B experiment (3 replicates per arm) is reproduced in this pass's
ablation arms A→B under a different model, which is a stronger test of the effect than a
repeat under the original one.

**Frozen configs were not modified.** `configs/final_holdout/t2s_final_holdout_v1.json`
still declares `prompt_version: v001`, and its recorded `system_prompt_sha256` and
`user_template_sha256` still match the on-disk v001 files byte for byte — verified after
all changes. v001 and v002 were not edited.

**Added**: `prompts/direct_sql/v003_*` (v002 plus an evidence block and a value-usage
instruction) and `configs/runtime/t2s_value_grounded_runtime_v1.json`, a new `ACTIVE`
configuration that names the frozen one it does *not* supersede.

---

## UNRESOLVED Policy

### Old behaviour

```
solver returns unresolved: ["No tie-break rule was supplied."]
  → EscalationPolicy: if sql_candidate.unresolved: escalate
  → reground with expanded budget
  → context identical (budget was already sufficient)
  → same-context guard → OrchestrationOutcome.UNRESOLVED
  → runtime abstains; the candidate SQL is discarded unexecuted
```

The candidate was present in `OrchestrationResult.sql_candidate` the whole time.

### New behaviour

Classification is **structural**. The wording of the note is never inspected.

```
candidate exists
  ∧ grounding reported no unresolved_sql_identifier
  ∧ every referenced relation was grounded
  → NON_BLOCKING_CAVEAT → RESOLVED_WITH_CAVEATS
  → normal path: AST parse → read-only safety → authorization → execution
  → caveats surface as SOLVER_CAVEAT warnings on the response
```

The reasoning: a model that emitted a parseable statement over grounded relations
demonstrably *was* able to formulate a query, so its prose caveat describes that query
rather than preventing it. Blocking conditions remain `unresolved_sql_identifier`, a
reference to an ungrounded relation, and no candidate at all.

### Why no phrase matching

`src/t2s/evaluation/shadow_evaluator.py` already contains a free-text classifier, and it
demonstrates the failure mode this design avoids. Its `HARD_BLOCKER` list includes
`"no telephone"`, `"no patient-level join key"`, `"cannot show card names"` and
`"specific customer or transaction at 16:25:00 was not provided"` — strings recovered from
individual observed benchmark failures. That classifier is confined to offline shadow
analysis and is **not** used by the runtime policy added here.

Column-level reference checking was considered and rejected: aliases, computed projections
and quoting styles make it unreliable, and a wrong verdict there would abstain on a correct
query. The access validator re-derives relations from the parsed AST independently, so this
leniency cannot admit an unauthorized reference.

### Abstention posture is configurable

`RELEASE_CANDIDATES_WITH_CAVEATS` (default `true`) selects the posture. Setting it `false`
restores strict abstention — appropriate where an unreviewed answer costs more than no
answer, and the setting that reproduces pre-correction runs. It is a genuine risk control,
not a flag left behind by the experiment.

---

## Evidence Plumbing

| Field | Producer | Consumer | Populated? | Production source | Evaluation source |
|---|---|---|---|---|---|
| `QueryRequest.evidence` | caller | `{evidence}` in v003 prompt | when supplied | governed business context (none wired yet) | benchmark case, `--evidence-mode structured` |
| `GroundingContext.value_bindings` | `ValueGrounder` | `{value_bindings}` | **yes, new** | live read-only probes of the execution DB | same mechanism, same DB |
| `GroundingContext.glossary_hits` | none | `{glossary_hits}` | no | no provider exists | none |
| `GroundingContext.examples` | none | `{validated_examples}` | no | no provider exists | none |

`glossary_hits` and `validated_examples` were left empty on purpose. Populating them from
benchmark data would leak answer-side information into the solver, and fabricating them
would put invented business definitions into a prompt that instructs the model not to
invent business definitions. Empty is the honest state until a real glossary provider
exists.

**Benchmark evidence isolation.** Dataset evidence reaches the solver only through
`build_query_request_from_benchmark_case`, which lives in the evaluation layer. Production
constructs `QueryRequest` itself and leaves `evidence` empty by default. Tests assert both
directions.

Evidence is no longer silently concatenated into the question. `evidence_mode` is an
explicit per-run choice: `inline` reproduces the historical concatenation so earlier runs
stay comparable, `structured` carries evidence as its own field for prompt versions that
render an evidence block. Making the choice explicit is what allows arms D→E to measure it.

---

## Value Linking Architecture

```
Question
  → schema retrieval / relationship expansion   (authorization applied here)
  → grounded TableContexts + ColumnContexts
  → CandidateColumnSelector   (type, structural role, governance tags, lexical relevance)
  → QuestionTermExtractor     (quoted spans, words, adjacent word pairs)
  → ValueProbePort            (≤ 2 bounded, parameterized probes per column)
  → ValueGrounder             (deterministic ranking, dedup, budget cap)
  → GroundingContext.value_bindings
  → {value_bindings} in the solver prompt
```

Value grounding runs **inside** `GroundingContextBuilder` and is only ever offered columns
that are already in the context, so it inherits the authorization decision made upstream
rather than re-deriving it.

### Two passes, both bounded

1. **Targeted** — one batched equality probe per column carrying *every* question term at
   once. This is what keeps cost at one round trip per column instead of one per
   (term, column) pair.
2. **Domain** — only for columns the targeted pass did not hit: a capped distinct read that
   fetches `max_values + 1` rows. If the extra row appears, the column is high-cardinality
   and its partial domain is **discarded**, never rendered. Otherwise the column is
   enum-like and its terms are matched lexically in Python at no extra database cost.

Hard ceiling: `max_value_columns × 2` probes per request (12 by default), asserted by test.

### Language and schema neutrality

There is no stopword list, no capitalisation rule and no vocabulary. Every token of length
≥ 2 becomes a candidate term; precision comes from the probe, not from pre-filtering the
question. A term earns a binding only if the database actually stores it, so a word that
happens to equal a stored value *is* a legitimate value link.

Case folding happens in Python via `casefold()` on NFKC-normalised text, with variants
precomputed and bound as parameters. This is Unicode-correct regardless of database
collation, and it leaves the probe as a plain equality predicate an index can serve —
rather than `LOWER(col) = ?`, which is both ASCII-only in SQLite and unable to use an index.

### Literal fidelity

The binding carries the **database's** spelling, not the question's. A question saying
`ENTERPRISE` against a stored `enterprise` yields `candidate_value="enterprise"` with
`match_type=CASE_INSENSITIVE` and `phrase="ENTERPRISE"`. The normalized form used for
matching is never what reaches the prompt, so the solver always emits a literal that
compares equal.

### Column eligibility (generic signals only)

- **Type**: textual families only (`text`, `varchar`, `char`, `string`, `nvarchar`, `clob`,
  `enum`). Excluded outright: `json`, `uuid`, `blob`, `bytea`, `xml`, `array`, `vector`,
  geometry. Temporal types are excluded — date semantics belong in query planning, not
  distinct-value enumeration.
- **Structural role**: primary keys and declared foreign-key participants are skipped; they
  identify rows rather than categorise them, and their domains are as large as the table.
- **Governance**: any column whose tags or glossary terms carry a standard classification
  marker (`pii`, `phi`, `pci`, `sensitive`, `restricted`, `confidential`, `secret`,
  `credential`) is never probed.
- **Relevance**: lexical overlap between the question and the column's own metadata orders
  the candidates, but does not gate matching — proven by a metamorphic test that strips all
  descriptions and still finds the binding.

Free-text columns need no special rule: a long prose value will not equal a short question
term, and the domain pass discards any column whose distinct count exceeds the budget.

---

## Value Grounder Contract

```python
class ValueProbePort(Protocol):
    def probe_matching_values(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome: ...
    def probe_column_domain(self, probe_request: ValueProbeRequest) -> ValueProbeOutcome: ...


class ValueProbeColumn(BaseModel):       # frozen
    table_fqn: str
    sql_identifier: str                   # from the catalog, never from user input
    column_name: str
    data_type: str


class ValueProbeRequest(BaseModel):      # frozen
    column: ValueProbeColumn
    match_terms: tuple[str, ...] = ()     # always bound as parameters
    max_values: int = 5
    timeout_ms: int = 1500


class ValueBindingCandidate(BaseModel):  # frozen
    table_fqn: str
    column_name: str
    phrase: str                           # the user's wording
    candidate_value: str                  # the database's spelling
    match_type: ValueMatchType            # EXACT | CASE_INSENSITIVE | LEXICAL
    evidence_score: float                 # 0.0–1.0, deterministic


class ValueGrounder:
    def ground_values(
        self,
        question: str,
        catalog_tables: Sequence[CatalogTable],
        selected_column_names_by_table_fqn: dict[str, set[str]],
        relationships: Sequence[CatalogForeignKey] = (),
    ) -> ValueGroundingResult: ...
```

`ValueProbePort` is kept separate from `QueryExecutorPort` deliberately. That port executes
model-authored SQL and is guarded by AST parsing, safety and access validation. Value
probes are system-authored parameterized statements over catalog-supplied identifiers, so
they take a narrower contract that *cannot express arbitrary SQL*.

Adapters: `SqliteValueProbe`, `PostgresValueProbe`. Both satisfy the port structurally,
matching the repo's existing convention. The port itself carries no dialect syntax.

Ranking is deterministic — match type, then table, column and value — with no LLM call.

---

## Security / ACL

| Control | Mechanism |
|---|---|
| Authorization precedes retrieval | Only columns already in the grounding context are offered to the grounder; that context is built from `AuthorizationService.get_authorized_resources`. |
| Read-only | SQLite: `mode=ro` URI + `PRAGMA query_only = ON`. PostgreSQL: `SET TRANSACTION READ ONLY` as the transaction's first statement, always rolled back. |
| Parameterization | Every term is bound. SQL syntax inside a term stays inert — asserted by a test that attempts `'); DELETE FROM accounts; --` and then verifies the row count. |
| Identifier safety | Identifiers come only from the catalog and are still quoted: `"` doubling for SQLite, `psycopg.sql.Identifier` for PostgreSQL. |
| Row bounds | `LIMIT` on every probe; domain reads fetch `max_values + 1` purely to detect truncation. |
| Time bounds | SQLite progress handler aborts past `timeout_ms`; PostgreSQL `SET LOCAL statement_timeout`. |
| Sensitive columns | Governance-tagged columns are excluded before any probe is issued. |
| Cost bounds | `max_value_columns × 2` probes per request, asserted by test. |
| Log hygiene | Diagnostics record the **exception type only**, never the database message, because a database error can echo the offending literal. Traces record column FQNs and counts, never values. |
| Failure mode | A failed probe yields no bindings plus a diagnostic; it never fails the pipeline. |
