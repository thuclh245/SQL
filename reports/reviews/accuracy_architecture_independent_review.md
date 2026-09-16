# T2S / CHATSQL Independent Accuracy & Production Architecture Review

**Review date:** 2026-09-16
**Repository:** `/home/thuclh245/MyCode/SQL`
**Scope:** causal-evaluation claims, runtime wiring, prompt/evidence controls, verification, parity, metadata contracts, and governance.

## Executive Verdict

**Overall verdict: PASS_WITH_CONDITIONS.**

The review supports retaining the corrected unresolved policy and post-execution result checking. It does not support promoting v003 or removing the Semantic Planner as a matter of causal accuracy. The planner has a credible operational case against default hot-path execution, but no clean F0/F1 planner-only accuracy experiment exists. Value Linking shows no benchmark execution-accuracy lift, but remains a safe enterprise capability whose production usefulness is not disproved.

The highest-leverage next slice is a provenance-aware semantic metadata extension to the existing canonical metadata model, followed by a preregistered parity-controlled evaluation. No benchmark-specific rule, linguistic dictionary expansion, or production enforcement change is justified by this review.

## Evidence Reviewed

Primary evidence included:

- `reports/experiments/accuracy_causal_evaluation.md`.
- Raw ablation artifacts under `results/accuracy_foundation_ablation/`, including `cases.jsonl`, `failures.jsonl`, `metrics.json`, and `manifest.json` for A, B, C, D, E, and E1.
- Live source in `src/t2s/bootstrap/runtime_factory.py`, `src/t2s/benchmark/runtime_factory.py`, `src/t2s/orchestration/adaptive_orchestrator.py`, `src/t2s/semantics/`, `src/t2s/solver/prompt_builder.py`, `src/t2s/verification/`, `src/t2s/benchmark/runner.py`, and `src/t2s/benchmark/metrics.py`.
- Prompt files `v001`, `v002`, and `v003`; canonical metadata, snapshot, provider, and grounding contracts.
- Relevant architecture, security, semantics, verification, value-grounding, and evidence-isolation tests by inspection.
- Existing implementation and hardcode/governance audit reports.

The working tree is dirty and contains the implementation under review. The ablation manifests consistently identify commit `4f5543a...`, the same dataset SHA-256, model `openai/gpt-oss-120b`, temperature `0.0`, and official database root. However, the manifests do **not** contain prompt hashes or system/user template hashes, despite the review requirement. This weakens exact reproducibility claims.

## Methodology Risks

The experiments share dataset, database root, model, temperature, token limit, and read-only execution settings. C vs D is a useful three-replicate comparison. E vs E1 is not a pure v003 wording comparison because evidence representation changes, and E1 has N=1. The report correctly identifies this confounding, but its conclusion that the structured mode alone “caused” the collapse should be stated as the leading explanation, not a fully isolated causal result.

The raw artifacts also show minor accounting distinctions that should be made explicit: status `SUCCESS` is not the same as “gold execution was attempted,” and per-run status counts vary because access/safety/execution failures are included. Historical `gold_execution_success` is serialized as `false` both when gold SQL was not attempted and when it was attempted and failed.

## Semantic Planner Review

### Live behavior

The production factory constructs `GroundedSemanticPlanner` with the same chat client and model as the solver and passes it to `AdaptiveOrchestrator`. The orchestrator invokes it once for every query when configured. A planner exception is swallowed and converted to `semantic_plan = None`, after which SQL generation continues. Thus it adds a remote structured LLM call on the normal production path, but planner failure is fail-open with respect to SQL generation.

The benchmark factory does not construct or pass a planner. This is a real production/benchmark mismatch.

The planner can return `READY` with weak or empty semantic content. In deterministic mode, a nonempty grounded table list makes the status `READY` even when metric grain is unknown; in LLM mode the schema permits empty `relevant_tables`, no filters, `metric_name=None`, and `aggregation=NONE` unless the provider/model supplies better values. Such a plan reaches downstream prompt formatting and consistency checks and can alter SQL generation. The reported empty-plan examples are therefore operationally credible.

The deterministic implementation contains linguistic heuristics mapping English and Vietnamese words such as `total`, `average`, `count`, `tổng`, and `trung bình` to aggregations. These are general linguistic heuristics, not benchmark table hardcodes, but they are not reliable semantic proof: “average” can occur in a comparison/filter or subquery. The existing tests encode the behavior; they do not establish production accuracy. The review requirement to not expand these dictionaries is upheld.

### Decision

**Planner hot path: `DISABLE_BY_DEFAULT` — action `KEEP_SHADOW`.**

Operational evidence is strong enough to avoid paying an extra LLM call and exposing downstream generation to unvalidated empty plans by default. Accuracy evidence against the planner is **INCONCLUSIVE**, because there is no identical F0/F1 planner-only experiment. Keep the implementation and collect shadow plans/latency/errors; do not delete it and do not claim causal accuracy harm.

## Prompt v003 Review

The v003 system and user templates add grounded-value instructions and separate business evidence. E1 uses the same model, temperature, token limit, dataset SHA, database root, unresolved policy, and value-grounding configuration as E. E1 changes `evidence_mode` from `structured` to `inline`; therefore E1 is not an isolated prompt-only comparison. The raw results are 17/85 (20.00%) for E and 41/85 (48.24%) for E1, with generation failures 29 vs 7.

The most supported classification is **evidence placement / provider-model structured-output interaction**, with prompt interpretation/refusal as the observed mechanism. Parsing failure is less supported because the dominant E failure is empty generation, not a broad SQL parser rejection. No evidence supports blaming v003 wording alone.

The manifests record prompt version but not prompt content hashes. v003 is therefore **`REPLICATE_FIRST`**, action `REPLICATE_FIRST`; it must remain experimental until at least three parity-controlled replicates, with prompt hashes and explicit evidence-mode accounting, reproduce the result.

## Value Linking Review

C and D have three replicates under the same reported model, temperature, v002 prompt, inline evidence, unresolved policy, and retrieval settings. C mean EX is 42.75%; D mean EX is 41.57%; reported delta is -1.18% ± 2.54%. The binding subgroup is similarly unstable and shows no net value-driven gain. This supports **no demonstrated benchmark accuracy effect**, not “no production value.”

**Decision: `KEEP_SHADOW`, action `KEEP_SHADOW`.** It is bounded, read-only, and latency is reported in milliseconds rather than LLM seconds. Keep collecting adoption, literal correctness, and enterprise slices without making it a required hot-path dependency. Do not tune it using individual benchmark cases.

## ResultVerifier Review

`ResultVerifier` runs after successful SQL execution and does not alter SQL generation. It distinguishes mathematical zero from `NULL`, flags unexpected empty results and all-null rows, and presents suspicious results as `ambiguous` rather than an unqualified answer. This is an appropriate reliability metric distinct from SQL-generation EX.

The replay claim of 77 executed queries, 7 flagged, 6 incorrect, and 1 false alarm is consistent with the reported 6/7 precision claim, but the provenance of the false alarm matters. The cited `bird_761` false alarm is attributable to an upstream planner semantic expectation/heuristic that classified a list query as scalar AVG; the ResultVerifier then applied that expectation. It is not evidence that the verifier’s NULL/empty checks independently miscomputed a result. Still, verifier correctness depends on plan quality.

Diagnostic probes are AST-parsed, read-only validated, access-validated, and dispatched through the bounded executor policy. They are ACL-safe in the inspected path. However, the generated probes use the first table and drop the candidate’s joins and predicates, so their findings are suggestive rather than a proof of filter failure; wording such as “indicating” is appropriate, while “confirmed matching rows” is too strong.

**Decision: `KEEP_POST_EXECUTION`, action `IMPLEMENT_NOW` (already implemented).** Keep it post-execution and non-generative. Preserve `0 != NULL`, allow empty results when expectation permits them, and retain timeout/row-limit/ACL gates. Improve probe attribution before treating diagnostics as causal labels.

## Production/Benchmark Parity

| Component | Production | Benchmark | Classification |
|---|---|---|---|
| Semantic Planner | LLM planner enabled in factory | Absent | **MEASUREMENT_RISK**; operationally intentional only if benchmark explicitly measures SQL generation without planner |
| Value Grounder | Settings-controlled, dialect-aware | Explicit benchmark flag | **INTENTIONAL** when recorded in manifest |
| ResultVerifier | Enabled after execution | Absent | **PRODUCTION_ONLY_SAFETY**; must not be folded into SQL EX |
| Diagnostic probes | Enabled on suspicious output | Absent | **PRODUCTION_ONLY_SAFETY** |
| Prompt version | Settings-controlled | Manifest-controlled | **INTENTIONAL**, but hash evidence missing |
| Evidence source | Governed metadata/evidence in production | Dataset evidence in harness | **INTENTIONAL** boundary; modes must be measured separately |
| Unresolved policy | Settings/orchestration policy | Manifest-controlled | **INTENTIONAL** when recorded |
| Risk validator | Runtime feature flag, default shadow | Not wired in benchmark runtime | **MEASUREMENT_RISK** for acceptance/abstention metrics |
| Execution policy | Production settings | Benchmark fixed read-only, 1000 rows/30s | **PRODUCTION_ONLY_SAFETY / INTENTIONAL** |

The benchmark should report at least SQL generation accuracy, execution accuracy among attempted queries, answer-acceptance reliability, and abstention quality separately. Result verification should not contaminate the historical EX metric.

## Failure Taxonomy Review

The reported persistent-failure distribution sums to 100%: wrong/missing filter 26.2%, time semantics 19.0%, projection 16.7%, join/table 14.3%, generation failure 11.9%, aggregation/grain 7.1%, literal 4.8%. The raw evidence cited for the review supports these as useful categories, but the report does not expose a machine-readable cross-tab or mutually exclusive adjudication protocol sufficient for independent reclassification. Treat the percentages as **MODERATE**, not strong causal estimates. Do not design fixes from individual cases.

## Metadata Sufficiency Review

The proposed categories—missing metadata, ambiguous semantics, model failure despite available semantics, and retrieval failure—are useful diagnostic labels, but the report does not establish that they are mutually exclusive. A failure can simultaneously have missing grain metadata and poor retrieval, or have present metadata that is ambiguous. Therefore `38% + 29%` must not be reported as a proven 67% metadata-addressable share.

The strongest defensible statement is that metadata sufficiency is a plausible high-leverage bottleneck, with moderate evidence, requiring explicit adjudication rules and provenance for each label.

## Semantic Metadata Enrichment Decision

**Decision: `DESIGN_NEXT`, action `DESIGN_NEXT`.** The direction is justified as a design hypothesis, not yet as a measured production lift.

Use the existing `CatalogTable`/`CatalogColumn`, `MetadataProvider`, `CanonicalMetadataSnapshot`, `GroundingContext`, and `EvidenceRef` boundaries. Do not create a parallel semantic catalog. The next contract slice should add only provenance-aware optional fields for:

- business definition;
- unit and source grain;
- governed metric formula;
- certification state;
- allowed categorical values where authoritative;
- provenance and confidence for each semantic assertion.

Authoritative OpenMetadata, glossary, certified metric definitions, and existing documentation may be `TRUSTED`. LLM-inferred semantics must be `INFERRED`/`REVIEW_REQUIRED` and must never silently become production truth. Sync OpenMetadata into a local accepted canonical snapshot; do not call it per request. The first implementation should support serialization, deterministic snapshot hashing, grounding display, and rejection of untrusted high-impact formulas—not full enrichment or automatic LLM guessing.

## Security/Governance

No new benchmark table/column/case/gold-SQL behavior was found in the inspected production source. The benchmark registry explicitly separates production packages. AST safety, read-only execution, ACL checks, timeouts, and row limits remain in scope. `production_enforcement_authorized` defaults to `False`, and Settings rejects `validator_mode="enforce"` without explicit authorization. Do not alter this.

The separate n8n-to-FastAPI authentication gap remains outside this review’s requested changes; it should not be silently treated as solved by the SQL controls.

## Recommended Code Changes

1. **Implement now:** retain post-execution ResultVerifier and its safety gates; improve diagnostic-probe findings to distinguish “base-table count observed” from “candidate predicate matched.”
2. **Keep shadow:** make planner execution opt-in/default-off in production configuration while preserving shadow telemetry. This is a production policy change only if implemented with an explicit flag and tests; no planner deletion is recommended.
3. **Keep shadow:** retain Value Linking as optional and instrument literal adoption/correctness.
4. **Design next:** extend existing canonical metadata contracts with optional semantic fields, per-field provenance, confidence, and certification state.
5. **Evaluation hygiene:** add SHA-256 hashes for exact system/user prompt files and record provider request payload policy in every experiment manifest.

No code change was made in this review because the user requested architecture review first and the planner default-off change requires a deliberate configuration/test decision. Frozen v001/v002 artifacts were not edited.

## Deferred Work

- Do not promote v003 from one E1 run.
- Do not claim a causal planner accuracy penalty or delete planner code.
- Do not expand English/Vietnamese aggregation dictionaries.
- Do not make Value Linking mandatory based on enterprise intuition or disable it globally based only on BIRD EX.
- Do not implement full automatic metadata enrichment or treat LLM guesses as trusted metadata.
- Do not rewrite historical `gold_execution_success` values.

## Quality Gates

The requested commands were attempted in the workspace, but the environment has no `pytest`, `ruff`, `mypy`, or even `python` executable available on PATH. Exact outputs:

```text
pytest: /bin/bash: line 1: pytest: command not found
ruff check src/ tests/: /bin/bash: line 1: ruff: command not found
mypy src/: /bin/bash: line 1: mypy: command not found
architecture/security targeted pytest: /bin/bash: line 1: pytest: command not found
```

Accordingly, this review cannot certify passing quality gates. Before any production code change, run:

```text
pytest
ruff check src/ tests/
mypy src/
pytest tests/unit/architecture/ tests/unit/security/ tests/unit/grounding/test_value_grounding_security.py tests/unit/semantics/ tests/unit/verification/
```

## Required Final Verdict Table

| Decision | Verdict | Evidence Strength |
|---|---|---|
| Unresolved policy | KEEP_ACTIVE | STRONG |
| Value Linking hot path | KEEP_SHADOW | MODERATE |
| Semantic Planner hot path | DISABLE_BY_DEFAULT / KEEP_SHADOW | INCONCLUSIVE for accuracy; STRONG operationally |
| ResultVerifier | KEEP_POST_EXECUTION | MODERATE |
| v003 prompt | REPLICATE_FIRST | WEAK |
| Structured evidence mode | KEEP_EXPERIMENTAL pending isolation | MODERATE |
| Tri-state gold reporting | DESIGN_NEXT; backward-compatible additive field | STRONG |
| Semantic metadata enrichment | DESIGN_NEXT | MODERATE |

The safe production path is: grounded generation with the corrected unresolved policy, optional Value Linking, no planner LLM call by default but shadow-capable, mandatory AST/ACL/read-only execution controls, and post-execution ResultVerifier kept separate from SQL EX.
