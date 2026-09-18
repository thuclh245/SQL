# Prompt — Integrate T2S Evaluation Kit into the Repository

You are integrating the prepared `T2S Evaluation Kit v1` into the existing T2S repository.

Do not redesign the benchmark or silently modify benchmark gold.

## Inputs expected

- `t2s_pilot_v1.jsonl` supplied by the project owner.
- Official local BIRD Mini-Dev 500 SQLite JSON (`mini_dev_sqlite.json` or equivalent HF export).
- Official local BIRD SQLite database root containing all 11 Mini-Dev databases.
- The files in this evaluation kit.

## Required work

1. Place the kit under the repository's benchmark/evaluation convention without breaking existing P3/P5 evaluators.
2. Run `audit_pilot_v1.py` and preserve the audit artifact.
3. Generate `t2s_eval_v1.jsonl` with `build_eval_v1.py` from the official local BIRD file.
4. Validate that:
   - exactly 100 eval cases exist;
   - no `question_id` overlaps with the 85 BIRD pilot cases;
   - quotas are S1=25, S2=30, S3=30, S4=15;
   - all 11 BIRD databases are represented;
   - official BIRD SQL is unchanged in eval v1.
5. Run `verify_gold_execution.py` against the local read-only SQLite DB root and report failures. Do not repair gold automatically.
6. Implement a thin benchmark runner adapter around the existing T2S runtime. Gold fields must never enter inference.
7. Add a separate scoring step. Prefer the official BIRD execution evaluator if already available in the repo; do not reimplement it unnecessarily.
8. Store one JSONL result record per case using `run_result.schema.json`.
9. Record provider/model/prompt/config/git/source checksums in a run manifest.

## Temporary model backend

The OSS inference backend is temporarily unavailable. Support the current OpenAI-compatible Chat 5 mini path through configuration only.

- API key must come from environment/secret storage.
- Never commit or print the key.
- Do not hardcode the temporary model in business logic.
- Preserve the provider abstraction so OSS can be restored later.

## Evaluation rules

- Pilot is an opened development set.
- Eval v1 is a checkpoint set; do not use its failures for per-change tuning.
- S5 robustness is scored separately and never included in SQL EX.
- Do not treat P5 `BASELINE_SUCCESS` or `ESCALATED_SUCCESS` as proof of SQL correctness.
- Report EX overall, by T2S stratum, BIRD difficulty, and DB.
- Report grounding, escalation, safety, latency, token and failure-stage metrics separately.

## Gold correction rule

The pilot currently contains edited gold. Preserve both original and corrected SQL. Do not make corrected SQL authoritative unless the corresponding correction ledger row has been explicitly approved.

## Validation

Run the repository's standard suite:

```bash
.venv/bin/python -m pytest -vv
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src workers
```

Also run dataset build/validation/gold-execution preflight and record exact outputs.

## Required report

Create `reports/evaluation/t2s_eval_v1_setup_report.md` containing:

- source BIRD path/version/checksum;
- pilot audit summary;
- eval selection manifest;
- overlap check;
- DB/stratum/difficulty distribution;
- gold execution preflight;
- benchmark runner wiring;
- temporary model provider configuration;
- files changed;
- test/lint/type-check results;
- known limitations.

Do not claim benchmark accuracy until an actual model run and official execution scoring have been completed.
