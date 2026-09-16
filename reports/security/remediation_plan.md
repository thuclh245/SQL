# Architecture Hygiene & Remediation Plan

## Objective

Establish a permanent, automated governance architecture that prevents benchmark contamination, scientific leakage, and phase-coupling across the lifecycle of the T2S Text-to-SQL system.

---

## 1. Remediation Matrix

| Category | Vulnerability Identified | Action Taken | Current State | Continuous Verification |
| :--- | :--- | :--- | :--- | :--- |
| **A: Benchmark Hardcoding** | Specific BIRD table/column heuristics in `p4_validator.py` and phrases in `shadow_evaluator.py` | Removed dataset-specific rules; retained AST invariants; renamed to `sql_semantic_risk_validator.py` | Sanitized | Guard B automated CI test |
| **B: Dependency Boundary** | `runtime_factory.py` imported `load_bird_catalog_tables` from `benchmark/` | Removed unused import; routed manifest loading through `t2s.catalog` | Sanitized | Guard A automated CI test |
| **C: Gold Data Isolation** | Potential risk of gold fields entering runtime | Enforced `extra="forbid"` on `ValidationInput` and runtime requests | Isolated | Guard C automated CI test |
| **D: Prompt Hygiene** | Risk of few-shot contamination in prompt builders | Verified prompt templates use strictly dynamic schema contexts | Clean | Guard D automated CI test |
| **G: Phase Name Coupling** | Production classes/files named `P4DeterministicValidator`, `p4_validator_outcome`, etc. | Full refactoring to neutral architectural names (`SqlSemanticRiskValidator`, etc.) | Neutralized | Guard B automated CI test |
| **K: Secret Hygiene** | Presence of local `.env` with developer API keys | Confirmed `.gitignore` exclusions; scanned git tracking index | 0 secrets in git | Guard E automated CI test |

---

## 2. Architectural CI Guards (Automated Enforcement)

The repository enforces architectural boundaries via `tests/unit/architecture/test_architecture_hygiene_guards.py`:

```text
Guard A: Dependency Boundary Guard
- Scans AST of all production modules in src/t2s (excluding benchmark/ and evaluation/)
- Asserts 0 imports from t2s.benchmark, t2s.evaluation, tests, or scripts.

Guard B: Production Naming & Benchmark Hygiene Guard
- Scans all lines in production modules
- Asserts 0 occurrences of phase tokens (\b[PE]\d+\b, \bp8e\d+\b)
- Asserts 0 occurrences of benchmark names (bird, dev100, mini_dev, spider).

Guard C: Gold Isolation Guard
- Asserts ValidationInput and runtime DTOs reject gold_sql, gold_answer, gold_tables, ground_truth.

Guard D: Prompt Hygiene Guard
- Asserts prompt templates contain 0 benchmark schema references or static few-shots.

Guard E: Secret Scan Guard
- Scans all tracked git files (git ls-files) for API key patterns (sk-...).
```

---

## 3. Governance Policy for Future Work

1. **Absolute Phase-Neutral Naming**:
   - Production code, public APIs, configurations, and prompts must never receive names derived from research sprints or experiment numbers.
   - All historical research notes must be contained in `docs/research/` or `reports/`.

2. **Zero Paid LLM Calls Without Independent Validation**:
   - No paid API calls or benchmark evaluations may be launched against BIRD Mini-Dev or uncertified holdout sets.
   - The production validator remains in `SHADOW` mode (`DEFAULT_MODE = SHADOW`, `ENFORCEMENT_AUTHORIZED = NO`).

3. **Independent Data Certification Required**:
   - Before any validator rules may be considered for `ENFORCE` mode, they must be validated on an independently certified dataset (e.g., Enterprise Olist) that has zero exposure to the rule designers.
