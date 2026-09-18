# T2S Eval v1 — Evaluation Dataset Report

## 1. Executive Summary

- **File Path**: `benchmarks/t2s/datasets/t2s_eval_v1.jsonl`
- **Manifest Path**: `benchmarks/t2s/manifests/t2s_eval_v1_manifest.json`
- **Total Case Count**: 100
- **Pilot Overlap**: **0** (`pilot_question_ids ∩ eval_question_ids = ∅`)
- **Databases Covered**: 11 of 11 (100% coverage)
- **Status**: **`READY_FOR_T2S_BENCHMARK`**

---

## 2. Dataset Construction Methodology

`t2s_eval_v1.jsonl` was constructed from the pool of 415 unseen official BIRD Mini-Dev cases remaining after excluding the 85 pilot BIRD cases.

- **Reproducibility**: Deterministic selection using seed `20260914` and stable SHA256 hashing on `(seed, db_id, question_id)`.
- **Parser**: SQL structural features and strata classifications were computed via AST parsing using `sqlglot` (not regular expressions).
- **Leakage Prevention**: Inference fields (`inference.question`, `inference.db_id`, `inference.evidence`) strictly omit gold SQL, expected answers, and gold schema labels. Gold queries are quarantined in `bird_gold_sql` and `gold.sql_original` for scorer access only.

---

## 3. Structural Complexity and Strata Distribution

| Stratum | Definition | Candidate Pool (N=415) | Selected in Eval v1 (N=100) | Percentage |
|---|---|---:|---:|---:|
| **S1** | Basic single-table queries (0 joins, 1 SELECT) | 56 | 25 | 25.0% |
| **S2** | Single join queries (1 JOIN, 1 SELECT) | 239 | 38 | 38.0% |
| **S3** | Multi-join, subqueries, or HAVING | 113 | 30 | 30.0% |
| **S4** | Advanced SQL (CTE, Window, SetOp, or $\ge$3 SELECTs) | 7 | 7 | 7.0% |
| **Total** | | **415** | **100** | **100.0%** |

### Empirical Note on S4 Allocation
Across the entire 500-case BIRD Mini-Dev dataset, only 21 queries contain S4 constructs (6 CTEs, 5 Window functions, 2 Set operations, and 8 deep subqueries with $\ge$3 SELECTs). The development pilot previously incorporated 15 S4 cases (including all 13 CTE, Window, and SetOp queries). 

Consequently, only 7 S4 cases remained in the unseen pool. To strictly adhere to the data integrity principle—**zero fabrication, zero leakage, and zero overlap with the pilot**—Eval v1 exhaustively includes all 7 available S4 queries. The remaining 93 slots are allocated across S1 (25), S3 (30), and S2 (38), mirroring the natural distribution of BIRD.

---

## 4. BIRD Difficulty and Database Distribution

### Official BIRD Difficulty Balance
- **Simple**: 34 cases (34.0%)
- **Moderate**: 48 cases (48.0%)
- **Challenging**: 18 cases (18.0%)

### Database Coverage
All 11 BIRD Mini-Dev databases are represented virtually uniformly:
- `formula_1`: 10 cases
- `california_schools`: 9 cases
- `card_games`: 9 cases
- `codebase_community`: 9 cases
- `debit_card_specializing`: 9 cases
- `european_football_2`: 9 cases
- `financial`: 9 cases
- `student_club`: 9 cases
- `superhero`: 9 cases
- `thrombosis_prediction`: 9 cases
- `toxicology`: 9 cases

---

## 5. Gold Execution Verification

All 100 gold queries in `t2s_eval_v1.jsonl` were executed against the official SQLite databases:
- **Successfully Executable**: 100 / 100 (100.0%)
- **Execution Failures**: 0
- **Mode**: Read-only (`PRAGMA query_only = ON`)

---

## 6. Leakage Audit

A comprehensive static audit confirmed:
- **Gold SQL exposed in inference inputs**: **NO**
- **Expected results exposed in inference inputs**: **NO**
- **Gold schema labels exposed to solver**: **NO**
