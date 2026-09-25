"""Read-only data profile measured from the warehouse.

Only facts that can be measured go here: real column types, whether a column
carries information (not constant, not a generator placeholder), low-cardinality
value sets, time ranges, and grain (keys that are not unique).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

TIME_COLUMNS = {"date_hour", "date", "dt", "ts", "timestamp", "ngay"}
# Primary-key candidates in priority order; the first informative one is checked.
KEY_HINTS = (
    "object_id",
    "province_code",
    "station_code",
    "enodeb_id",
    "hostname",
    "username",
    "unit_id",
    "id",
)
MAX_VALUES = 12
PLACEHOLDER = re.compile(r"^sample_")


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    data_type: str
    distinct: int
    informative: bool
    values: tuple[str, ...] = ()
    value_range: tuple[str, str] | None = None


@dataclass
class TableProfile:
    name: str
    rows: int
    columns: dict[str, ColumnProfile] = field(default_factory=dict)
    grain_notes: list[str] = field(default_factory=list)

    @property
    def informative_columns(self) -> list[ColumnProfile]:
        return [c for c in self.columns.values() if c.informative]


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class DataProfiler:
    """Profiles lazily and caches per table; the synthetic warehouse is small enough
    to profile on first use.  A production deployment would persist this in the catalog."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._cache: dict[str, TableProfile] = {}
        with duckdb.connect(str(db_path), read_only=True) as con:
            self.tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}

    def table(self, name: str) -> TableProfile:
        if name not in self._cache:
            with duckdb.connect(str(self.db_path), read_only=True) as con:
                self._cache[name] = self._profile(con, name)
        return self._cache[name]

    def _profile(self, con: duckdb.DuckDBPyConnection, name: str) -> TableProfile:
        rows = int(_one(con, f"SELECT COUNT(*) FROM {_q(name)}"))
        prof = TableProfile(name=name, rows=rows)
        for _cid, col, dtype, *_ in con.execute(f"PRAGMA table_info({_q(name)})").fetchall():
            qc = _q(col)
            distinct, placeholders = con.execute(
                f"SELECT COUNT(DISTINCT {qc}), "
                f"COUNT(*) FILTER (WHERE CAST({qc} AS VARCHAR) LIKE 'sample\\_%' ESCAPE '\\') "
                f"FROM {_q(name)}"
            ).fetchone() or (0, 0)
            informative = distinct > 1 and placeholders == 0
            values: tuple[str, ...] = ()
            value_range = None
            if informative and "CHAR" in dtype.upper() and distinct <= MAX_VALUES:
                values = tuple(
                    str(r[0])
                    for r in con.execute(
                        f"SELECT DISTINCT {qc} FROM {_q(name)} WHERE {qc} IS NOT NULL ORDER BY 1"
                    ).fetchall()
                )
            if informative and col.lower() in TIME_COLUMNS:
                lo, hi = con.execute(f"SELECT MIN({qc}), MAX({qc}) FROM {_q(name)}").fetchone() or (
                    None,
                    None,
                )
                if lo is not None and hi is not None:
                    value_range = (str(lo), str(hi))
            prof.columns[col.lower()] = ColumnProfile(
                name=col,
                data_type=dtype,
                distinct=int(distinct),
                informative=informative,
                values=values,
                value_range=value_range,
            )
        prof.grain_notes = self._grain(con, prof)
        return prof

    def _grain(self, con: duckdb.DuckDBPyConnection, prof: TableProfile) -> list[str]:
        """Report keys that do not identify a row, because a JOIN or COUNT(*) on them fans out."""
        if prof.rows < 2:
            return []
        cols = prof.columns
        unique = next(
            (c.name for c in cols.values() if c.informative and c.distinct == prof.rows), None
        )
        time_col = next(
            (c for c in ("date_hour", "date", "ts") if c in cols and cols[c].informative), None
        )
        if unique is not None and time_col is not None:
            # Bảng sự kiện: mỗi dòng là một sự kiện; nhiều dòng cùng trạm/giờ là bình thường.
            return [f"Mỗi dòng là một sự kiện riêng, định danh bởi {unique}; không khử trùng."]
        key = next((k for k in KEY_HINTS if k in cols and cols[k].informative), None)
        if key is None or key == unique:
            return []
        group = [key] + ([time_col] if time_col else [])
        max_rows = int(
            _one(
                con,
                f"SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM {_q(prof.name)} "
                f"GROUP BY {', '.join(_q(cols[g].name) for g in group)})",
            )
        )
        if max_rows <= 1:
            return []
        scope = " + ".join(group)
        if time_col is not None:
            return [
                f"Một {scope} có thể có tới {max_rows} dòng: đếm thực thể bằng "
                f"COUNT(DISTINCT {key}), không bằng COUNT(*)."
            ]
        if unique is not None:
            return [
                f"Mỗi dòng định danh bởi {unique}; {key} KHÔNG duy nhất (tối đa {max_rows} "
                f"dòng/giá trị) nên JOIN theo {key} sẽ nhân dòng, đếm {key} dùng COUNT(DISTINCT)."
            ]
        return [
            f"{scope} KHÔNG duy nhất (tối đa {max_rows} dòng/giá trị): "
            "khử trùng (DISTINCT/gom nhóm) trước khi JOIN hoặc đếm."
        ]

    def data_range(self, tables: list[str]) -> dict[str, tuple[str, str]]:
        out = {}
        for t in tables:
            for c in self.table(t).columns.values():
                if c.value_range:
                    out[f"{t}.{c.name}"] = c.value_range
        return out


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    row = con.execute(sql).fetchone()
    return row[0] if row else 0
