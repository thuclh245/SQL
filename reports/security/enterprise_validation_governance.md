# Enterprise Validation Provenance Reconciliation & Gold Governance Report

**Document ID**: `T2S-GOV-ENT-VAL-2026-09`  
**Audit Date**: September 15, 2026  
**Auditor**: Independent T2S Governance & Audit Agent  
**Execution Context**: `/home/thuclh245/MyCode/SQL`  
**Target Environments**: PostgreSQL 18.4 (`ecommerce_db`, Port 5432) & PostgreSQL 16.15 (`qddd_olist`, Port 5433)  
**Verification Standard**: Strict Zero-Leakage, Tri-State Actor Exposure, Dual-Role Separation of Duties  

---

## 1. Executive Summary

This governance audit reconciles the provenance, authorship, actor exposure, certification state, and readiness of the staged candidate enterprise validation pool for the T2S (Text-to-SQL) system.

The core objective is to ensure that any prospective validation suite is scientifically valid, free from contamination, completely separated from internal model/prompt tuning, and backed by certified ground truth.

### Key Governance Determinations

| Governance Metric | Audit Finding | Certification Status |
| :--- | :---: | :---: |
| **Repository Hygiene Status** | `COMPLETE` | **PASSED** (307/307 unit tests pass, 0 lint/mypy errors, no hardcoded benchmark logic) |
| **Validation Data Governance Status** | `PARTIAL_COHORT_REQUIRES_GOLD_REVIEW` | **REQUIRES REMEDIATION** |
| **Total Enterprise Cases Discovered** | `60` | 20 in `ecommerce_db`, 40 in `qddd_olist` |
| **Certified Independent Cases** | `0` | **ZERO CASES CURRENTLY CERTIFIED** |
| **Independent Validation Permitted** | `BLOCKED` | **BLOCKED** until gold authoring & dual-role signoff are complete |
| **Production Enforcement Authorized** | `NO` | **PROHIBITED** |
| **Paid LLM Calls Consumed** | `0` | **ZERO PAID API CALLS** |
| **Protected Data Exposure** | `NONE` | Zero question text or gold queries leaked into public logs |

---

## 2. Inventory of Candidate Validation Sources

The audit identified a total pool of **60 candidate cases** originating from two distinct sources:

```
Total Enterprise Pool: 60 Candidate Cases
│
├── Source A: ai-dd-t2s Canonical Business Suite (20 Cases)
│   ├── Target Database: ecommerce_db (Port 5432, PostgreSQL 18.4)
│   ├── Schema: 12 tables (public schema)
│   ├── Language: Vietnamese (vi)
│   ├── Staged Path: benchmarks/t2s/independent_validation/
│   └── Current State: 20/20 Gold Authored, 20/20 Runnable, 0 Certified
│
└── Source B: ChatSQL Olist E-Commerce Benchmark (40 Cases)
    ├── Target Database: qddd_olist (Port 5433, PostgreSQL 16.15)
    ├── Schema: 9 tables (core schema)
    ├── Language: English (en)
    ├── Source Path: /home/thuclh245/MyCode/ChatSQL/data/benchmark/cases/
    └── Current State: 34/40 Gold Authored, 33/40 Runnable, 1 Defect, 6 Missing, 0 Certified
```

### Database Environment Details

1. **`ecommerce_db` (Canonical Suite)**:
   - **Engine**: PostgreSQL 18.4-1.pgdg13+1 (Debian container `ecommerce_postgres`).
   - **Port**: `5432`.
   - **Container State**: `Up 2 days (healthy)`.
   - **Tables (12)**: `addresses`, `categories`, `customers`, `order_items`, `order_promotions`, `orders`, `payments`, `products`, `promotions`, `reviews`, `shipments`, `suppliers`.
   - **Schema Fingerprint**: Verified against recorded SHA-256 digest (`87cb5c6507ffde0cf8215d27ba568664a3c895110274f475e199858466005946`).

2. **`qddd_olist` (Olist Benchmark Suite)**:
   - **Engine**: PostgreSQL 16.15 (Alpine container `chatsql_postgres`).
   - **Port**: `5433`.
   - **Container State**: `Up 7 hours`.
   - **Tables (9, core schema)**: `customers`, `geolocation`, `order_items`, `order_payments`, `order_reviews`, `orders`, `product_category_translation`, `products`, `sellers`.
   - **Schema Fingerprint**: Verified against recorded SHA-256 digest (`0fee58ea162618524ed6e769106e0157974c2f5516e723a0188bab310d32de2f`).

---

## 3. Gold SQL Status & Availability Breakdown

Ground-truth Gold SQL status across the 60 cases is categorized as follows:

| Metric | `ecommerce_db` (Source A) | `qddd_olist` (Source B) | Total Aggregate | Percentage |
| :--- | :---: | :---: | :---: | :---: |
| **Total Candidates** | 20 | 40 | **60** | 100.0% |
| **Gold SQL Authored** | 20 | 34 | **54** | 90.0% |
| **Gold SQL Missing** | 0 | 6 | **6** | 10.0% |
| **Gold SQL Runnable** | 20 | 33 | **53** | 88.3% |
| **Execution Defects** | 0 | 1 | **1** | 1.7% |
| **Semantically Reviewed** | 0 | 0 | **0** | 0.0% |
| **Independently Certified** | 0 | 0 | **0** | 0.0% |

### Identified Defect & Gap Registry

1. **Missing Gold Queries (6 Cases)**:
   - `OLIST-0035`, `OLIST-0036`, `OLIST-0037`, `OLIST-0038`, `OLIST-0039`, `OLIST-0040`.
   - *Impact*: These cases cannot be evaluated until valid reference SQL is authored and verified.
2. **Schema Name Typo (1 Case)**:
   - `OLIST-0017`: Query references table `core.category_translation` instead of `core.product_category_translation`.
   - *Impact*: Fails execution on PostgreSQL 16 with error `relation "core.category_translation" does not exist`.

---

## 4. Reconciling the "Uninspected" Holdout Contradiction

Previous research memos contained an apparent contradiction:
- *Statement 1*: "40 staged holdout cases are completely uninspected."
- *Statement 2*: "34/40 Gold SQL queries are authored and 33/40 are execution-verified."

### Resolution: Multi-Actor Exposure Disambiguation

The term "uninspected" was applied imprecisely. Exposure must be evaluated across distinct actors and systems:

| Exposure Dimension | Source A (`ecommerce_db`, 20) | Source B (`qddd_olist`, 40) |
| :--- | :---: | :---: |
| **Production Solver Execution** | `NO` (0/20) | `NO` (0/40) |
| **Production Semantic Validator Execution** | `NO` (0/20) | `NO` (0/40) |
| **LLM Verifier Execution** | `NO` (0/20) | `NO` (0/40) |
| **T2S Prompt Tuning Exposure** | `NO` (0/20) | `NO` (0/40) |
| **T2S Grounding Rule Tuning Exposure** | `NO` (0/20) | `NO` (0/40) |
| **T2S Validator Rule Tuning Exposure** | `NO` (0/20) | `NO` (0/40) |
| **T2S Development Engineer Inspection** | `YES` (20/20) | `NO` (0/40) |
| **Gold SQL Author Inspection** | `YES` (20/20) | `YES` (34/40) / `NO` (6/40) |
| **Independent Secondary Reviewer Inspection** | `NO` (0/20) | `NO` (0/40) |

### Key Takeaway
- The 40 ChatSQL Olist cases were **completely unexposed to the T2S engineering team, solver, and validator**.
- However, 34 of those cases **were inspected by the external Gold author** during query construction. The 6 cases lacking Gold SQL (`OLIST-0035` through `OLIST-0040`) are genuinely unauthored and blind to all SQL evaluators.
- For Source A (20 cases), the questions were authored by members of the engineering team, creating an author-developer overlap that requires independent secondary review before certification.

---

## 5. Separation of Duties Governance Audit

A bedrock principle of independent validation is **Separation of Duties**:
$$\text{Gold SQL Author} \neq \text{Independent Gold Reviewer}$$
$$\text{Independent Gold Reviewer} \notin \text{T2S Engineering / Prompt / Validator Tuning Team}$$

### Audit Findings by Cohort

1. **Source A (`ecommerce_db`)**:
   - *Current Status*: `NON_COMPLIANT_PENDING_SECONDARY_REVIEW`
   - *Analysis*: Because internal engineers authored both the cases and initial SQL, self-certification is prohibited. An independent reviewer who did not develop the T2S verifier or rules must independently inspect and verify the semantics of each query.
2. **Source B (`qddd_olist`)**:
   - *Current Status*: `NON_COMPLIANT_PENDING_AUTHORING_AND_SECONDARY_REVIEW`
   - *Analysis*: While external to the T2S development team, 0 cases have undergone formal dual-role review. Furthermore, 6 queries remain unwritten.

**Result**: Exactly **0 out of 60 cases** currently satisfy the Separation of Duties requirement for certified independent holdout evaluation.

---

## 6. Cohort Staging & Freeze Audit

- **Staged In-Repository Manifest**: `benchmarks/t2s/independent_validation/manifest.json` (Version `1.0.0-draft`).
  - Contains **20 cases** (`ecommerce_db`).
  - Manifest SHA-256: `6cda4fb7747e9ff8eb5970c63fb9396be2679261a8ef832626e834fa2ab7c31d`.
  - Cases JSONL SHA-256: `a937a098485dd008985c57b77ce2a514d115db99787e91d5ae1384074ee94589`.
  - Post-Freeze Modifications: `NO` (Zero post-staging mutations detected on `git HEAD f8aded617dde`).
- **External Cohort**: The 40 Olist cases reside in `/home/thuclh245/MyCode/ChatSQL` and **have not yet been merged into the staged repository manifest**.

---

## 7. Audit Artifact Deliverables

All 12 required governance artifacts have been constructed and integrity-fingerprinted in `results/security/enterprise_validation_governance/`:

1. `source_inventory.json`: Structural and network metadata for `ecommerce_db` and `qddd_olist`.
2. `case_provenance_ledger.jsonl`: 60 records detailing origin, partition, author roles, tri-state exposure booleans, and final case eligibility.
3. `exposure_matrix.json`: Cross-tabulated matrix of 60 cases across 9 exposure dimensions.
4. `gold_inventory.json`: Inventory of 54 authored queries, 6 missing queries, 53 runnable queries, and 1 execution defect.
5. `gold_review_registry.jsonl`: Case-by-case review log tracking separation of duties and blocking reasons.
6. `role_separation_audit.json`: Governance analysis of author vs reviewer vs developer roles.
7. `cohort_freeze_audit.json`: Staging manifest audit, versioning, and post-freeze immutability checks.
8. `database_snapshot_audit.json`: Docker container status, schema details, and SHA-256 snapshots for both target databases.
9. `evidence_index.json`: Comprehensive cross-referenced index connecting audit claims to logs and filesystem paths.
10. `cohort_certification_summary.json`: Quantitative summary metrics across all 60 cases.
11. `final_decision.json`: Explicit gating decision enforcing `BLOCKED` status for independent validation runs.
12. `governance_execution_manifest.json`: Root cryptographic integrity ledger recording SHA-256 fingerprints of all 11 sibling artifacts.

---

## 8. Final Decision & Remediation Roadmap

### Formal Gating Decision

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  REPOSITORY_HYGIENE_STATUS: COMPLETE (PASSED)                                │
│  VALIDATION_DATA_GOVERNANCE_STATUS: PARTIAL_COHORT_REQUIRES_GOLD_REVIEW     │
│  CERTIFIED_INDEPENDENT_CASES: 0 / 60                                        │
│  INDEPENDENT_VALIDATION_PERMITTED: BLOCKED                                  │
│  PRODUCTION_ENFORCEMENT_AUTHORIZED: NO                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Remediation Action Plan

To transition the cohort from `PARTIAL_COHORT_REQUIRES_GOLD_REVIEW` to `CERTIFIED_INDEPENDENT_COHORT`:

1. **Author Missing Gold SQL**:
   - Write reference SQL for cases `OLIST-0035` through `OLIST-0040`.
2. **Repair Schema Typo**:
   - Correct `core.category_translation` to `core.product_category_translation` in `OLIST-0017`.
3. **Execute Dual-Role Semantic Review**:
   - Assign an independent reviewer (not the original author, not a T2S solver/validator developer) to review and certify all 60 cases.
   - Record review timestamps, reviewer identities, and approval decisions in `gold_review_registry.jsonl`.
4. **Unify and Freeze Repository Manifest**:
   - Stage all 60 certified cases into `benchmarks/t2s/independent_validation/manifest.json`.
   - Update manifest version to `1.0.0-final` and compute the immutable SHA-256 freeze fingerprint.
5. **Re-evaluate Gate**:
   - Only after all 60 cases achieve `INDEPENDENTLY_CERTIFIED` state may independent validation execution and production enforcement be considered.

---
*Report generated strictly with zero remote LLM API calls and zero protected data disclosure.*
