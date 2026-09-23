"""Gom CSV của snapshot vào .stage/raw theo phạm vi đã chọn.

Bố cục ở đây quyết định layout object trên lake vì mirror_stage.sh mirror
nguyên thư mục này lên s3://<bucket>/raw. Mỗi bảng chiếm một thư mục riêng:
Hive external table trỏ vào thư mục chứ không trỏ vào file.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lakehouse_catalog import SCOPE_CHOICES, load_expected_row_counts, resolve_scope

STAGE_ROOT = Path(__file__).resolve().parents[1] / ".stage" / "raw"


def _count_data_rows(csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def main() -> int:
    scope = os.getenv("LAKEHOUSE_SCOPE", "sample8")
    if scope not in SCOPE_CHOICES:
        raise SystemExit(f"LAKEHOUSE_SCOPE không hợp lệ: {scope!r}. Chọn một trong {SCOPE_CHOICES}.")

    specs = resolve_scope(scope)
    expected_counts = load_expected_row_counts()

    if STAGE_ROOT.exists():
        shutil.rmtree(STAGE_ROOT)
    STAGE_ROOT.mkdir(parents=True)

    mismatches: list[str] = []
    staged_rows = 0

    for spec in specs:
        if not spec.csv_path.exists():
            raise SystemExit(f"Thiếu CSV nguồn cho {spec.fqn}: {spec.csv_path}")

        destination_dir = STAGE_ROOT / spec.schema / spec.table
        destination_dir.mkdir(parents=True)
        shutil.copy2(spec.csv_path, destination_dir / f"{spec.table}.csv")

        actual = _count_data_rows(spec.csv_path)
        expected = expected_counts.get(spec.sqlite_table, spec.row_count)
        staged_rows += actual
        if actual != expected:
            mismatches.append(f"{spec.fqn}: CSV có {actual} dòng, snapshot khai {expected}")

        print(f"{spec.fqn:<32} {actual:>7} dòng -> raw/{spec.schema}/{spec.table}/")

    print(f"\nPhạm vi {scope}: {len(specs)} bảng, {staged_rows} dòng -> {STAGE_ROOT}")

    if mismatches:
        print("\nSố dòng lệch so với snapshot:", file=sys.stderr)
        for line in mismatches:
            print(f"  {line}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
