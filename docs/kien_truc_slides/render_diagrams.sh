#!/usr/bin/env bash
# Trích mọi khối ```mermaid trong docs/kien_truc_slides/*.md và render ra SVG
# để chèn vào slide. Cần Node.js (dùng npx, tự tải mermaid-cli lần đầu).
#
#   bash docs/kien_truc_slides/render_diagrams.sh [thư_mục_đích]
#
# Mặc định xuất ra docs/kien_truc_slides/rendered/

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-$SRC_DIR/rendered}"
mkdir -p "$OUT_DIR"

python3 - "$SRC_DIR" "$OUT_DIR" <<'PY'
import re, sys, pathlib

src_dir, out_dir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
count = 0
for markdown_file in sorted(src_dir.glob("*.md")):
    content = markdown_file.read_text(encoding="utf-8")
    blocks = re.findall(r"^```mermaid\n(.*?)^```", content, re.S | re.M)
    for index, block in enumerate(blocks, start=1):
        (out_dir / f"{markdown_file.stem}_{index}.mmd").write_text(block, encoding="utf-8")
        count += 1
print(f"Đã trích {count} sơ đồ Mermaid")
PY

failed=0
for diagram in "$OUT_DIR"/*.mmd; do
    name="$(basename "${diagram%.mmd}")"
    if npx -y @mermaid-js/mermaid-cli -i "$diagram" -o "$OUT_DIR/$name.svg" \
        -b transparent >/dev/null 2>"$OUT_DIR/$name.err"; then
        echo "OK   $name.svg"
        rm -f "$OUT_DIR/$name.err"
    else
        echo "LỖI  $name — xem $OUT_DIR/$name.err"
        failed=$((failed + 1))
    fi
done

echo "---"
echo "Kết quả ở: $OUT_DIR"
[ "$failed" -eq 0 ] || { echo "$failed sơ đồ lỗi cú pháp."; exit 1; }
