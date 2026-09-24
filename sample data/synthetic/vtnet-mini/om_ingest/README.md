# OpenMetadata VM Ingestion Guide - VTNet Mini

Tài liệu hướng dẫn đồng bộ Metadata Package của VTNet Mini lên máy ảo (VM) có sẵn OpenMetadata.

## 1. Cấu trúc gói Ingestion

```text
om_ingest/
  service.json              # Khai báo Trino Database Service
  domains.jsonl             # 6 domains viễn thông
  owners.jsonl              # 4 nhóm chủ quản (NOC RAN, Core, FBB, Data Gov)
  tags.jsonl                # Hệ thống phân loại độ nhạy cảm và thẻ viễn thông
  glossary_terms.jsonl      # Thuật ngữ nghiệp vụ (Throughput, Cell ID, Bad Cell, ...)
  databases.jsonl           # Danh mục catalog (hive, mysql_datamon, ...)
  schemas.jsonl             # 8 schemas lõi
  tables.jsonl              # 148 tables kèm metadata và mô tả
  columns.jsonl             # 5.864 columns kèm kiểu dữ liệu
  ingest_config_template.yaml # Template pipeline OpenMetadata CLI
  ingestion_manifest.json   # Checksum xác thực toàn vẹn
```

## 2. Quy trình chuyển lên VM và Ingest

### Bước 1: Sao chép gói lên VM qua SCP / Rsync
```bash
# Ví dụ đẩy thư mục om_ingest lên VM
rsync -avz sample data/synthetic/vtnet-mini/om_ingest/ user@<VM_IP>:/opt/openmetadata/vtnet_mini_ingest/
```

### Bước 2: Kích hoạt Service và Metadata tối thiểu trên VM
Trên VM đã cài sẵn OpenMetadata:
```bash
# 1. Tạo Database Service
curl -X POST http://localhost:8585/api/v1/services/databaseServices \
  -H "Authorization: Bearer $OPENMETADATA_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d @service.json

# 2. Ingest Domains và Tags
python3 -m openmetadata.ingestion.scripts.import_entities --input domains.jsonl
python3 -m openmetadata.ingestion.scripts.import_entities --input tags.jsonl
python3 -m openmetadata.ingestion.scripts.import_entities --input glossary_terms.jsonl
```

### Bước 3: Chạy Ingestion Pipeline qua OpenMetadata CLI
```bash
export OPENMETADATA_JWT_TOKEN="your_jwt_token_here"
metadata ingest -c ingest_config_template.yaml
```

## 3. Kiểm tra kết quả tìm kiếm trên OpenMetadata (Search Validation)
Truy cập UI OpenMetadata hoặc qua Search API:
- `GET /api/v1/search/query?q=bad cell throughput 5g` -> Trả về `kpi_access5g_5g_cell_peak_view`
- `GET /api/v1/search/query?q=occean_cell` -> Trả về `hive.npms.occean_cell`
- `GET /api/v1/search/query?q=f_location_new` -> Trả về `hive.netbi.f_location_new`
