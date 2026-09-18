# T2S Evaluation Integration Guide

## Suggested project placement

```text
benchmarks/t2s/
    datasets/
    configs/
    manifests/
    results/
    scripts/
    docs/
```

## Runtime adapter contract

The benchmark runner should map a case into the existing T2S runtime without allowing gold fields to enter inference:

```text
INFERENCE INPUT
question
evidence (only if the experiment explicitly enables BIRD oracle evidence)
db_id
user identity / authorization fixture

NEVER INPUT TO MODEL/GROUNDING
sql_original
sql_corrected
BIRD difficulty
gold stratum
execution result
expected correctness
```

Gold is loaded only by the evaluator after prediction is finalized.

## Suggested CLI

```bash
t2s benchmark run \
  --dataset benchmarks/t2s/datasets/t2s_eval_v1.jsonl \
  --db-root /path/to/BIRD/dev_databases \
  --output benchmarks/t2s/results/<run_id>.jsonl

# Score separately after inference
t2s benchmark score \
  --dataset benchmarks/t2s/datasets/t2s_eval_v1.jsonl \
  --predictions benchmarks/t2s/results/<run_id>.jsonl
```

If the project does not yet expose these commands, implement them as thin adapters over existing P3/P4/P5/P6 components. Do not duplicate the runtime pipeline inside benchmark code.

## Secrets and provider config

Temporary model backend:

```text
provider = OpenAI-compatible
model    = supplied by T2S_LLM_MODEL
key      = environment/secret only
```

The benchmark dataset and result files must never contain the API key.

## Result record

Use `schemas/run_result.schema.json`. One record per case. Prediction records should preserve stage timings and orchestration traces needed for failure attribution.

## Reproducibility

Before a checkpoint run:

1. validate dataset;
2. verify gold execution against the exact local BIRD DB snapshot;
3. record source checksum;
4. record git commit;
5. freeze provider/model/prompt/config;
6. run inference exactly once for the sealed evaluation checkpoint;
7. score after all predictions are complete.
