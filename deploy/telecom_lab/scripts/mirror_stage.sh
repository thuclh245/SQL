#!/bin/sh
# Đẩy CSV đã staging lên object storage. Idempotent: chạy lại cùng snapshot
# không tạo thêm object, chỉ ghi đè file đã đổi.
set -eu

BUCKET="${LAKEHOUSE_BUCKET:-lakehouse}"

if [ ! -d /stage/raw ]; then
  echo "Chưa có /stage/raw. Chạy scripts/stage_raw.py trước." >&2
  exit 1
fi

mc alias set lab http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing "lab/${BUCKET}"
mc mirror --overwrite --remove /stage/raw "lab/${BUCKET}/raw"
echo "Đã đồng bộ /stage/raw -> s3://${BUCKET}/raw"
mc ls --recursive "lab/${BUCKET}/raw" | head -20
