# 15 — Optional Extension Points

These are explicitly **not required for the first working production baseline**.

## 1. Alternative solver

Implement `SolverStrategy`:

```python
class SolverStrategy(Protocol):
    name: str
    async def generate(self, req: SolverRequest) -> SolverOutput: ...
```

Candidates: direct, divide-and-conquer, relational-plan reasoning, metric-first. The orchestrator chooses at most the allowed strategies.

## 2. Independent semantic verifier

Implement behind `SemanticVerifierPort`. It receives question + grounded evidence + candidate SQL + diagnostics, never generator private reasoning. Its output is a feature/finding, not a final decision.

## 3. Semantic runtime / Wren

Add:

```python
class SemanticRuntimePort(Protocol):
    async def context(self, req: SemanticContextRequest) -> SemanticContext: ...
    async def plan_or_compile(self, req: SemanticQueryRequest) -> SemanticRuntimeResult: ...
```

Compare raw schema/direct SQL with semantic context/runtime using the same verification, DB gateway and risk policy. Do not require all 9,000 tables to be modeled up front.

## 4. Typed IR

If tested, keep it behind a strategy/port:

```text
Grounding -> IR Solver -> Compiler -> common verification -> common DB gateway
```

Do not allow IR to become a dependency of grounding/security/evaluation until it wins empirically.

## 5. Dense retrieval/reranker

`EmbeddingPort` and `RerankerPort` must be independently replaceable. If no approved embedding model exists, lexical retrieval must still produce a valid baseline.

## 6. Learned risk model

Replace heuristic `RiskPolicyV0` with a calibrated model only after enough labeled data exists. Keep feature logging backward-compatible so historic runs can train/replay the model.

## 7. Multi-turn clarification

Not required for v1. The system may return a specific `ambiguous` response. Interactive continuation can later be implemented as a separate conversation state capability without changing SQL safety/grounding contracts.
