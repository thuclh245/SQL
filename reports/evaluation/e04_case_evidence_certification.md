# E04 — Case-Level Evidence Harness & Exact Prompt Traceability

**Verdict: PASS**
**Branch:** `eval/e04-case-evidence`
**Source commit (base):** `4a4cc44ba3d35e082a564dbef70f9ba7109d7ce8`
**Scope:** measurement infrastructure only — no accuracy behavior changed.

---

## 1. Objective

Make every evaluation case reconstructable case-by-case:

> question → exact grounding/context → exact prompt → exact model config →
> candidate SQL (raw + extracted) → verification → execution → result
> fingerprints → completeness/audit references.

The hard lesson E04 answers: prior P1 semantic conclusions became un-auditable
because candidate SQL and exact per-case context/prompt were never persisted.
E04 makes candidate-SQL and exact-prompt persistence a hard requirement and
adds machine-checkable evidence completeness.

E04 is **not** about improving SQL accuracy and makes no accuracy claim.

---

## 2. What was built (files changed)

New evaluation-layer package (under `src/t2s/benchmark/`, excluded from
production-runtime audits):

| File | Purpose |
|---|---|
| `src/t2s/benchmark/case_evidence/contract.py` | Canonical versioned `CaseRunRecord` (`e04.case_run_record.v1`), `EvidenceCompleteness`, `GenerationOutcome`, completeness classifier |
| `src/t2s/benchmark/case_evidence/hashing.py` | Deterministic SHA-256 over canonical JSON / UTF-8 text |
| `src/t2s/benchmark/case_evidence/recorder.py` | Observational `RecordingChatClient` + `recording_schema_serializer` + contextvar case correlation |
| `src/t2s/benchmark/case_evidence/assembler.py` | Fuses runtime result + recorded evidence into a `CaseRunRecord` |
| `src/t2s/benchmark/case_evidence/writer.py` | Artifact directory tree (§11) + experiment manifest + `case_records.jsonl` |
| `src/t2s/benchmark/case_evidence/replay.py` | Read-only replay (no LLM) + hash-integrity verification |
| `src/t2s/benchmark/case_evidence/emit.py` | `EvidenceEmitter` glue + source/config provenance helpers |

Additive integration (observational only):

- `src/t2s/benchmark/runner.py` — wraps the chat client with `RecordingChatClient`,
  passes the recording serializer, sets a per-case correlation scope, and emits a
  `CaseRunRecord` per case. New flags: `--no-case-evidence`, `--evidence-dir`,
  `--experiment-id`, `--replicate-id`, `--dataset-split`. Emission defaults **on**.

Scripts & tests:

- `scripts/evaluation/run_e04_certification.py` — dry certification (fake provider, no network).
- `scripts/evaluation/audit_e04_evidence.py` — independent falsification self-audit.
- `scripts/evaluation/build_e04_manifests.py` — generates `results/e04/*` manifests.
- `tests/unit/benchmark/test_case_evidence_harness.py` — 15 tests (§20).
- `tests/unit/architecture/test_case_evidence_boundary.py` — 2 boundary guards.

**No production runtime file was modified.** The only edited non-new source file is
the evaluation-layer `benchmark/runner.py`.

---

## 3. Traceability map (audit before change, §5)

See `results/e04/prompt_traceability_manifest.json` for the full stage-by-stage
map (evaluation runner → case loader → grounding → serializer → prompt builder →
LLM client → returned SQL → validators → execution → scoring). Key gaps E04
closed:

- **Exact prompt** — was never persisted; now captured at the chat-client boundary
  (closest safe point to the provider) as the exact ordered messages + SHA-256.
- **Exact grounding sent to the model** — only baseline/final table FQNs were
  persisted; now the byte-for-byte serialized authorized schema + structured
  provenance (tables/columns/relationships) are captured.
- **Raw model output** — was discarded after extraction; now preserved distinctly
  from the extracted candidate SQL (§9 hard gate).

---

## 4. How the guarantees are met

### Exact prompt (§7)
`RecordingChatClient` records the exact ordered `messages` handed to the provider
plus a reproducible `prompt_hash`. Model config that lives on the client
(temperature, token-limit parameter) is frozen once in the experiment manifest.
API keys / auth headers are **never** captured — the wrapper only sees `messages`.

### Exact grounding (§8)
`recording_schema_serializer` delegates to the default
`DirectSqlPromptBuilder._format_authorized_schema` (a pure function of the
grounding context) so the serialized string is **byte-identical** to the
un-instrumented run, then records it plus structured selected-tables/columns/
relationships. Verified byte-identical in
`test_instrumentation_does_not_change_runtime_semantics`.

### Candidate SQL — hard gate (§9)
`raw_model_output` (full structured dict) and `raw_model_output_hash` are stored
separately from `candidate_sql` / `candidate_sql_hash`. The extracted candidate is
never allowed to overwrite the raw output.

### Result fingerprinting (§10)
Reuses the existing deterministic `t2s.benchmark.scoring.compute_result_fingerprint`.
Default evidence stores fingerprints + row count + schema, not row contents.

### Directory contract (§11)
```
results/evaluation/<experiment_id>/
    experiment_manifest.json
    case_records.jsonl                      # one full record per line (E05 feed)
    cases/<case_id>/<replicate_id>/
        input.json grounding.json prompt.json generation.json
        validation.json execution.json evidence_manifest.json
```
Every record is addressable by `experiment_id` / `case_id` / `replicate_id`.

### Evidence completeness (§12)
`classify_evidence_completeness` → COMPLETE / PARTIAL / INSUFFICIENT. A case with
no candidate SQL **and** no explicit generation-failure state is INSUFFICIENT
(semantic audit not reproducible), never silently scored. Exposed on every record.

### Generation-failure semantics (§13)
Distinct `GenerationOutcome`: PROVIDER_ERROR, GENERATION_EMPTY, SQL_EXTRACTION_ERROR,
VALIDATION_REJECTED, EXECUTION_ERROR, EXECUTION_SUCCESS, ABSTAIN, UNKNOWN. The dry
run demonstrates EXECUTION_SUCCESS, SQL_EXTRACTION_ERROR and PROVIDER_ERROR from
real runtime states.

### Replicate identity (§14)
`case_id` is stable across replicates; `replicate_id` differs; each lands in its
own addressable directory. Replicates are never flattened into independent cases.

### Experiment manifest (§15)
Freezes source commit + dirty, dataset name/split/hash, model/provider/temperature,
seed & retry policy, correction budget, grounding strategy + config hash, prompt
version, validator/verifier mode, scorer-version placeholder, timestamp.

### Replay (§17)
`load_case_record` reloads from `evidence_manifest.json`, calls no LLM, executes no
SQL, mutates nothing. Re-running is a separate concern that must mint a new
run/replicate identity.

### Hash integrity (§18)
SHA-256 everywhere; `verify_record_hashes` recomputes every stored hash from stored
content. A mismatch is flagged as corruption (proved by `test_hash_corruption_detected`).

---

## 5. E04 ↔ E05 shared interface

E05 (`src/t2s/evaluation/scoring/protocols.py`) declares the consumption protocol
`CaseRunEvidence`, version **`e05.case_evidence.v1`**. `CaseRunRecord` **structurally
satisfies** it (`isinstance(record, CaseRunEvidence)` is `True`) — matching field
names/semantics for `case_id`, `replicate_id`, `db_id`, `question`,
`evidence_context`, `candidate_sql`, `gold_sql`, `runtime_status`,
`candidate_execution_ok`, `gold_execution_ok`, `candidate_result`, `gold_result`,
`candidate_fingerprint`, `gold_fingerprint`, `db_path`. The coupling is structural
and versioned, not an import: the boundary guard forbids E04 from importing
`t2s.evaluation.scoring`, and E05 supplies gold text from the dataset (E04 stores gold
**fingerprints only**, never gold SQL).

---

## 6. Anti-leakage & isolation (§3, §19)

- Production runtime never imports the evidence harness — enforced by
  `test_production_runtime_does_not_import_case_evidence`.
- The evidence harness never imports the scorer/gold path — enforced by
  `test_case_evidence_does_not_import_scorer_or_gold`.
- Gold SQL is never handed to the harness; it cannot appear in any prompt/context
  artifact (`test_no_gold_in_evidence`, plus the self-audit's `no_gold_in_prompt`).
- No secrets captured (`test_no_secret_captured`, self-audit `no_secret_leak`).
- Dry certification uses the **dev** partition (`t2s_p8b_dev100.jsonl`) with a fake
  provider; the protected holdout is untouched.

---

## 7. Dry certification run (§21)

`python scripts/evaluation/run_e04_certification.py --limit 8`

- 8 dev cases through the **real** runtime pipeline (real grounding, real SQLite
  execution on official BIRD dev databases), fake deterministic provider.
- Outcomes: **6 EXECUTION_SUCCESS, 1 SQL_EXTRACTION_ERROR, 1 PROVIDER_ERROR**.
- **8/8 COMPLETE** (reconstructable), all hashes valid, no gold in prompt, no
  secret captured, replay reconstructs each case with no LLM call.

Full summary: `results/e04/dry_certification_summary.json`.

---

## 8. Independent self-audit (§24)

`python scripts/evaluation/audit_e04_evidence.py` → **PASS** on every question
(`results/e04/leakage_audit.json`): exact prompt, exact context, candidate SQL /
explicit failure, raw output preserved pre-rewrite, all hashes recompute,
provider/model recorded, provider-vs-SQL failure distinguished, no secret leak, no
gold in prompt, replay read-only/no-LLM, replicate identity preserved.

---

## 9. Regression (§23)

- Unit tests: **576 passed, 4 skipped, 0 failed** (external-artifact skips
  preserved) across the shared working tree (E04 + E05). During development a
  transient 4 failures existed purely in E05's scorer (hygiene guard 2/3 and the
  security-audit naming/dependency checks); E05 then relocated its scorer to
  `src/t2s/evaluation/scoring/` (an audit-excluded path), resolving them. E04
  introduced **zero** failures at any point.
- New E04 tests: 15 (harness) + 2 (boundary guards), all pass.
- `mypy`: Success, no issues in 173 source files.
- `ruff`: clean on all changed files.

Details: `results/e04/regression_manifest.json`.

---

## 10. E04 FINAL DECISION

```
E04 FINAL DECISION
==================
Verdict:                          PASS
Source commit:                    4a4cc44ba3d35e082a564dbef70f9ba7109d7ce8 (branch eval/e04-case-evidence)
Exact prompt persisted:           YES
Exact final context persisted:    YES
Candidate SQL persisted:          YES
Raw model output preserved:       YES
Execution evidence persisted:     YES
Replicate identity preserved:     YES
Evidence completeness:            PASS (machine-checkable; COMPLETE/PARTIAL/INSUFFICIENT)
Hash integrity:                   PASS
Replay without LLM:               PASS
Gold/runtime separation:          PASS
Secret leakage:                   NOT_DETECTED
Runtime semantic behavior changed:NO
Dry certification cases:          8
Reconstructable cases:            8
Incomplete cases:                 0
Core tests:                       17 E04 tests pass; full suite 576 passed / 4 skipped / 0 failed
Architecture guards:              E04 boundary guards PASS; all hygiene/audit guards PASS
Ruff:                             PASS (changed files)
Mypy:                             PASS (173 files)
Ready for E05 integration:        YES (CaseRunRecord satisfies e05.case_evidence.v1)
Blocking issues:                  none for E04
Artifacts:                        reports/evaluation/e04_case_evidence_certification.md; results/e04/*.json;
                                  results/evaluation/e04_dry_certification/
```
