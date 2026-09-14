import json
import sqlite3
from pathlib import Path
from typing import Any

from t2s.benchmark.case_loader import _read_jsonl, load_benchmark_cases
from t2s.benchmark.scoring import execute_gold_sql
from t2s.errors import BenchmarkDatabaseIntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_INTEGRITY_MANIFEST = (
    PROJECT_ROOT / "benchmarks" / "t2s" / "manifests" / "database_integrity_report.json"
)


def verify_eval_v1_invariants(
    eval_dataset_path: Path,
    pilot_dataset_path: Path,
    database_root: Path,
) -> None:
    eval_cases = load_benchmark_cases(eval_dataset_path)

    if len(eval_cases) != 100:
        raise ValueError(f"Eval v1 invariant failed: expected 100 cases, found {len(eval_cases)}")

    eval_question_ids = {
        case.inference_case.question_id
        for case in eval_cases
        if case.inference_case.question_id is not None
    }
    pilot_question_ids = _read_pilot_question_ids(pilot_dataset_path)
    overlap = eval_question_ids & pilot_question_ids
    if overlap:
        raise ValueError(
            f"Eval v1 invariant failed: pilot overlap question IDs found: {sorted(overlap)}"
        )

    db_ids = {case.inference_case.db_id for case in eval_cases}
    if len(db_ids) != 11:
        raise ValueError(f"Eval v1 invariant failed: expected 11 databases, found {len(db_ids)}")

    verify_benchmark_database_integrity(
        database_root=database_root,
        db_ids=db_ids,
        integrity_manifest_path=DEFAULT_DATABASE_INTEGRITY_MANIFEST,
    )

    failed_gold_cases: list[str] = []
    for case in eval_cases:
        gold_sql = case.scoring_gold.official_sql
        if gold_sql is None:
            failed_gold_cases.append(case.inference_case.case_id)
            continue
        db_path = resolve_official_database_path(database_root, case.inference_case.db_id)
        gold_result = execute_gold_sql(gold_sql, db_path)
        if not gold_result.ok:
            failed_gold_cases.append(case.inference_case.case_id)
    if failed_gold_cases:
        raise ValueError(
            "Eval v1 invariant failed: gold SQL did not execute for "
            f"{len(failed_gold_cases)}/100 cases: {failed_gold_cases[:10]}"
        )


def resolve_official_database_path(database_root: Path, db_id: str) -> Path:
    db_path = database_root / db_id / f"{db_id}.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"Official database not found for db_id={db_id}: {db_path}")
    return db_path


def verify_benchmark_database_integrity(
    database_root: Path,
    db_ids: set[str],
    integrity_manifest_path: Path = DEFAULT_DATABASE_INTEGRITY_MANIFEST,
) -> None:
    records = _load_official_database_records(integrity_manifest_path)
    for db_id in sorted(db_ids):
        db_path = resolve_official_database_path(database_root, db_id)
        expected_record = records.get(db_id)
        if expected_record is None:
            raise BenchmarkDatabaseIntegrityError(
                f"No official database integrity manifest record found for db_id={db_id}."
            )
        _verify_database_file_integrity(
            db_id=db_id,
            db_path=db_path,
            expected_record=expected_record,
        )


def _verify_database_file_integrity(
    db_id: str,
    db_path: Path,
    expected_record: dict[str, Any],
) -> None:
    expected_classification = expected_record.get("classification")
    if expected_classification != "OFFICIAL_EXECUTION_DB":
        raise BenchmarkDatabaseIntegrityError(
            f"Database manifest record for {db_id} is not an official execution DB: "
            f"{expected_classification}"
        )

    expected_table_row_counts = expected_record.get("table_row_counts")
    if not isinstance(expected_table_row_counts, dict) or not expected_table_row_counts:
        raise BenchmarkDatabaseIntegrityError(
            f"Database manifest record for {db_id} has no expected table row counts."
        )

    try:
        connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=30)
    except sqlite3.DatabaseError as exc:
        raise BenchmarkDatabaseIntegrityError(
            f"Benchmark database could not be opened as SQLite for db_id={db_id}: {db_path}"
        ) from exc

    try:
        actual_tables = _read_user_table_names(connection)
        expected_tables = set(expected_table_row_counts)
        missing_tables = sorted(expected_tables - actual_tables)
        if missing_tables:
            raise BenchmarkDatabaseIntegrityError(
                f"Benchmark database {db_id} is missing expected user tables: {missing_tables}"
            )

        total_row_count = 0
        non_empty_table_count = 0
        mismatched_tables: list[str] = []
        for table_name, expected_row_count in expected_table_row_counts.items():
            actual_row_count = _count_table_rows(connection, table_name)
            total_row_count += actual_row_count
            if actual_row_count > 0:
                non_empty_table_count += 1
            if actual_row_count != int(expected_row_count):
                mismatched_tables.append(
                    f"{table_name}: expected {expected_row_count}, got {actual_row_count}"
                )

        if total_row_count <= 0 or non_empty_table_count <= 0:
            raise BenchmarkDatabaseIntegrityError(
                f"Benchmark database {db_id} contains no data rows and is not scoreable."
            )
        if mismatched_tables:
            raise BenchmarkDatabaseIntegrityError(
                f"Benchmark database {db_id} row counts do not match official manifest: "
                f"{mismatched_tables[:5]}"
            )

        manifest_total = int(expected_record.get("total_row_count", 0))
        if manifest_total <= 0 or total_row_count != manifest_total:
            raise BenchmarkDatabaseIntegrityError(
                f"Benchmark database {db_id} total row count mismatch: "
                f"expected {manifest_total}, got {total_row_count}"
            )
    except sqlite3.DatabaseError as exc:
        raise BenchmarkDatabaseIntegrityError(
            f"Benchmark database failed SQLite integrity checks for db_id={db_id}: {db_path}"
        ) from exc
    finally:
        connection.close()


def _read_user_table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _count_table_rows(connection: sqlite3.Connection, table_name: str) -> int:
    escaped_table_name = table_name.replace('"', '""')
    row = connection.execute(f'SELECT COUNT(*) FROM "{escaped_table_name}"').fetchone()
    if row is None:
        return 0
    return int(row[0])


def _load_official_database_records(
    integrity_manifest_path: Path,
) -> dict[str, dict[str, Any]]:
    if not integrity_manifest_path.exists():
        raise BenchmarkDatabaseIntegrityError(
            f"Database integrity manifest not found: {integrity_manifest_path}"
        )
    payload = json.loads(integrity_manifest_path.read_text(encoding="utf-8"))
    official_databases = payload.get("official_databases")
    if not isinstance(official_databases, dict):
        raise BenchmarkDatabaseIntegrityError(
            f"Database integrity manifest missing official_databases: {integrity_manifest_path}"
        )
    records = official_databases.get("records")
    if not isinstance(records, list):
        raise BenchmarkDatabaseIntegrityError(
            f"Database integrity manifest missing official database records: "
            f"{integrity_manifest_path}"
        )
    official_records: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        db_id = record.get("db_id")
        if isinstance(db_id, str):
            official_records[db_id] = record
    return official_records


def _read_pilot_question_ids(pilot_dataset_path: Path) -> set[int]:
    question_ids: set[int] = set()
    for raw_case in _read_jsonl(pilot_dataset_path):
        source = raw_case.get("source")
        if not isinstance(source, dict):
            continue
        question_id = source.get("question_id")
        if question_id is None:
            continue
        question_ids.add(int(question_id))
    return question_ids
