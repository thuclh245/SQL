# 01 — Product Contract

## 1. Business problem

A business user asks a question in Vietnamese or English. The system must use only data the user is allowed to access and produce one of three outcomes:

- **Answer:** result + SQL + concise explanation + confidence/evidence summary.
- **Ambiguous:** state the *specific unresolved point*; interactive follow-up may remain a later UX feature.
- **Abstain:** decline when evidence is insufficient, out of scope, unsafe, or budget is exhausted.

The worst failure mode is **wrong-but-plausible output**: executable SQL whose result is semantically wrong but looks credible.

## 2. Production context

- Catalog scale: approximately 9,000 tables across multiple databases/domains.
- Metadata: OpenMetadata, with actual coverage of descriptions, query history, profiler, lineage, joins and glossary to be measured in the target environment.
- SQL engines: ClickHouse, StarRocks, PostgreSQL; SQLite/public benchmarks remain evaluation infrastructure.
- Model ceiling: company-hosted `gpt-oss-120b` via vLLM; accuracy has priority over latency; no fine-tuning assumed.
- Primary language: Vietnamese, with English support.
- Access: user/department aware; DB role/RLS/read-only enforcement belongs below the LLM.

## 3. Product objective

The objective is not maximum raw execution accuracy at any cost and not maximum refusal. It is:

> **Maximize trustworthy answer coverage subject to a required precision/reliability constraint.**

The current internal gate `precision >= 85% at coverage >= 55%` is retained as an **initial acceptance hypothesis**, not a universal production SLA. It must be validated with business owners and real traffic.

## 4. Design principles

1. **Problem before method.** A component must map to a measured failure mode or hard requirement.
2. **Evidence before confidence.** LLM self-confidence is not accepted as a correctness probability.
3. **Security below the LLM.** ACL/read-only/RLS are infrastructure guarantees.
4. **Simple before complex.** Direct SQL + strong grounding is the baseline; agentic/semantic/IR mechanisms must earn their complexity.
5. **Bounded recovery.** Loops are allowed only when they can obtain new evidence or an independent solution path.
6. **Replaceable components.** Public systems may be wrapped or reused; avoid framework lock-in.
7. **Measure production utility.** Accuracy, coverage, reliability, operational cost and maintainability determine keep/reject decisions.

## 5. Non-goals for the first production scope

- Write/update/delete data.
- Unbounded autonomous agents.
- Mandatory multi-turn conversational state.
- Mandatory semantic-layer modeling of all 9,000 tables.
- Fine-tuning the 120B model.
- Building infrastructure that existing maintained OSS already solves adequately without measured benefit.
