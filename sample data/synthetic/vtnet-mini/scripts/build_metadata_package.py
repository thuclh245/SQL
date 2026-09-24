"""
build_metadata_package.py
=========================
Script xây dựng Metadata Package toàn diện cho VTNet Mini v1 (Phase 4):
1. metadata/catalog.json: Catalog kỹ thuật 148 bảng và 5.864 cột cho engine Text-to-SQL.
2. metadata/schema_catalog.json: Tổng hợp mô tả và thống kê cấp schema/domain.
3. om_ingest/: Gói OpenMetadata Ingestion bundle (service, databases, schemas,
   tables, columns, tags, glossary_terms, domains, owners, manifest, config template, README).
"""

import csv
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
METADATA_DIR = BASE_DIR / "metadata"
GENERATED_DIR = BASE_DIR / "generated"
OM_INGEST_DIR = BASE_DIR / "om_ingest"

OM_INGEST_DIR.mkdir(parents=True, exist_ok=True)


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def main():
    print("=== Building VTNet Mini Metadata Package (Phase 4) ===")
    t0 = time.time()

    # 1. Đọc tables và columns
    tables_csv = METADATA_DIR / "selected_tables.csv"
    columns_csv = METADATA_DIR / "selected_columns.csv"
    mapping_json = GENERATED_DIR / "table_name_mapping.json"
    relationships_json = GENERATED_DIR / "relationships.json"

    with open(mapping_json, encoding="utf-8") as f:
        mapping_list = json.load(f)
    mapping_by_fqn = {m["production_fqn"]: m for m in mapping_list}

    with open(relationships_json, encoding="utf-8") as f:
        rel_data = json.load(f)

    # Đọc columns
    cols_by_table = defaultdict(list)
    with open(columns_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cols_by_table[r["table_fqn"]].append({
                "name": r["column_name"],
                "fqn": r["column_fqn"],
                "data_type": r["data_type"],
                "data_type_display": r["data_type_display"],
                "is_key_candidate": r["is_key_candidate"].lower() == "true",
                "description": r["description"],
            })

    # Đọc tables
    tables = []
    with open(tables_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = mapping_by_fqn.get(r["table_fqn"], {})
            tables.append({
                "catalog": r["catalog"],
                "schema": r["schema"],
                "table_name": r["table_name"],
                "table_fqn": r["table_fqn"],
                "trino_fqn": m.get("trino_fqn", f"{r['catalog']}.{r['schema']}.{r['table_name']}"),
                "duckdb_table": m.get("duckdb_table", f"{r['catalog']}__{r['schema']}__{r['table_name']}"),
                "domain": r["domain"],
                "is_executable": r["is_executable"].lower() == "true",
                "primary_grain": r["primary_grain"],
                "column_count": int(r["column_count"]),
                "description": r["description"],
                "columns": cols_by_table.get(r["table_fqn"], []),
            })

    print(f"Loaded {len(tables)} tables and {sum(len(t['columns']) for t in tables)} columns.")

    # 2. Xây dựng metadata/catalog.json
    print("Generating metadata/catalog.json...")
    catalog_content = {
        "service_name": "VTNet Datalake Presto",
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "total_tables": len(tables),
        "total_columns": sum(len(t["columns"]) for t in tables),
        "tables": tables,
        "relationships": rel_data.get("join_paths", []),
    }
    catalog_path = METADATA_DIR / "catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog_content, f, ensure_ascii=False, indent=2)
    print(f"Saved {catalog_path} ({catalog_path.stat().st_size // 1024} KB).")

    # 3. Xây dựng metadata/schema_catalog.json
    print("Generating metadata/schema_catalog.json...")
    schemas_dict = defaultdict(lambda: {"tables": [], "columns_count": 0, "domain": "", "description": ""})

    schema_descriptions = {
        "hive.npms": "Schema chứa các bảng chỉ số KPI hiệu năng mạng vô tuyến 5G/4G (NPMS), thống kê lưu lượng, độ trễ và danh sách đen tế bào mạng.",
        "hive.netbi": "Schema kho dữ liệu kinh doanh và báo cáo (NetBI), chứa bảng dimension địa bàn cấp tỉnh, khu vực và lịch viễn thông.",
        "hive.geolocation": "Schema lưu trữ thông tin không gian và danh bạ trạm, cell, vùng phủ sóng và phần tử mạng viễn thông.",
        "hive.gnoc": "Schema hệ thống điều hành mạng tập trung (GNOC), lưu trữ sự kiện cảnh báo (alarm), lịch bảo dưỡng thiết bị và lịch sử xử lý sự cố.",
        "hive.fbb": "Schema dịch vụ Internet băng rộng cố định (FTTH/FBB), thống kê lưu lượng phiên, chất lượng mạng và đo lường QoE.",
        "hive.aaa": "Schema hệ thống xác thực, phân quyền và kế toán phiên truy cập mạng băng rộng (Authentication, Authorization, Accounting).",
        "mysql_datamon.data_monitoring": "Schema giám sát chất lượng dữ liệu (Data Quality), độ tươi mới (Freshness), SLA pipeline và chiến dịch người dùng.",
        "hive_geo_old.pm_counter": "Schema kho dữ liệu bộ đếm đo lường hiệu năng cũ (PM Counters), đóng vai trò bảng nhiễu thử nghiệm retrieval.",
    }

    for t in tables:
        s_key = f"{t['catalog']}.{t['schema']}"
        schemas_dict[s_key]["tables"].append(t["table_name"])
        schemas_dict[s_key]["columns_count"] += len(t["columns"])
        schemas_dict[s_key]["domain"] = t["domain"]
        schemas_dict[s_key]["description"] = schema_descriptions.get(s_key, f"Schema {s_key}")

    schema_catalog_content = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "total_schemas": len(schemas_dict),
        "schemas": [
            {
                "schema_fqn": f"VTNet Datalake Presto.{s_key}",
                "catalog": s_key.split(".")[0],
                "schema": s_key.split(".")[1],
                "domain": s_info["domain"],
                "table_count": len(s_info["tables"]),
                "columns_count": s_info["columns_count"],
                "description": s_info["description"],
                "sample_tables": s_info["tables"][:5],
            }
            for s_key, s_info in schemas_dict.items()
        ]
    }
    schema_catalog_path = METADATA_DIR / "schema_catalog.json"
    with open(schema_catalog_path, "w", encoding="utf-8") as f:
        json.dump(schema_catalog_content, f, ensure_ascii=False, indent=2)
    print(f"Saved {schema_catalog_path}.")

    # 4. Sinh Gói Ingest OpenMetadata (om_ingest/)
    print("Generating OpenMetadata Ingest Bundle in om_ingest/...")

    # 4.1 service.json
    service_content = {
        "name": "VTNet Datalake Presto",
        "serviceType": "Trino",
        "description": "Kho dữ liệu viễn thông tập trung VTNet Datalake Presto/Trino",
        "connection": {
            "config": {
                "type": "Trino",
                "hostPort": "localhost:8080",
                "username": "openmetadata_ingestion",
                "catalog": "hive"
            }
        }
    }
    with open(OM_INGEST_DIR / "service.json", "w", encoding="utf-8") as f:
        json.dump(service_content, f, ensure_ascii=False, indent=2)

    # 4.2 domains.jsonl
    domains = [
        {"name": "Network KPI/5G", "displayName": "Chỉ Số Mạng 5G/4G", "description": "Chỉ số hiệu năng mạng vô tuyến 5G/4G, lưu lượng cell và throughput"},
        {"name": "Common/Location", "displayName": "Địa Bàn & Hạ Tầng", "description": "Phân cấp địa bàn tỉnh, khu vực và danh bạ phần tử trạm"},
        {"name": "Alarm", "displayName": "Quản Lý Cảnh Báo", "description": "Hệ thống quản lý cảnh báo mạng GNOC, lịch bảo trì và sự cố"},
        {"name": "FBB", "displayName": "Băng Rộng Cố Định", "description": "Dịch vụ Internet cáp quang FTTH, tài khoản PPPoE và QoE"},
        {"name": "Data Monitoring", "displayName": "Giám Sát Dữ Liệu", "description": "Giám sát chất lượng dữ liệu, độ tươi mới và pipeline SLA"},
        {"name": "Noisy Metadata", "displayName": "Siêu Dữ Liệu Nhiễu", "description": "Bảng đo lường hiệu năng cũ dùng kiểm thử khả năng chịu nhiễu retrieval"},
    ]
    with open(OM_INGEST_DIR / "domains.jsonl", "w", encoding="utf-8") as f:
        for d in domains:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # 4.3 owners.jsonl
    owners = [
        {"name": "vtnet_noc_ran", "displayName": "RAN NOC Team", "email": "ran_noc@vtnet.viettel.vn", "type": "team"},
        {"name": "vtnet_noc_core", "displayName": "Core NOC Team", "email": "core_noc@vtnet.viettel.vn", "type": "team"},
        {"name": "vtnet_fbb_ops", "displayName": "FBB Operations", "email": "fbb_ops@vtnet.viettel.vn", "type": "team"},
        {"name": "vtnet_data_platform", "displayName": "Data Governance Team", "email": "data_gov@vtnet.viettel.vn", "type": "team"},
    ]
    with open(OM_INGEST_DIR / "owners.jsonl", "w", encoding="utf-8") as f:
        for o in owners:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    # 4.4 tags.jsonl
    tags = [
        {"classification": "Sensitivity", "name": "L1_Public", "description": "Dữ liệu công khai"},
        {"classification": "Sensitivity", "name": "L2_Internal", "description": "Dữ liệu nội bộ VTNet"},
        {"classification": "Sensitivity", "name": "L3_Confidential", "description": "Dữ liệu mật kinh doanh / KPI"},
        {"classification": "Sensitivity", "name": "L4_Restricted", "description": "Dữ liệu hạn chế truy cập nghiêm ngặt"},
        {"classification": "PII", "name": "Sensitive", "description": "Thông tin định danh cá nhân nhạy cảm"},
        {"classification": "PII", "name": "NonSensitive", "description": "Thông tin định danh thông thường"},
        {"classification": "Telecom", "name": "KPI_Network", "description": "Chỉ số hiệu năng mạng"},
        {"classification": "Telecom", "name": "Topology", "description": "Cấu trúc trạm và phần tử mạng"},
        {"classification": "Telecom", "name": "Alarm_Incident", "description": "Sự cố và cảnh báo"},
    ]
    with open(OM_INGEST_DIR / "tags.jsonl", "w", encoding="utf-8") as f:
        for t in tags:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # 4.5 glossary_terms.jsonl
    glossary = [
        {"glossary": "Telecom Terms", "name": "Throughput", "displayName": "Thông lượng mạng", "description": "Tốc độ truyền dữ liệu đường tải xuống (DL) hoặc tải lên (UL) qua giao diện vô tuyến, đơn vị Mbps"},
        {"glossary": "Telecom Terms", "name": "Cell_ID", "displayName": "Mã nhận diện tế bào mạng", "description": "Mã định danh duy nhất của một ô thu phát sóng di động (cell/object_id)"},
        {"glossary": "Telecom Terms", "name": "Bad_Cell", "displayName": "Tế bào mạng suy giảm chất lượng", "description": "Tế bào mạng di động có chất lượng dịch vụ hoặc thông lượng thấp hơn ngưỡng quy định trong nhiều ngày"},
        {"glossary": "Telecom Terms", "name": "PPPoE", "displayName": "Giao thức PPPoE", "description": "Giao thức truyền thông mạng điểm-điểm qua Ethernet (Point-to-Point Protocol over Ethernet) cho dịch vụ FTTH"},
        {"glossary": "Telecom Terms", "name": "SLA", "displayName": "Cam kết mức dịch vụ", "description": "Cam kết chất lượng dịch vụ (Service Level Agreement) về thời gian xử lý sự cố mạng"},
    ]
    with open(OM_INGEST_DIR / "glossary_terms.jsonl", "w", encoding="utf-8") as f:
        for g in glossary:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    # 4.6 databases.jsonl
    distinct_dbs = {t["catalog"] for t in tables}
    with open(OM_INGEST_DIR / "databases.jsonl", "w", encoding="utf-8") as f:
        for db in sorted(distinct_dbs):
            f.write(json.dumps({
                "service": "VTNet Datalake Presto",
                "name": db,
                "fullyQualifiedName": f"VTNet Datalake Presto.{db}",
                "description": f"Catalog {db} trong VTNet Datalake Presto",
            }, ensure_ascii=False) + "\n")

    # 4.7 schemas.jsonl
    with open(OM_INGEST_DIR / "schemas.jsonl", "w", encoding="utf-8") as f:
        for s_key, s_info in schemas_dict.items():
            f.write(json.dumps({
                "database": f"VTNet Datalake Presto.{s_key.split('.')[0]}",
                "name": s_key.split(".")[1],
                "fullyQualifiedName": f"VTNet Datalake Presto.{s_key}",
                "domain": s_info["domain"],
                "description": s_info["description"],
            }, ensure_ascii=False) + "\n")

    # 4.8 tables.jsonl
    domain_to_owner = {
        "Network KPI/5G": "vtnet_noc_ran",
        "Common/Location": "vtnet_data_platform",
        "Alarm": "vtnet_noc_core",
        "FBB": "vtnet_fbb_ops",
        "Data Monitoring": "vtnet_data_platform",
        "Noisy Metadata": "vtnet_data_platform",
    }
    with open(OM_INGEST_DIR / "tables.jsonl", "w", encoding="utf-8") as f:
        for t in tables:
            owner = domain_to_owner.get(t["domain"], "vtnet_data_platform")
            f.write(json.dumps({
                "databaseSchema": f"VTNet Datalake Presto.{t['catalog']}.{t['schema']}",
                "name": t["table_name"],
                "fullyQualifiedName": t["table_fqn"],
                "trino_fqn": t["trino_fqn"],
                "domain": t["domain"],
                "owner": owner,
                "primary_grain": t["primary_grain"],
                "is_executable": t["is_executable"],
                "description": t["description"],
                "column_count": len(t["columns"]),
            }, ensure_ascii=False) + "\n")

    # 4.9 columns.jsonl
    with open(OM_INGEST_DIR / "columns.jsonl", "w", encoding="utf-8") as f:
        for t in tables:
            for c in t["columns"]:
                f.write(json.dumps({
                    "table_fqn": t["table_fqn"],
                    "name": c["name"],
                    "fullyQualifiedName": c["fqn"],
                    "dataType": c["data_type"],
                    "dataTypeDisplay": c["data_type_display"],
                    "is_key_candidate": c["is_key_candidate"],
                    "description": c["description"],
                }, ensure_ascii=False) + "\n")

    # 4.10 ingest_config_template.yaml
    yaml_config = """# OpenMetadata Ingestion Pipeline Configuration for VTNet Mini
# Sử dụng với OpenMetadata CLI: metadata ingest -c ingest_config_template.yaml

source:
  type: trino
  serviceName: "VTNet Datalake Presto"
  serviceConnection:
    config:
      type: Trino
      hostPort: localhost:8080
      username: openmetadata_ingestion
      catalog: hive
  sourceConfig:
    config:
      type: DatabaseMetadata
      schemaFilterPattern:
        includes:
          - npms
          - netbi
          - geolocation
          - gnoc
          - fbb
          - aaa
          - data_monitoring
          - pm_counter
      tableFilterPattern:
        includes:
          - kpi_access5g_5g_cell_peak_view
          - occean_cell
          - f_location_new
          - gnoc
          - ftth_account_pppoe
      includeViews: false
      markDeletedTables: false

sink:
  type: metadata-rest
  config:
    mode: backup
    openMetadataServerConnection:
      hostPort: http://localhost:8585/api
      authProvider: openmetadata
      securityConfig:
        jwtToken: "${OPENMETADATA_JWT_TOKEN}"

workflowConfig:
  openMetadataServerConnection:
    hostPort: http://localhost:8585/api
    authProvider: openmetadata
    securityConfig:
      jwtToken: "${OPENMETADATA_JWT_TOKEN}"
"""
    with open(OM_INGEST_DIR / "ingest_config_template.yaml", "w", encoding="utf-8") as f:
        f.write(yaml_config)

    # 4.11 README.md
    readme_content = """# OpenMetadata VM Ingestion Guide - VTNet Mini

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
curl -X POST http://localhost:8585/api/v1/services/databaseServices \\
  -H "Authorization: Bearer $OPENMETADATA_JWT_TOKEN" \\
  -H "Content-Type: application/json" \\
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
"""
    with open(OM_INGEST_DIR / "README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)

    # 4.12 ingestion_manifest.json
    manifest_files = {}
    for p in sorted(OM_INGEST_DIR.glob("*")):
        if p.name != "ingestion_manifest.json" and p.is_file():
            manifest_files[p.name] = {
                "size_bytes": p.stat().st_size,
                "sha256": sha256_file(p),
            }

    manifest = {
        "package_name": "vtnet_mini_openmetadata_bundle",
        "version": "1.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "total_tables": len(tables),
        "total_columns": sum(len(t["columns"]) for t in tables),
        "files": manifest_files,
    }
    with open(OM_INGEST_DIR / "ingestion_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Generated {OM_INGEST_DIR / 'ingestion_manifest.json'}.")

    print(f"\nPhase 4 execution completed successfully in {time.time() - t0:.2f}s!")


if __name__ == "__main__":
    main()
