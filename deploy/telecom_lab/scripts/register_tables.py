"""Đăng ký CSV trên lake thành bảng Parquet có kiểu trong catalog `hive`.

Đường đi: CSV trên S3 -> bảng ngoài trong schema `stg` (mọi cột VARCHAR, vì
Hive CSV không đọc được kiểu nào khác) -> CTAS sang Parquet kèm CAST theo
catalog. Chạy lại cùng snapshot cho ra cùng kết quả: mỗi bảng bị DROP trước
khi tạo lại.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lakehouse_catalog import (
    SCOPE_CHOICES,
    STAGING_SCHEMA,
    TableSpec,
    load_expected_row_counts,
    resolve_scope,
)

CONTAINER = os.getenv("TRINO_CONTAINER", "telecom_lab_trino")
TRINO_USER = os.getenv("TRINO_LOADER_USER", "lab_loader")
BUCKET = os.getenv("LAKEHOUSE_BUCKET", "lakehouse")
# Hive Metastore chỉ được cấu hình fs.s3a.* nên nó không phân giải được s3://.
# Trino đọc được cả hai scheme, vì vậy s3a:// là mẫu số chung.
LAKE_ROOT = f"{os.getenv('LAKEHOUSE_SCHEME', 's3a')}://{BUCKET}"


def run_sql(statement: str) -> str:
    completed = subprocess.run(
        [
            "docker", "exec", CONTAINER,
            "trino", "--user", TRINO_USER, "--output-format", "TSV",
            "--execute", statement,
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Trino lỗi:\n  SQL: {statement[:160]}\n  {detail}")
    return completed.stdout.strip()


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def create_staging_table(spec: TableSpec) -> None:
    columns = ",\n    ".join(f"{quote(column.name)} VARCHAR" for column in spec.columns)
    location = f"{LAKE_ROOT}/raw/{spec.schema}/{spec.table}"
    run_sql(f"DROP TABLE IF EXISTS hive.{STAGING_SCHEMA}.{quote(spec.staging_table)}")
    run_sql(
        f"CREATE TABLE hive.{STAGING_SCHEMA}.{quote(spec.staging_table)} (\n    {columns}\n) "
        f"WITH (format = 'CSV', external_location = '{location}', skip_header_line_count = 1)"
    )


def create_curated_table(spec: TableSpec) -> None:
    projections = []
    for column in spec.columns:
        name = quote(column.name)
        if column.trino_type == "VARCHAR":
            projections.append(f"{name} AS {name}")
        else:
            # Ô rỗng trong CSV đến đây là chuỗi '', CAST thẳng sẽ hỏng cả câu.
            projections.append(f"CAST(NULLIF({name}, '') AS {column.trino_type}) AS {name}")

    run_sql(f"DROP TABLE IF EXISTS hive.{quote(spec.schema)}.{quote(spec.table)}")
    run_sql(
        f"CREATE TABLE hive.{quote(spec.schema)}.{quote(spec.table)} WITH (format = 'PARQUET') AS\n"
        f"SELECT\n    " + ",\n    ".join(projections) + "\n"
        f"FROM hive.{STAGING_SCHEMA}.{quote(spec.staging_table)}"
    )


def count_rows(schema: str, table: str) -> int:
    return int(run_sql(f"SELECT count(*) FROM hive.{quote(schema)}.{quote(table)}"))


def main() -> int:
    scope = os.getenv("LAKEHOUSE_SCOPE", "sample8")
    if scope not in SCOPE_CHOICES:
        raise SystemExit(f"LAKEHOUSE_SCOPE không hợp lệ: {scope!r}. Chọn một trong {SCOPE_CHOICES}.")

    specs = resolve_scope(scope)
    expected_counts = load_expected_row_counts()

    run_sql(
        f"CREATE SCHEMA IF NOT EXISTS hive.{STAGING_SCHEMA} "
        f"WITH (location = '{LAKE_ROOT}/{STAGING_SCHEMA}')"
    )
    for schema in sorted({spec.schema for spec in specs}):
        run_sql(
            f"CREATE SCHEMA IF NOT EXISTS hive.{quote(schema)} "
            f"WITH (location = '{LAKE_ROOT}/curated/{schema}')"
        )

    mismatches: list[str] = []
    for spec in specs:
        create_staging_table(spec)
        create_curated_table(spec)

        actual = count_rows(spec.schema, spec.table)
        expected = expected_counts.get(spec.sqlite_table, spec.row_count)
        status = "OK" if actual == expected else "LỆCH"
        if actual != expected:
            mismatches.append(f"{spec.fqn}: Trino có {actual} dòng, snapshot khai {expected}")
        print(f"{status:<5} {spec.fqn:<32} {actual:>7} dòng")

    print(f"\nPhạm vi {scope}: {len(specs)} bảng đã đăng ký trong catalog hive.")

    if mismatches:
        print("\nSố dòng lệch so với snapshot:", file=sys.stderr)
        for line in mismatches:
            print(f"  {line}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
