# T2S Pilot v1 — Audit Report

## 1. Executive Summary

- **File Path**: `benchmarks/t2s/datasets/t2s_pilot_v1.jsonl`
- **File Size**: 122,029 bytes
- **SHA256**: `7fdc36efbf6e8f6b2b52d9ce3d57dd985f4b458ecaeeaa9ff1022290110d7e56`
- **Total Slots**: 100
- **Pilot Audit Verdict**: `REVISE` (Compatible as development/pilot dataset; requires review of 34 gold corrections and completion of S5 robustness cases before benchmark freezing).

---

## 2. Slot Breakdown and Strata Distribution

Direct inspection of `t2s_pilot_v1.jsonl` demonstrates that the file contains 85 executable BIRD Mini-Dev queries and 15 hand-written robustness stubs:

| Stratum | Definition / Focus | Count | State |
|---|---|---:|---|
| **S1** | Single table, basic projections | 20 | Executable BIRD Mini-Dev |
| **S2** | Single join queries | 25 | Executable BIRD Mini-Dev |
| **S3** | Multi-join, subqueries, HAVING | 25 | Executable BIRD Mini-Dev |
| **S4** | CTE, Window functions, Set operations | 15 | Executable BIRD Mini-Dev |
| **S5** | Robustness / Abstention / Ambiguity | 15 | Pending stubs (`status: stub_pending`) |
| **Total** | | **100** | **85 Executable + 15 Stubs** |

### Robustness (S5) Stub Details
The 15 S5 cases consist of:
- 5 Ambiguous queries (`t2s_pilot_v1_s5_ambiguous_01` to `05`)
- 5 Out-of-scope queries (`t2s_pilot_v1_s5_out_of_scope_01` to `05`)
- 5 Overreach queries (`t2s_pilot_v1_s5_overreach_01` to `05`)

All 15 S5 cases currently have `question: null`, `sql_original: null`, and `evidence: null`. They must NOT be included in SQL Execution Accuracy calculations.

---

## 3. Provenance and Gate Verification

Every executable BIRD case in the pilot was checked against the official BIRD Mini-Dev source (`mini_dev_sqlite.json`):

- **Gate 1 (Source Identity)**: **PASS** — All 85 cases map to valid official BIRD `question_id`s.
- **Gate 2 (Database Identity)**: **PASS** — All 85 `db_id` attributes match official BIRD database metadata.
- **Gate 3 (Question Identity)**: **PASS** — All 85 question strings match official BIRD questions exactly.
- **Gate 4 (Evidence Identity)**: **PASS** — Evidence strings match canonical BIRD metadata.
- **Gate 5 (Gold Provenance)**: **PASS** — Canonical BIRD SQL is preserved in `gold.sql_original`. Modifications are tracked in `gold.sql_corrected`.
- **Gate 6 (Database Availability)**: **PASS** — All referenced databases exist as populated SQLite files.
- **Gate 7 (Gold Executability)**: **PASS** — 85/85 official gold queries execute with 0 errors on official SQLite DBs.
- **Gate 8 (Duplicate Detection)**: **PASS** — 0 duplicate `case_id`s, 0 duplicate `question_id`s.

---

## 4. Gold SQL Corrections and Semantic Risk Analysis

Across the 85 BIRD cases:
- **Unchanged Gold**: 51 cases (`sql_corrected == sql_original`).
- **Corrected Gold**: 34 cases (`sql_corrected != sql_original`).

When executed against the official BIRD SQLite databases:
- **Matching Results**: 4 cases produce identical row sets despite query syntax reformatting.
- **Divergent Results**: 30 cases produce different execution result rows.

All 34 modified queries have been exported to `benchmarks/t2s/manifests/pilot_gold_correction_review.csv`.

### Key Review Items
1. **`bird_1242` (`thrombosis_prediction`)**:
   - Question: *"For laboratory examinations take in 1984, list all patients below 50 years old with normal platelet level."*
   - Change: The corrected query replaces examination date calculation with `CURRENT_TIMESTAMP`, altering age calculations relative to 1984.
2. **`bird_1322` (`student_club`)**:
   - Question: *"How many meeting events have more than 10 attendees?"*
   - Change: Official BIRD query erroneously used `EXCEPT` returning event names. Corrected query computes `COUNT(DISTINCT T1.event_id)`, correctly answering the "How many" request.
3. **`bird_128` (`financial`)**:
   - Question asks for female account holders by descending order; correction alters district grouping and count projection.

**Policy Recommendation**: Until the 34 cases in `pilot_gold_correction_review.csv` receive formal sign-off, benchmark scoring should report dual metrics:
- `EX_official`: Execution Accuracy measured against `sql_original`.
- `EX_curated`: Execution Accuracy measured against approved `sql_corrected`.

---

## 5. Database Integrity and Execution Verification

- **Official Execution DBs**: Located at `benchmarks/t2s/databases/official/`. All 11 databases are populated with real BIRD data (4,399,514 total rows across 85 tables).
- **Schema-Only Placeholders**: DDL-reconstructed databases with 0 data rows were detected in `data/bird_mini_dev/databases/` and migrated to `benchmarks/t2s/databases/schema_only_placeholders/`. They are strictly excluded from execution scoring.
- **Gold Execution Test**: 85/85 pilot queries executed with 100% success (0 errors).
