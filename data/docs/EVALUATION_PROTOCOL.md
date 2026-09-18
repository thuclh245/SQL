# T2S Evaluation Protocol v1

## Required run manifest

Every run must record:

- benchmark name/version;
- source BIRD SHA256 and evaluation-manifest SHA256;
- git commit and dirty/clean state;
- provider and model alias;
- prompt version;
- temperature / seed where supported;
- P3 grounding budget;
- P5 escalation budget;
- database dialect;
- start timestamp;
- whether oracle BIRD evidence is enabled;
- whether any corrected gold is used.

Do not store credentials.

## Temporary LLM backend

While OSS inference is unavailable, T2S may run through the temporary OpenAI-compatible Chat 5 mini endpoint. Provider selection must remain configuration-driven. API keys belong in environment/secret storage only.

For comparability, do not mix provider/model versions within one benchmark run.

## Primary end-to-end metric

### Execution Accuracy (EX)

For answerable BIRD cases:

```text
EX = correctly executed result-equivalent cases / evaluated cases
```

Use the official BIRD evaluator when available. Do not replace EX with exact SQL string match.

Report:

- overall EX;
- EX by T2S stratum S1–S4;
- EX by BIRD difficulty;
- EX by database;
- database macro-average EX.

## Grounding metrics

Where gold table/column references can be extracted from gold SQL:

- Table Recall@K
- Column Recall@K
- relationship/join-path coverage
- average selected tables
- average selected columns
- grounding latency

A SQL error should be attributed to grounding only when required schema evidence was missing/incorrect before generation.

## P5 orchestration metrics

- escalation rate;
- success-after-escalation rate;
- unnecessary escalation rate;
- average grounding calls;
- average solver calls;
- same-context stop rate.

## Safety/runtime metrics

- safety rejection count;
- access rejection count;
- execution failure count;
- timeout count;
- result-limit count.

## Cost/latency

- model input tokens;
- output tokens;
- model calls/case;
- end-to-end latency;
- grounding latency;
- solver latency;
- execution latency;
- estimated cost if provider exposes pricing.

## Failure taxonomy

Assign exactly one primary failure stage, plus optional secondary labels:

```text
GROUNDING_TABLE
GROUNDING_COLUMN
GROUNDING_RELATIONSHIP
VALUE_FILTER
BUSINESS_SEMANTIC
SQL_GENERATION
SAFETY_REJECTED
ACCESS_REJECTED
EXECUTION_ERROR
TIMEOUT
GOLD_OR_EVAL_DEFECT
UNRESOLVED_CORRECTLY
OTHER
```

## Robustness S5 metrics

Never combine S5 with EX.

Report:

- clarification accuracy (ambiguous);
- correct abstention rate (out_of_scope);
- unsafe overreach rate;
- false-answer rate.

## Comparing two variants

Run A and B on the exact same frozen case IDs. Report:

- paired win/loss/tie counts;
- delta EX overall and by slice;
- cases fixed;
- cases regressed;
- model-call and latency delta.

For statistical inference on paired binary correctness, use a paired test such as McNemar when sample size is adequate. With N=100, interpret small deltas cautiously.
