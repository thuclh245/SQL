# BIRD Mini-Dev Compatibility and Audit Report

## 1. Official Source Verification

| Artifact | Source Origin | File Size (Bytes) | Record Count | SHA256 Hash | Status |
|---|---|---:|---:|---|---|
| `mini_dev_sqlite.json` | Local Canonical (`minidev.zip`) | 278,486 | 500 | `4ba5fa8de55856222f484d380d2ba872b380bf79d825de70478e2120cb0fc43b` | MATCHES_PILOT_PROVENANCE |
| `mini_dev_sqlite.json` | Hugging Face (`birdsql/bird_mini_dev`) | 278,513 | 500 | `88ceb0710163cae46a256ecea8f0a8c98286599530b60587fda5c3cfe57d45d2` | OFFICIAL_HF_SNAPSHOT |
| `mini_dev_tables.json` | BIRD Schema Metadata | 158,350 | 11 databases | `382943b17781b0a8f828a2a472c918ec3bfa097a829f02be8d2ae4c1851e06fa` | OFFICIAL_TABLE_SCHEMAS |

### Source Variant Analysis
A diff between the local original `mini_dev_sqlite.json` and the Hugging Face snapshot identified exactly 2 query updates in the HF version:
1. **`qid=879` (`formula_1`)**: HF cast `fastestLapSpeed` as `REAL` for numeric ordering (`ORDER BY CAST(T2.fastestLapSpeed AS REAL) DESC`).
2. **`qid=1322` (`student_club`)**: HF corrected the query from returning event names via `EXCEPT` to `COUNT(DISTINCT T1.event_id)`.

The T2S Pilot v1 `gold.sql_original` strictly aligns with the canonical local Mini-Dev source (`4ba5fa8d...`) across all 85 BIRD cases (85/85 match).

---

## 2. Pilot Compatibility Audit (Gates 1–8)

- **Pilot Total Slots**: 100
- **Executable BIRD Cases**: 85
- **Robustness Cases**: 15 (all 15 are stubs)
- **Stub Cases**: 15
- **Exact Official Matches**: 85
- **Modified Questions**: 0
- **Missing IDs**: 0
- **Duplicates**: 0

### Gate Evaluation Matrix
- **Gate 1 (Source Identity)**: **PASS** — 85/85 map to official BIRD Mini-Dev `question_id`.
- **Gate 2 (Database Identity)**: **PASS** — 85/85 match official `db_id`s.
- **Gate 3 (Question Identity)**: **PASS** — 85/85 match official question texts.
- **Gate 4 (Evidence Identity)**: **PASS** — 85/85 match official evidence texts.
- **Gate 5 (Gold Provenance)**: **PASS** — `sql_original` retains official gold; modifications are quarantined in `sql_corrected`.
- **Gate 6 (Database Availability)**: **PASS** — All 11 databases exist with real data rows.
- **Gate 7 (Gold Executability)**: **PASS** — 85/85 queries execute successfully.
- **Gate 8 (Duplicate Detection)**: **PASS** — 0 duplicates.

---

## 3. Gold SQL Audit

- **Official Gold Unchanged**: 51 cases
- **T2S Corrected Gold**: 34 cases
- **Corrections Causing Different Execution Results**: 30 cases
- **Corrections with Matching Results**: 4 cases
- **Needs Manual Review**: 34 cases (documented in `pilot_gold_correction_review.csv`)

---

## 4. Database Integrity Inspection

| Database ID | Path | Size (Bytes) | Tables | Non-Empty | Total Rows | Classification |
|---|---|---:|---:|---:|---:|---|
| `california_schools` | `.../california_schools.sqlite` | 11,116,544 | 3 | 3 | 29,941 | OFFICIAL_EXECUTION_DB |
| `card_games` | `.../card_games.sqlite` | 261,820,416 | 6 | 6 | 803,445 | OFFICIAL_EXECUTION_DB |
| `codebase_community` | `.../codebase_community.sqlite` | 481,419,264 | 8 | 8 | 740,646 | OFFICIAL_EXECUTION_DB |
| `debit_card_specializing` | `.../debit_card_specializing.sqlite` | 34,635,776 | 5 | 5 | 423,050 | OFFICIAL_EXECUTION_DB |
| `european_football_2` | `.../european_football_2.sqlite` | 597,754,880 | 7 | 7 | 222,796 | OFFICIAL_EXECUTION_DB |
| `financial` | `.../financial.sqlite` | 71,294,976 | 8 | 8 | 1,079,680 | OFFICIAL_EXECUTION_DB |
| `formula_1` | `.../formula_1.sqlite` | 22,360,064 | 13 | 13 | 493,257 | OFFICIAL_EXECUTION_DB |
| `student_club` | `.../student_club.sqlite` | 2,641,920 | 8 | 8 | 42,511 | OFFICIAL_EXECUTION_DB |
| `superhero` | `.../superhero.sqlite` | 237,568 | 10 | 10 | 10,614 | OFFICIAL_EXECUTION_DB |
| `thrombosis_prediction` | `.../thrombosis_prediction.sqlite` | 7,327,744 | 3 | 3 | 15,252 | OFFICIAL_EXECUTION_DB |
| `toxicology` | `.../toxicology.sqlite` | 2,678,784 | 4 | 4 | 36,922 | OFFICIAL_EXECUTION_DB |

- **Official Execution DB Count**: 11 (4,399,514 total rows)
- **Schema-Only Placeholder Count**: 11 (0 data rows; safely isolated in `schema_only_placeholders/`)
- **Missing DB Count**: 0

---

## 5. Gold Execution Verification

- **Total Cases Tested**: 85
- **Successfully Executable**: 85 (100.0%)
- **Failed Gold Executions**: 0
- **Execution Engine**: SQLite read-only mode (`PRAGMA query_only = ON`)

---

## 6. Compatibility Verdict

**`READY_FOR_T2S_BENCHMARK`** for official BIRD execution evaluation.

*Note regarding Pilot v1*: While the underlying 85 BIRD cases are 100% compatible and executable, Pilot v1 as a single file remains in `REVISE` status until the 15 S5 stubs are authored and the 34 gold corrections receive sign-off.
