# 09 — Evidence-Gated Roadmap

**Version:** 2.0

---

## 1. Roadmap principle

The roadmap is selected by audited error mass, not by feature popularity.

---

## 2. Current state

```text
MG0
+
P2-R2 canonical semantic baseline
```

Architecture direction: **SUPPORTED**.

---

## 3. Next committed step

### Temporal Grounding isolated certification experiment

Entry conditions:

- P2-R2 complete,
- canonical A–F taxonomy established,
- deployable defaults frozen,
- unseen temporal challenge set frozen.

Control:

```text
MG baseline without Temporal Grounding
```

Treatment:

```text
same baseline + Temporal Grounding
```

Only one causal variable changes.

Exit:

- CERTIFY
- KEEP_SHADOW
- REJECT
- INCONCLUSIVE

---

## 4. After Temporal experiment

Recompute D/E error mass.

The next capability is selected only then.

Potential candidates:

- Value Grounding,
- Grain/Cardinality Grounding,
- metric/denominator semantics,
- relationship reasoning,
- bounded syntax repair.

None is pre-committed.

---

## 5. MG* formation

```text
MG* = MG0 + certified capabilities only
```

When enough capabilities are certified, freeze MG* and compare against OR*.

---

## 6. OR* and solver ceiling

OR* is diagnostic only.

If:

```text
MG* ≈ OR*
```

then remaining gap increasingly points toward solver/reasoning/evaluation limits.

If:

```text
MG* << OR*
```

then grounding remains the primary improvement area.

---

## 7. Future, not committed

- enterprise-scale retrieval stress tests,
- multi-dialect generalization,
- semantic runtime branch,
- multi-solver/planner experiments,
- large-scale agentic orchestration.

These require separate evidence gates.

---

## 8. Enterprise pilot entry gate

Pilot only after:

- OpenMetadata integration verified,
- authorization end-to-end verified,
- MG* candidate frozen,
- evaluation artifacts complete,
- n8n integration verified,
- warehouse execution controls verified,
- rollback/incident procedure defined.

