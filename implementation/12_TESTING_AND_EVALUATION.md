# 12 — Testing and Evaluation

## 1. Test pyramid

### Unit

- parsers and SQL policy;
- authorization filter;
- context serializer/budgeter;
- risk rules;
- action-budget accounting;
- result fingerprints.

### Contract

Each adapter must pass common tests:

- `CatalogPort` returns normalized entities/provenance;
- `LLMPort` returns valid `SolverOutput` or typed failure;
- `DatabaseGateway` rejects writes and enforces timeouts;
- `AuthorizationPort` is fail-closed.

### Integration

Run against disposable PostgreSQL plus test ClickHouse/StarRocks where available, test OpenMetadata, and a stub/mock vLLM for deterministic CI.

### Security

Bypass/unauthorized FQN, prompt injection, dangerous SQL functions, multi-statement SQL, direct DB mutation, stale-cache scope leakage.

### Regression/evaluation

Reuse the existing T2S evaluation harness where possible. Every experiment stores config, code revision, model, dataset split and artifacts.

## 2. Golden workflow tests

Minimum end-to-end cases:

1. simple single-table lookup;
2. aggregate + date filter;
3. two-table join;
4. unresolved literal -> probe -> success;
5. missing schema -> expand -> success;
6. unauthorized requested table -> abstain/refuse without leak;
7. SQL parse error -> one targeted repair;
8. DB timeout -> safe failure;
9. true ambiguity -> ambiguous;
10. budget exhausted -> abstain.

## 3. Offline evaluation CLI

```bash
t2s eval run   --dataset eval/datasets/dev.jsonl   --config configs/baseline.yaml   --output results/run_YYYYMMDD
```

Manifest includes git SHA, dirty flag, model/vLLM, prompt hash, metadata/index version, SQLGlot version, dialect adapter version and random seed where relevant.

## 4. Metrics

Primary: precision/coverage/risk curve. Also report raw EX, fixed/broke cases, error taxonomy, retrieval recall, latency/token/warehouse cost and security failures.

## 5. Evaluation discipline

A 100–200-case stratified working set is fine for development, but keep a locked holdout and larger benchmark sanity checks. Do not tune thresholds and then report the same cases as independent evidence.

## 6. Mechanism keep/drop rule

A mechanism is kept only if it improves production utility without unacceptable regressions. Example questions:

- Does schema exploration fix retrieval failures without breaking easy cases?
- Does a second solver create genuinely new correct candidates?
- Does an LLM verifier improve selective precision after accounting for false rejects?
- Does semantic/Wren reduce metric/join errors enough to justify modeling/ops cost?
