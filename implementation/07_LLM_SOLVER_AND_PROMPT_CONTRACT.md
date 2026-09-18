# 07 — LLM Solver and Prompt Contract

## 1. vLLM adapter

Use the OpenAI-compatible API exposed by the company vLLM endpoint. `gpt-oss-120b` supports configurable reasoning effort and structured outputs; current vLLM supports `response_format`/`structured_outputs`, and gpt-oss output parsing uses Harmony-aware support. [R1–R4]

Do not code against deprecated `guided_json`.

## 2. Structured output

Return a minimal schema:

```json
{
  "sql": "SELECT ...",
  "dialect": "clickhouse",
  "expected_columns": ["region", "net_revenue"],
  "assumptions": [],
  "unresolved": []
}
```

If structured-output enforcement fails operationally, treat it as a generation failure and retry only under a bounded policy; do not regex-extract arbitrary SQL from untrusted prose as the default.

## 3. Prompt structure

```text
SYSTEM
- You are a read-only enterprise SQL solver.
- Use ONLY authorized schema/evidence supplied below.
- Do not invent tables, columns, business definitions or literal values.
- If critical evidence is missing, record it in unresolved.
- Produce exactly one read query for the requested dialect.
- Follow output schema.

DEVELOPER CONTEXT
- dialect rules
- output shape constraints
- selected schema/columns
- relationships + provenance
- grounded values/business terms
- validated examples (small number)

USER
- original question
```

Do not ask the model to enforce security; security is enforced before and after the call.

## 4. Prompt budgeting

Prioritize context in this order:

1. question/instructions;
2. selected table/column types;
3. joins/keys and business evidence;
4. grounded values/time;
5. validated examples;
6. descriptions only for relevant entities.

Never use the 131k context window as permission to dump the entire 9,000-table catalog. Large context can increase noise and cost even when it fits.

## 5. Reasoning effort policy

Initial policy:

- easy/single-table -> medium;
- complex aggregate/multi-join -> high;
- escalation candidate -> high.

This is a starting policy, not a fixed truth. Log reasoning-effort mode and measure accuracy/latency by complexity slice.

## 6. Candidate generation

v1 generates **one direct-SQL candidate**. Alternative candidates are enabled only after baseline/error analysis.

When enabled, candidate B must differ by strategy or new evidence; repeated sampling of identical context/prompt is not treated as independent evidence.

## 7. Targeted repair

Repair is allowed only when there is concrete diagnosis, e.g.:

- DB says unknown column;
- dialect rejects syntax;
- value is proven nonexistent;
- verifier identifies a specific missing condition.

Repair request contains the original question/context, previous SQL and **only the observed failure evidence**. `max_repairs` should start at 1.

## 8. LLM output logging

Persist final structured output and token/latency metadata. Avoid treating or exposing private reasoning traces as product explanations; store concise assumptions/evidence summaries instead, following company logging/privacy policy.
