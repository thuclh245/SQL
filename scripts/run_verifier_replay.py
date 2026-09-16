"""ResultVerifier replay and precision audit script.

Replays ResultVerifier over executed queries from benchmark cohorts against
ground-truth databases, tracking true positives (correctly intercepted broken queries)
and false alarms (valid queries erroneously flagged), and persisting a machine-readable
evaluation artifact.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from t2s.database.query_execution_result import QueryExecutionResult
from t2s.verification.result_verifier import ResultVerifier


@dataclass(frozen=True)
class CaseVerificationRecord:
    case_id: str
    db_id: str
    execution_correct: bool | None
    generated_sql: str
    is_suspicious: bool
    failure_code: str | None
    recommended_probe: str | None
    details: dict[str, Any]
    verdict: str  # TRUE_POSITIVE, FALSE_POSITIVE, CLEAN_ACCEPT, UNKNOWN


def run_verifier_replay(
    ablation_dir: Path,
    db_root: Path,
    output_file: Path,
) -> dict[str, Any]:
    verifier = ResultVerifier()
    summary_by_arm: dict[str, Any] = {}
    all_records: list[dict[str, Any]] = []

    arm_dirs = sorted([d for d in ablation_dir.glob("arm_*") if d.is_dir()])
    if not arm_dirs:
        arm_dirs = [ablation_dir]

    grand_total_executed = 0
    grand_total_flagged = 0
    grand_true_positives = 0
    grand_false_positives = 0

    for arm_dir in arm_dirs:
        cases_file = arm_dir / "cases.jsonl"
        if not cases_file.exists():
            continue

        raw_cases = [
            json.loads(line)
            for line in cases_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        executed_count = 0
        flagged_count = 0
        true_positives = 0
        false_positives = 0
        arm_records: list[CaseVerificationRecord] = []

        for c in raw_cases:
            if not c.get("execution_success") or not c.get("generated_sql"):
                continue

            executed_count += 1
            db_id = c["db_id"]
            db_path = db_root / db_id / f"{db_id}.sqlite"
            if not db_path.exists():
                continue

            sql = c["generated_sql"]
            execution_correct = c.get("execution_correct")

            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                rows_raw = cursor.fetchall()
                cols = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                rows = [dict(zip(cols, r, strict=False)) for r in rows_raw]
                exec_result = QueryExecutionResult(
                    columns=cols, rows=rows, row_count=len(rows)
                )

                outcome = verifier.verify_result(exec_result, plan=None)

                if outcome.is_suspicious:
                    flagged_count += 1
                    if execution_correct is False:
                        verdict = "TRUE_POSITIVE"
                        true_positives += 1
                    elif execution_correct is True:
                        verdict = "FALSE_POSITIVE"
                        false_positives += 1
                    else:
                        verdict = "UNKNOWN"
                else:
                    verdict = "CLEAN_ACCEPT"

                record = CaseVerificationRecord(
                    case_id=c["case_id"],
                    db_id=db_id,
                    execution_correct=execution_correct,
                    generated_sql=sql,
                    is_suspicious=outcome.is_suspicious,
                    failure_code=outcome.failure_code,
                    recommended_probe=outcome.recommended_probe,
                    details=outcome.details,
                    verdict=verdict,
                )
                arm_records.append(record)
                all_records.append(asdict(record))

            except Exception:
                continue
            finally:
                conn.close()

        precision = (
            (true_positives / flagged_count) if flagged_count > 0 else 1.0
        )
        summary_by_arm[arm_dir.name] = {
            "executed_count": executed_count,
            "flagged_count": flagged_count,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "precision": precision,
            "flagged_cases": [
                {
                    "case_id": r.case_id,
                    "failure_code": r.failure_code,
                    "execution_correct": r.execution_correct,
                    "verdict": r.verdict,
                }
                for r in arm_records
                if r.is_suspicious
            ],
        }

        grand_total_executed += executed_count
        grand_total_flagged += flagged_count
        grand_true_positives += true_positives
        grand_false_positives += false_positives

    overall_precision = (
        (grand_true_positives / grand_total_flagged)
        if grand_total_flagged > 0
        else 1.0
    )

    persisted_payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "summary": {
            "total_executed_across_arms": grand_total_executed,
            "total_flagged": grand_total_flagged,
            "true_positives": grand_true_positives,
            "false_positives": grand_false_positives,
            "overall_precision": overall_precision,
        },
        "arms": summary_by_arm,
        "records": all_records,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(persisted_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return persisted_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ResultVerifier replay audit"
    )
    parser.add_argument(
        "--ablation-dir",
        type=Path,
        default=Path("results/accuracy_foundation_ablation"),
    )
    parser.add_argument(
        "--db-root",
        type=Path,
        default=Path("benchmarks/t2s/databases/official"),
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("results/verifier_replay/verifier_replay_cohort.json"),
    )
    args = parser.parse_args()

    payload = run_verifier_replay(
        ablation_dir=args.ablation_dir,
        db_root=args.db_root,
        output_file=args.output_file,
    )
    summary = payload["summary"]
    print("\n=== ResultVerifier Replay Audit Completed ===")
    print(f"Total Executed:  {summary['total_executed_across_arms']}")
    print(f"Total Flagged:   {summary['total_flagged']}")
    print(f"True Positives:  {summary['true_positives']} (broken SQL caught)")
    print(f"False Positives: {summary['false_positives']} (valid SQL flagged)")
    print(f"Precision:       {summary['overall_precision'] * 100:.2f}%")
    print(f"Persisted to:    {args.output_file}\n")


if __name__ == "__main__":
    main()
