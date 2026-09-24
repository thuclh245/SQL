#!/usr/bin/env python3
"""Profile executable DuckDB tables and emit evidence for metadata variant M2.

Read-only.  Every finding carries the statistics it was derived from, so M2
descriptions can cite evidence instead of inventing provenance.

Findings per column (keyed by production trino_fqn):
  numeric_text     VARCHAR whose non-empty values all parse as numbers
  format           value pattern: date_hour (YYYY-MM-DD-HH), iso_date, yyyymmdd
  epoch_unit       BIGINT timestamps: seconds vs milliseconds, with date range
  negative_sentinel  a single repeated negative value in an otherwise >= 0 column
  constant         only one distinct value (synthetic filler; flag only)
  placeholder      contains 'sample_*' values (synthetic filler; flag only)

Relationships: same-name columns across tables whose value sets overlap
(>= 80% containment either way, or >= 5 shared values).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "generated" / "vtnet.duckdb"
MAPPING = ROOT / "generated" / "table_name_mapping.json"
OUT = ROOT / "metadata" / "variants" / "M2" / "profile_report.json"

MIN_ROWS = 3
FORMATS = {
    "date_hour": r"^\d{4}-\d{2}-\d{2}-\d{2}$",
    "iso_date": r"^\d{4}-\d{2}-\d{2}$",
    "yyyymmdd": r"^\d{8}$",
}
JOIN_MIN_DISTINCT = 3
JOIN_MIN_OVERLAP = 0.8
JOIN_MIN_SHARED = 5  # partial overlap, e.g. an exclusion list that is a small subset


def epoch_unit(lo: int, hi: int) -> str | None:
    if 1_000_000_000 <= lo and hi < 2_000_000_000:
        return "seconds"
    if 1_000_000_000_000 <= lo and hi < 2_000_000_000_000:
        return "milliseconds"
    return None


def iso(ts_seconds: int) -> str:
    return datetime.fromtimestamp(ts_seconds, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def profile_column(con, table: str, col: str, typ: str, total: int) -> dict:
    q = f'"{table}"'
    c = f'"{col}"'
    distinct, placeholder = con.execute(
        f"SELECT COUNT(DISTINCT {c}), SUM(CASE WHEN CAST({c} AS VARCHAR) LIKE 'sample\\_%' ESCAPE '\\' THEN 1 ELSE 0 END) FROM {q}"
    ).fetchone()
    stats: dict = {"rows": total, "distinct": distinct, "flags": []}
    if placeholder:
        stats["flags"].append("placeholder")
        stats["placeholder_count"] = placeholder
    if distinct == 1 and total >= MIN_ROWS:
        stats["flags"].append("constant")
        stats["constant_value"] = str(con.execute(f"SELECT ANY_VALUE({c}) FROM {q}").fetchone()[0])
    if placeholder or distinct <= 1:
        return stats

    upper = typ.upper()
    if "CHAR" in upper or "TEXT" in upper:
        non_empty, numeric = con.execute(
            f"SELECT COUNT(*), COUNT(TRY_CAST({c} AS DOUBLE)) FROM {q} WHERE {c} IS NOT NULL AND TRIM({c}) <> ''"
        ).fetchone()
        if non_empty >= MIN_ROWS and numeric == non_empty:
            stats["flags"].append("numeric_text")
            stats["numeric_parse_ratio"] = 1.0
        for name, pattern in FORMATS.items() if non_empty >= MIN_ROWS else ():
            hits = con.execute(f"SELECT COUNT(*) FROM {q} WHERE regexp_full_match({c}, '{pattern}')").fetchone()[0]
            if hits == non_empty:
                stats["flags"].append("format")
                stats["format"] = name
                break
    elif "INT" in upper:
        lo, hi = con.execute(f"SELECT MIN({c}), MAX({c}) FROM {q}").fetchone()
        unit = epoch_unit(lo, hi) if lo is not None else None
        if unit:
            div = 1 if unit == "seconds" else 1000
            stats["flags"].append("epoch_unit")
            stats["epoch_unit"] = unit
            stats["epoch_range"] = [iso(lo // div), iso(hi // div)]
    if any(t in upper for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL")):
        negatives = con.execute(
            f"SELECT {c}, COUNT(*) FROM {q} WHERE {c} < 0 GROUP BY {c}"
        ).fetchall()
        if len(negatives) == 1 and negatives[0][1] >= 2:
            stats["flags"].append("negative_sentinel")
            stats["negative_sentinel"] = {"value": negatives[0][0], "count": negatives[0][1]}
    return stats


def infer_relationships(con, value_columns: dict[str, list[tuple[str, str]]]) -> list[dict]:
    """value_columns: column name -> [(duckdb_table, trino_fqn)] for joinable candidates."""
    rels = []
    for col, tables in sorted(value_columns.items()):
        if len(tables) < 2:
            continue
        sets = {}
        for duck, fqn in tables:
            sets[fqn] = {
                r[0]
                for r in con.execute(f'SELECT DISTINCT CAST("{col}" AS VARCHAR) FROM "{duck}" WHERE "{col}" IS NOT NULL').fetchall()
            }
        fqns = sorted(sets)
        for i, a in enumerate(fqns):
            for b in fqns[i + 1:]:
                sa, sb = sets[a], sets[b]
                if min(len(sa), len(sb)) < JOIN_MIN_DISTINCT:
                    continue
                inter = len(sa & sb)
                a_in_b, b_in_a = inter / len(sa), inter / len(sb)
                if max(a_in_b, b_in_a) >= JOIN_MIN_OVERLAP or inter >= JOIN_MIN_SHARED:
                    rels.append({
                        "column": col, "left": a, "right": b,
                        "left_values_in_right": round(a_in_b, 3),
                        "right_values_in_left": round(b_in_a, 3),
                        "shared_values": inter,
                    })
    return rels


def main() -> None:
    mapping = {m["duckdb_table"]: m["trino_fqn"] for m in json.loads(MAPPING.read_text(encoding="utf-8"))}
    con = duckdb.connect(str(DB), read_only=True)
    columns: dict[str, dict] = {}
    joinable: dict[str, list[tuple[str, str]]] = {}
    for (table,) in con.execute("SHOW TABLES").fetchall():
        fqn = mapping.get(table)
        if fqn is None:
            continue
        total = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if total == 0:
            continue
        for _, col, typ, *_ in con.execute(f"PRAGMA table_info('{table}')").fetchall():
            stats = profile_column(con, table, col, typ, total)
            if stats["flags"]:
                columns[f"{fqn}.{col}"] = stats
            usable = not {"placeholder", "constant"} & set(stats["flags"])
            if usable and stats["distinct"] >= JOIN_MIN_DISTINCT and (col.endswith(("_id", "_code")) or col in {"hostname", "vendor"}):
                joinable.setdefault(col, []).append((table, fqn))
    report = {
        "method": "read-only DuckDB profiler; thresholds: min_rows=%d, join_overlap>=%.1f or shared>=%d" % (MIN_ROWS, JOIN_MIN_OVERLAP, JOIN_MIN_SHARED),
        "database": "generated/vtnet.duckdb",
        "summary": {
            flag: sum(flag in s["flags"] for s in columns.values())
            for flag in ("numeric_text", "format", "epoch_unit", "negative_sentinel", "constant", "placeholder")
        },
        "columns": dict(sorted(columns.items())),
        "relationships": infer_relationships(con, joinable),
    }
    report["summary"]["relationships"] = len(report["relationships"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
