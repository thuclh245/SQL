# 10 — Evidence Register

## Evidence taxonomy

Evidence status used throughout:
[E] externally or internally measured evidence; [I] hard technical/security invariant; [S] strong engineering inference that still requires measurement; [H] open hypothesis/candidate mechanism.

## Internal measured evidence

### I1 — Stable error taxonomy from the prior Text2sql project

106 stable wrong cases: wrong_row_set 40.6%, wrong_metric_or_formula 38.7%, width_delta 32.1%, join_type_delta 23.6%, fan_out 15.1%. Use as prior evidence, not as the production error distribution.

### I2 — Literal validity association

EX 5.81% when predictions contained nonexistent literals vs 48.67% when all literals existed. Strong predictive association; not a causal +43pp improvement claim.

### I3 — Generic post-generation repair negative evidence

Five negative results around SQL refinement; one treatment/control comparison produced byte-identical SQL on 855 predictions. Generic self-reflection without new evidence should not be a default loop.

### I4 — Same-prompt resampling ceiling

k=3 oracle at_least_one_correct improved only +4.68pp over single run; 39.6% of cases were never correct. Motivates testing genuinely diverse strategies rather than repeated sampling.

### I5 — Column-description prompt arm

Adding descriptions to generation prompt reduced EX by 0.70pp while raising cost by 23.1%. This supports using descriptions primarily for retrieval/context selection, not blindly injecting all descriptions.

### I6 — Output minimality

The retained arm improved EX by 1.75pp and reduced over-selection. Supports deterministic projection/output-shape checks where possible.


## External sources

### S1 — OpenAI — gpt-oss-120b model documentation

117B total / 5.1B active parameters, reasoning effort, agentic capabilities, structured outputs.

Source: https://developers.openai.com/api/docs/models/gpt-oss-120b

### S2 — OpenAI — gpt-oss model card

Open-weight reasoning model designed for agentic workflows, tool use and structured outputs.

Source: https://openai.com/index/gpt-oss-model-card/

### S3 — vLLM — Structured Outputs

Structured output generation; deprecated guided_json replaced by structured_outputs.

Source: https://github.com/vllm-project/vllm/blob/main/docs/features/structured_outputs.md

### S4 — vLLM — Automatic Prefix Caching

Prefix reuse lowers prefill cost but does not reduce decoding time.

Source: https://github.com/vllm-project/vllm/blob/main/docs/features/automatic_prefix_caching.md

### S5 — CHASE-SQL — ICLR 2025

Multi-path candidate generation and candidate selection; evidence that diverse reasoning paths can improve Text-to-SQL.

Source: https://proceedings.iclr.cc/paper_files/paper/2025/hash/974ff7b5bf08dbf9400b5d599a39c77f-Abstract-Conference.html

### S6 — Agentar-Scale-SQL — 2025

Orchestrated test-time scaling combining sequential, parallel and internal scaling; reports 81.67% BIRD test EX.

Source: https://arxiv.org/abs/2509.24403

### S7 — AutoLink — AAAI 2026

Iterative agent-driven schema exploration; high strict schema-linking recall on BIRD and Spider 2.0-Lite, including large-schema settings.

Source: https://ojs.aaai.org/index.php/AAAI/article/view/40672

### S8 — PV-SQL — Findings of ACL 2026

Database probing plus rule-based verification; reports +5% EX over its strongest baseline and lower token use.

Source: https://aclanthology.org/2026.findings-acl.1286/

### S9 — VET — Findings of ACL 2026

Step-wise executable reasoning against the database; emphasizes observable intermediate evidence.

Source: https://aclanthology.org/2026.findings-acl.1544/

### S10 — DPC — ACL 2026

Training-free candidate selection using cross-paradigm consistency; warns about self-consistency and LLM-judge shared blind spots.

Source: https://aclanthology.org/2026.acl-long.313/

### S11 — Selective Prediction Study — 2026 preprint

Reasoning-based verification signals predict correctness better than simple executability/self-consistency in the reported experiments; preprint, so treat as suggestive evidence.

Source: https://arxiv.org/abs/2607.06799

### S12 — Spider 2.0 — official repository

Enterprise-style Text-to-SQL workflows across Snowflake/BigQuery/SQLite, illustrating large-schema/tool-workflow difficulty.

Source: https://github.com/xlang-ai/Spider2

### S13 — Wren AI — Architecture

Open context layer: MDL, memory, planning, validation, connectors and query history.

Source: https://docs.getwren.ai/oss/reference/architecture

### S14 — Wren AI — CLI Reference

dry-plan, dry-run, schema/memory tools and SQL execution primitives.

Source: https://docs.getwren.ai/oss/reference/cli

### S15 — Wren AI — MDL

MDL as semantic contract describing business meaning, relationships and reusable calculations.

Source: https://docs.getwren.ai/oss/engine/concept/what_is_mdl

### S16 — Vanna 2.0 — archived repository

User-aware agent framework; repository archived 2026-03-29, so useful as reference but risky as a new core dependency without a maintenance plan.

Source: https://github.com/vanna-ai/vanna/blob/main/README.md?plain=1

### S17 — DB-GPT — GitHub

Agentic data analysis platform with tool execution, multi-source access and skills; useful as runtime/orchestration reference.

Source: https://github.com/eosphoros-ai/DB-GPT

### S18 — OpenMetadata — Data asset details

Schema descriptions, glossary/tags, sample data, queries, profiler and lineage are available depending on ingestion/configuration.

Source: https://docs.open-metadata.org/v1.12.x/how-to-guides/guide-for-data-users/data-asset-tabs

### S19 — OpenMetadata — Table relationships

Join information can include joined columns and join counts.

Source: https://docs.open-metadata.org/v1.12.x/api-reference/data-assets/tables/relationships

### S20 — OpenMetadata — Data Profiler

Column/table statistics for value/evidence grounding, subject to profiler enablement and cost.

Source: https://docs.open-metadata.org/v1.12.x/how-to-guides/data-quality-observability/profiler

### S21 — OpenMetadata — Discovery

Elasticsearch-backed keyword discovery, usage and relationship-based discovery.

Source: https://docs.open-metadata.org/v1.12.x/how-to-guides/data-discovery/discover


## Evidence-use rules

- Do not convert an association into a causal gain claim.
- A paper result establishes feasibility/evidence in its setting, not guaranteed transfer to the company estate.
- Preprints are labeled weaker than peer-reviewed/official documentation.
- Framework capability documentation proves the capability exists, not that it improves T2S accuracy.
- Production decisions require local benchmark/shadow evidence.
