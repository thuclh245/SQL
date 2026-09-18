# 10 — Risks, Limitations and Unknown Unknowns

**Version:** 2.0

---

## 1. Risk model

T2S must assume that executable SQL may still be semantically wrong.

The system goal is not to eliminate all uncertainty; it is to prevent uncertainty from silently becoming a confident wrong answer.

---

## 2. Project-specific risks

| Risk | Detection | Mitigation | Fallback |
|---|---|---|---|
| wrong join | AST/relationship checks, semantic audit | certified relationship evidence | abstain |
| fan-out | grain/cardinality checks, result anomalies | future certified grain capability | caveat/abstain |
| wrong literal | value evidence check | certified Value Grounding | clarify/abstain |
| temporal error | temporal challenge tests | certified Temporal Grounding | abstain |
| wrong denominator | metric/grain evidence | future metric semantics | clarify |
| lucky match | counterexample mutation | adversarial fixtures | reject metric claim |
| stale metadata | version/freshness checks | resync | abstain |
| schema drift | metadata diff | refresh projection/index | abstain |
| business ambiguity | ambiguity detection | glossary / clarification | clarify |
| unauthorized access | independent authorization check | deny wins | deny |
| provider nondeterminism | replicate tracking | stable configs, fingerprints | caveat |
| evaluation leakage | provenance audit | strict gold isolation | invalidate experiment |
| missing run artifacts | governance check | persistence invariant | mark invalid |

---

## 3. Known unknowns

- real company-domain semantic accuracy,
- production metadata quality,
- unseen-domain behavior,
- large catalog retrieval,
- multi-dialect behavior,
- provider/model drift,
- long-tail business vocabulary,
- true MG* → OR* gap,
- conditional 120B solver ceiling.

---

## 4. Unknown-unknown containment

Design rule:

```text
uncertainty detected
→ seek bounded evidence
→ if unresolved
→ clarify / caveat / abstain
```

Never:

```text
uncertainty
→ hallucinate missing semantic rule
→ execute confidently
```

