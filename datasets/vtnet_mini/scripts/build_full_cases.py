#!/usr/bin/env python3
import sys
import json
from pathlib import Path
import duckdb

PROJECT_DIR = Path(__file__).resolve().parent.parent
DUCKDB_PATH = PROJECT_DIR / "generated" / "vtnet.duckdb"
CASES_PY_PATH = PROJECT_DIR / "benchmark" / "cases.py"

print("Building complete benchmark cases suite...")
