# 11 — Decision Log and Open Hypotheses

## Accepted principles

| Decision | Status | Basis |
|---|---|---|
| Requirements-first, architecture-neutral | Accepted | Production objective |
| Security/read-only below LLM | Accepted | [I] security invariant |
| Direct SQL as first baseline/mainline | Accepted for baseline | Lowest-assumption comparison path |
| Full-schema prompt at ~9,000 tables | Rejected | Context/noise/scalability constraint |
| Generic unbounded self-reflection loops | Rejected as default | Internal negative evidence + operability |
| Semantic model mandatory | Rejected | Must win comparative evaluation |
| IR mandatory | Rejected | Optional candidate only |
| Public-system reuse | Preferred when fit | Maintenance/commodity engineering rationale |

## Open hypotheses

### H1 — Adaptive orchestration beats a fixed workflow

**Why plausible:** easy questions need less compute; hard cases may benefit from targeted evidence.  
**How to test:** fixed-core vs adaptive escalation, report precision/coverage/latency/GPU/DB load.  
**Reversal:** if quality gain is small or instability/operational cost dominates, keep fixed workflow.

### H2 — Agentic schema exploration is needed at company scale

**Evidence:** AutoLink shows strong large-schema linking results.  
**Local test:** hierarchical static retrieval vs bounded exploration on the same catalog.  
**Reversal:** if static retrieval meets required recall with less complexity, do not deploy exploration agents.

### H3 — Safe database probing improves production accuracy enough to justify warehouse cost

**Evidence:** PV-SQL/VET show value in benchmark settings.  
**Test:** no-probe vs targeted-probe on value/schema-uncertain cases.  
**Reversal:** if extra load/latency exceeds quality gain, restrict probes to offline/shadow or disable.

### H4 — Multiple 120B solver strategies create useful independent diversity

**Evidence:** CHASE-SQL/Agentar support diverse test-time scaling; internal same-prompt resampling has limited ceiling.  
**Test:** effective semantic/result diversity and selected accuracy.  
**Reversal:** if candidates are highly correlated, use one solver plus verification.

### H5 — Independent 120B semantic verification improves selective accuracy

**Evidence:** 2026 selective-prediction preprint is encouraging; DPC warns about judge/shared biases.  
**Test:** correctness-prediction AUROC/calibration plus final risk–coverage.  
**Reversal:** if judge adds little predictive value, retain deterministic/DB evidence only.

### H6 — Wren/semantic context improves business-semantic accuracy or maintenance

**Evidence:** Wren provides semantic/runtime primitives, not accuracy proof for this estate.  
**Test:** raw direct vs semantic context vs semantic runtime.  
**Reversal:** if not materially better, keep semantic branch out of the production critical path.

### H7 — Full typed IR adds enough semantic verification/portability value

**Test:** direct SQL vs sidecar/IR under same model/context.  
**Reversal:** if IR reduces expressiveness/accuracy or adds maintenance without compensating benefit, reject.

## Decision discipline

No hypothesis becomes architecture dogma merely because it is theoretically elegant or appears in a strong paper. Local evidence decides production adoption.
