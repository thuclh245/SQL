# T2S Benchmark Infrastructure

This directory contains the canonical benchmark datasets, manifests, validation scripts, and audit reports for the T2S Text-to-SQL system.

## Directory Structure

```text
benchmarks/t2s/
├── README.md
├── datasets/
│   ├── t2s_pilot_v1.jsonl       # Development & pilot benchmark (100 slots: 85 BIRD + 15 S5 stubs)
│   └── t2s_eval_v1.jsonl        # Sealed evaluation set (100 unseen official BIRD cases)
├── manifests/
│   ├── bird_source_manifest.json           # Canonical BIRD Mini-Dev source hashes & metadata
│   ├── pilot_compatibility_report.json     # Pilot audit results against BIRD Mini-Dev
│   ├── pilot_gold_correction_review.csv    # 34 corrected gold queries review ledger
│   ├── database_integrity_report.json      # Official vs placeholder DB inspection
│   ├── t2s_eval_v1_manifest.json           # Eval v1 generation parameters & distribution
│   └── gold_execution_report.json          # Execution verification on official SQLite DBs
├── scripts/
│   ├── verify_bird_source.py       # Validates official BIRD Mini-Dev source files
│   ├── inspect_bird_databases.py   # Audits row counts and classifies execution vs placeholder DBs
│   ├── audit_pilot.py              # Evaluates Gates 1–8 for Pilot v1
│   ├── verify_gold_execution.py    # Runs queries against official read-only DBs
│   ├── build_eval_v1.py            # Generates reproducible 100-case eval set via sqlglot AST
│   └── validate_no_overlap.py      # Enforces zero overlap, zero leakage, full DB coverage
├── databases/
│   ├── official -> ...             # Symlink to populated official BIRD SQLite databases (4.4M rows)
│   └── schema_only_placeholders -> # Symlink to DDL-reconstructed schema-only databases (0 rows)
└── reports/
    ├── PILOT_V1_AUDIT.md           # Audit of t2s_pilot_v1.jsonl
    ├── BIRD_COMPATIBILITY_REPORT.md# Detailed Mini-Dev compatibility and gate evaluation
    └── T2S_EVAL_V1_REPORT.md       # Comprehensive specification of t2s_eval_v1.jsonl
```

## Quick Start & Verification Commands

To reproduce the complete benchmark audit and evaluation pipeline:

```bash
# 1. Verify official BIRD source artifacts
.venv/bin/python benchmarks/t2s/scripts/verify_bird_source.py

# 2. Inspect database integrity (official execution DBs vs placeholders)
.venv/bin/python benchmarks/t2s/scripts/inspect_bird_databases.py

# 3. Audit Pilot v1 across Gates 1–8
.venv/bin/python benchmarks/t2s/scripts/audit_pilot.py

# 4. Verify gold execution of Pilot queries on official SQLite databases
.venv/bin/python benchmarks/t2s/scripts/verify_gold_execution.py

# 5. Build the reproducible 100-case Eval v1 set
.venv/bin/python benchmarks/t2s/scripts/build_eval_v1.py

# 6. Validate zero overlap and leakage protection on Eval v1
.venv/bin/python benchmarks/t2s/scripts/validate_no_overlap.py

# 7. Run baseline evaluation against t2s_eval_v1 (full pipeline: P3 -> P4 -> P5 -> P1)
.venv/bin/python -m t2s.benchmark run \
  --dataset benchmarks/t2s/datasets/t2s_eval_v1.jsonl \
  --database-root benchmarks/t2s/databases/official \
  --provider openai_compatible \
  --model "$T2S_LLM_MODEL" \
  --base-url "$T2S_LLM_BASE_URL" \
  --limit 5 \
  --verify-invariants
```
