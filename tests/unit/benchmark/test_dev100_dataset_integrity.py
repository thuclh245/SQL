import hashlib
import json
from pathlib import Path

from t2s.benchmark.case_loader import BenchmarkCaseFilter, load_benchmark_cases
from t2s.benchmark.scoring import execute_gold_sql

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_p8b_dev100.jsonl"
MANIFEST_PATH = PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "t2s_p8b_dev100_manifest.json"
PARTITION_MANIFEST = (
    PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "bird_unopened_partition_manifest.json"
)
PILOT_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_pilot_v1.jsonl"
EVAL_DATASET = PROJECT_ROOT / "benchmarks" / "t2s" / "datasets" / "t2s_eval_v1.jsonl"
DB_ROOT = PROJECT_ROOT / "benchmarks" / "t2s" / "databases" / "official"


def test_dev100_dataset_count_and_format() -> None:
    cases = load_benchmark_cases(DATASET_PATH)
    assert len(cases) == 100

    # Ensure no duplicates
    case_ids = [c.inference_case.case_id for c in cases]
    assert len(set(case_ids)) == 100

    q_ids = [c.inference_case.question_id for c in cases]
    assert len(set(q_ids)) == 100


def test_dev100_dataset_disjoint_from_all_quarantine_partitions() -> None:
    dev100_cases = load_benchmark_cases(DATASET_PATH)
    dev100_qids = {c.inference_case.question_id for c in dev100_cases}

    # 1. Zero overlap with Pilot v1
    pilot_cases = load_benchmark_cases(PILOT_DATASET, BenchmarkCaseFilter(executable_only=True))
    pilot_qids = {
        c.inference_case.question_id
        for c in pilot_cases
        if c.inference_case.question_id is not None
    }
    assert len(dev100_qids & pilot_qids) == 0

    # 2. Zero overlap with Eval v1
    eval_cases = load_benchmark_cases(EVAL_DATASET)
    eval_qids = {
        c.inference_case.question_id for c in eval_cases if c.inference_case.question_id is not None
    }
    assert len(dev100_qids & eval_qids) == 0

    # 3. Zero overlap with 215-case final untouched holdout
    partition_data = json.loads(PARTITION_MANIFEST.read_text(encoding="utf-8"))
    holdout_qids = set(partition_data["final_untouched_holdout"]["question_ids"])
    assert len(holdout_qids) == 215
    assert len(dev100_qids & holdout_qids) == 0


def test_dev100_manifest_checksum_integrity() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["total_cases"] == 100

    actual_sha = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()
    assert manifest["dataset_sha256"] == actual_sha


def test_dev100_official_database_and_gold_executability() -> None:
    dev100_cases = load_benchmark_cases(DATASET_PATH)
    for bundle in dev100_cases:
        db_id = bundle.inference_case.db_id
        db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
        assert db_path.exists(), f"Database not found: {db_path}"

        gold_sql = bundle.scoring_gold.official_sql
        assert gold_sql is not None and gold_sql.strip()
        res = execute_gold_sql(gold_sql, db_path)
        assert res.ok, f"Gold execution failed on {bundle.inference_case.case_id}: {res.error}"
