# T2S Evaluation Kit v1

This kit turns the current T2S pilot into a reproducible two-set evaluation workflow built on the **BIRD Mini-Dev 500 SELECT-only SQLite subset**.

## Intended repository layout

Copy this directory into the project as `benchmarks/t2s/` (or keep the same files under your existing benchmark directory):

```text
benchmarks/t2s/
├── README.md
├── docs/
│   ├── PILOT_V1_AUDIT.md
│   ├── BENCHMARK_DESIGN.md
│   ├── EVALUATION_PROTOCOL.md
│   └── INTEGRATION_GUIDE.md
├── configs/
│   ├── pilot_v1.json
│   └── eval_v1.json
├── schemas/
│   ├── benchmark_case.schema.json
│   └── run_result.schema.json
├── scripts/
│   ├── audit_pilot_v1.py
│   ├── build_eval_v1.py
│   ├── validate_benchmark.py
│   └── verify_gold_execution.py
├── manifests/
└── results/
```

## Core split policy

- **Pilot / development**: existing `t2s_pilot_v1.jsonl`.
  - 85 executable BIRD cases.
  - 15 S5 robustness slots are currently unfinished stubs and MUST NOT be counted in SQL execution accuracy.
  - Opened during development; may be used for failure analysis and tuning.
- **Evaluation v1**: 100 BIRD cases generated deterministically from the remaining Mini-Dev cases.
  - No overlap by `question_id` with the pilot BIRD cases.
  - Uses official BIRD SQL unchanged on first evaluation.
  - Intended for checkpoint evaluation, not per-change tuning.

## Build the 100-case evaluation set

Assuming your local official BIRD file is available:

```bash
python benchmarks/t2s/scripts/build_eval_v1.py \
  --bird-json /path/to/mini_dev_sqlite.json \
  --exclude-jsonl /path/to/t2s_pilot_v1.jsonl \
  --output benchmarks/t2s/datasets/t2s_eval_v1.jsonl \
  --manifest benchmarks/t2s/manifests/t2s_eval_v1_manifest.json
```

The selector is deterministic and defaults to:

```text
S1 Basic / single-table      25
S2 One-join                  30
S3 Complex                   30
S4 Advanced SQL constructs  15
TOTAL                       100
```

`BIRD difficulty` (`simple/moderate/challenging`) is retained separately. T2S structural strata are **not** claimed to be official BIRD difficulty labels.

## Validate

```bash
python benchmarks/t2s/scripts/validate_benchmark.py \
  --dataset benchmarks/t2s/datasets/t2s_eval_v1.jsonl \
  --exclude-jsonl /path/to/t2s_pilot_v1.jsonl \
  --expected-count 100 \
  --require-all-bird-dbs
```

## Verify official gold executes on your local BIRD SQLite databases

```bash
python benchmarks/t2s/scripts/verify_gold_execution.py \
  --dataset benchmarks/t2s/datasets/t2s_eval_v1.jsonl \
  --db-root /path/to/dev_databases \
  --output benchmarks/t2s/manifests/t2s_eval_v1_gold_execution.json
```

## Temporary model backend

The benchmark protocol is provider-agnostic. While the OSS backend is unavailable, use the temporary OpenAI-compatible backend through configuration/environment variables. Do not commit API keys.

Recommended runtime convention (adapt names to the repo's existing config contract):

```bash
export T2S_LLM_PROVIDER=openai_compatible
export T2S_LLM_MODEL='<temporary-chat-5-mini-alias>'
export OPENAI_API_KEY='...'
```

Record the resolved provider/model alias in every run manifest; never store the API key.

## Primary metric

For answerable BIRD cases, the primary end-to-end metric is **Execution Accuracy (EX)** using the local SQLite BIRD database. Report it overall and by T2S stratum, BIRD difficulty, and database.

S5 robustness cases use abstention/clarification metrics and are never mixed into SQL EX.
