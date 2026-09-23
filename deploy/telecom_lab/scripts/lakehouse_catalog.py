"""Nguồn sự thật duy nhất về việc bảng nào vào lake và mang kiểu dữ liệu gì.

Mọi script nạp/kiểm tra đều đọc từ đây, nên phạm vi (scope) và ánh xạ kiểu không
bị lệch giữa các bước. Catalog gốc là `sample data/synthetic/generated/catalog.json`
do generator sinh ra; file này không sửa catalog, chỉ chiếu nó sang Trino.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATED_DIR = REPO_ROOT / "sample data" / "synthetic" / "generated"
CATALOG_PATH = GENERATED_DIR / "catalog.json"
COUNTS_PATH = GENERATED_DIR / "counts.json"
BENCHMARK_CASES_PATH = REPO_ROOT / "sample data" / "synthetic" / "benchmark" / "cases.jsonl"

Scope = Literal["sample8", "benchmark", "all"]
SCOPE_CHOICES: tuple[Scope, ...] = ("sample8", "benchmark", "all")

# 8 bảng có tên và cấu trúc xuất hiện trong bản mô tả OpenMetadata được cung cấp.
# Đây là cổng G1 trong docs/deployment/telecom_lab_pipeline_plan.md.
SAMPLE_SOURCE_TABLES: tuple[str, ...] = (
    "aaa.ftth_account_pppoe",
    "aaa.authentication",
    "aaa.accounting",
    "aam.kpi_aam_daily_tdxl",
    "aam.kpi_aam_daily_tlgd",
    "acs.f_uptime",
    "acs.g_uptime",
    "acs.f_wifi",
)

# Kiểu trong catalog của generator -> kiểu Trino.
# CSV trên Hive chỉ đọc được VARCHAR, nên giá trị được CAST khi chuyển sang Parquet.
TRINO_TYPE_BY_CATALOG_TYPE: dict[str, str] = {
    "text": "VARCHAR",
    "int": "INTEGER",
    "bigint": "BIGINT",
    "real": "DOUBLE",
    "date": "DATE",
    "timestamp": "TIMESTAMP(3)",
}

# Schema tạm giữ bảng CSV thô trước khi CTAS sang Parquet; bị loại khỏi ingestion.
STAGING_SCHEMA = "stg"


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    catalog_type: str

    @property
    def trino_type(self) -> str:
        try:
            return TRINO_TYPE_BY_CATALOG_TYPE[self.catalog_type]
        except KeyError as exc:  # pragma: no cover - chặn kiểu mới lọt qua im lặng
            raise ValueError(
                f"Chưa có ánh xạ Trino cho kiểu '{self.catalog_type}' (cột {self.name})."
            ) from exc


@dataclass(frozen=True)
class TableSpec:
    schema: str
    table: str
    csv_relative_path: str
    row_count: int
    origin: str
    description: str | None
    columns: tuple[ColumnSpec, ...]

    @property
    def fqn(self) -> str:
        """Tên hai phần trong catalog hive, ví dụ `aaa.authentication`."""
        return f"{self.schema}.{self.table}"

    @property
    def sqlite_table(self) -> str:
        """Tên bảng tương ứng trong SQLite oracle (`schema__table`)."""
        return f"{self.schema}__{self.table}"

    @property
    def csv_path(self) -> Path:
        return GENERATED_DIR / self.csv_relative_path

    @property
    def staging_table(self) -> str:
        return f"{self.schema}__{self.table}"


def load_table_specs() -> list[TableSpec]:
    """Đọc toàn bộ catalog của snapshot hiện tại."""
    raw_tables = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    specs: list[TableSpec] = []
    for raw in raw_tables:
        specs.append(
            TableSpec(
                schema=str(raw["schema"]),
                table=str(raw["table"]),
                csv_relative_path=str(raw["csv"]),
                row_count=int(raw["row_count"]),
                origin=str(raw.get("origin") or "unknown"),
                description=raw.get("description"),
                columns=tuple(
                    ColumnSpec(name=str(column["name"]), catalog_type=str(column["type"]))
                    for column in raw["columns"]
                ),
            )
        )
    return specs


def benchmark_table_fqns() -> set[str]:
    """Các bảng mà 100 benchmark case thực sự chạm tới."""
    fqns: set[str] = set()
    with BENCHMARK_CASES_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            for sqlite_table in case.get("tables") or []:
                schema, separator, table = str(sqlite_table).partition("__")
                if separator:
                    fqns.add(f"{schema}.{table}")
    return fqns


def resolve_scope(scope: Scope, specs: list[TableSpec] | None = None) -> list[TableSpec]:
    """Lọc catalog theo phạm vi và giữ nguyên thứ tự schema/table cho ổn định."""
    all_specs = specs if specs is not None else load_table_specs()
    by_fqn = {spec.fqn: spec for spec in all_specs}

    if scope == "all":
        selected = list(all_specs)
    elif scope == "sample8":
        selected = _select(by_fqn, SAMPLE_SOURCE_TABLES, scope)
    elif scope == "benchmark":
        selected = _select(by_fqn, sorted(benchmark_table_fqns()), scope)
    else:  # pragma: no cover - Literal đã chặn, giữ để fail rõ nếu mở rộng
        raise ValueError(f"Phạm vi không hợp lệ: {scope}")

    return sorted(selected, key=lambda spec: (spec.schema, spec.table))


def _select(
    by_fqn: dict[str, TableSpec],
    wanted_fqns: tuple[str, ...] | list[str],
    scope: Scope,
) -> list[TableSpec]:
    missing = [fqn for fqn in wanted_fqns if fqn not in by_fqn]
    if missing:
        raise ValueError(
            f"Phạm vi '{scope}' tham chiếu bảng không có trong catalog: {', '.join(missing)}"
        )
    return [by_fqn[fqn] for fqn in wanted_fqns]


def load_expected_row_counts() -> dict[str, int]:
    """Số dòng kỳ vọng theo `counts.json` của snapshot."""
    return {
        str(key): int(value)
        for key, value in json.loads(COUNTS_PATH.read_text(encoding="utf-8")).items()
    }
