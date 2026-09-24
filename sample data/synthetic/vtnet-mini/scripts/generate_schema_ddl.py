"""
generate_schema_ddl.py
======================
Script sinh DDL DuckDB, DDL Trino reference, table_name_mapping.json
và relationships.json cho 148 bảng của VTNet Mini v1 theo Phase 2.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

# Kiểu dữ liệu mapping
DUCKDB_TYPE_MAP = {
    "VARCHAR": "VARCHAR",
    "FLOAT": "DOUBLE",
    "DOUBLE": "DOUBLE",
    "BIGINT": "BIGINT",
    "INT": "INTEGER",
    "INTEGER": "INTEGER",
    "BOOLEAN": "BOOLEAN",
    "TIMESTAMP": "TIMESTAMP",
    "TINYINT": "SMALLINT",
    "SMALLINT": "SMALLINT",
    "VARBINARY": "BLOB",
    "BLOB": "BLOB",
}

TRINO_TYPE_MAP = {
    "VARCHAR": "VARCHAR",
    "FLOAT": "DOUBLE",
    "DOUBLE": "DOUBLE",
    "BIGINT": "BIGINT",
    "INT": "INTEGER",
    "INTEGER": "INTEGER",
    "BOOLEAN": "BOOLEAN",
    "TIMESTAMP": "TIMESTAMP",
    "TINYINT": "TINYINT",
    "SMALLINT": "SMALLINT",
    "VARBINARY": "VARBINARY",
    "BLOB": "VARBINARY",
}


def sanitize_ident(name: str) -> str:
    """Trả về identifier an toàn trong SQL."""
    return f'"{name}"'


def main():
    base_dir = Path(__file__).resolve().parents[1]
    metadata_dir = base_dir / "metadata"
    generated_dir = base_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    tables_csv = metadata_dir / "selected_tables.csv"
    columns_csv = metadata_dir / "selected_columns.csv"

    if not tables_csv.exists() or not columns_csv.exists():
        print(f"Error: Missing {tables_csv} or {columns_csv}!", file=sys.stderr)
        sys.exit(1)

    # 1. Đọc tables
    tables = []
    with open(tables_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            tables.append({
                "catalog": r["catalog"],
                "schema": r["schema"],
                "table_name": r["table_name"],
                "table_fqn": r["table_fqn"],
                "domain": r["domain"],
                "is_executable": r["is_executable"].lower() == "true",
                "primary_grain": r["primary_grain"],
                "column_count": int(r["column_count"]),
                "description": r["description"],
            })

    # 2. Đọc columns
    columns_by_table = defaultdict(list)
    with open(columns_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            columns_by_table[r["table_fqn"]].append({
                "column_name": r["column_name"],
                "column_fqn": r["column_fqn"],
                "data_type": r["data_type"].upper(),
                "data_type_display": r["data_type_display"],
                "is_key_candidate": r["is_key_candidate"].lower() == "true",
                "description": r["description"],
            })

    print(f"Loaded {len(tables)} tables and {sum(len(c) for c in columns_by_table.values())} columns.")

    # 3. Tạo Table Name Mapping
    mapping_list = []
    for t in tables:
        catalog = t["catalog"]
        schema = t["schema"]
        tbl_name = t["table_name"]
        trino_fqn = f"{catalog}.{schema}.{tbl_name}"
        duckdb_name = f"{catalog}__{schema}__{tbl_name}"

        mapping_list.append({
            "production_fqn": t["table_fqn"],
            "trino_fqn": trino_fqn,
            "duckdb_table": duckdb_name,
            "catalog": catalog,
            "schema": schema,
            "table_name": tbl_name,
            "domain": t["domain"],
            "primary_grain": t["primary_grain"],
            "is_executable": t["is_executable"],
            "column_count": t["column_count"],
        })

    mapping_path = generated_dir / "table_name_mapping.json"
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping_list, f, ensure_ascii=False, indent=2)
    print(f"Generated {mapping_path} ({len(mapping_list)} tables mapped).")

    # 4. Sinh DDL DuckDB
    duckdb_sql_lines = [
        "-- ===========================================================================",
        "-- VTNet Mini Data Platform - DuckDB DDL",
        f"-- Total Tables: {len(tables)} (Executable & Metadata-only)",
        "-- Naming Convention: catalog__schema__table",
        "-- ===========================================================================\n",
    ]

    for m in mapping_list:
        t_fqn = m["production_fqn"]
        cols = columns_by_table.get(t_fqn, [])
        table_name = m["duckdb_table"]
        domain = m["domain"]
        grain = m["primary_grain"]
        exec_tag = "EXECUTABLE" if m["is_executable"] else "METADATA_ONLY"

        duckdb_sql_lines.append(f"-- Domain: {domain} | Grain: {grain} | Status: {exec_tag}")
        duckdb_sql_lines.append(f"-- Original: {m['production_fqn']}")
        duckdb_sql_lines.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")

        col_defs = []
        for c in cols:
            raw_type = c["data_type"]
            duck_type = DUCKDB_TYPE_MAP.get(raw_type, "VARCHAR")
            col_defs.append(f"    {sanitize_ident(c['column_name'])} {duck_type}")

        if not col_defs:
            col_defs.append("    \"id\" BIGINT")

        duckdb_sql_lines.append(",\n".join(col_defs))
        duckdb_sql_lines.append(");\n")

    duckdb_sql_content = "\n".join(duckdb_sql_lines)
    duckdb_sql_path = generated_dir / "ddl_duckdb.sql"
    with open(duckdb_sql_path, "w", encoding="utf-8") as f:
        f.write(duckdb_sql_content)
    print(f"Generated {duckdb_sql_path} ({len(tables)} tables).")

    # 5. Sinh DDL Trino Reference
    trino_sql_lines = [
        "-- ===========================================================================",
        "-- VTNet Mini Data Platform - Trino Reference DDL",
        f"-- Total Tables: {len(tables)}",
        "-- Naming Convention: catalog.schema.table",
        "-- ===========================================================================\n",
    ]

    for m in mapping_list:
        t_fqn = m["production_fqn"]
        cols = columns_by_table.get(t_fqn, [])
        trino_table = m["trino_fqn"]
        domain = m["domain"]
        grain = m["primary_grain"]

        trino_sql_lines.append(f"-- Domain: {domain} | Grain: {grain}")
        trino_sql_lines.append(f"CREATE TABLE IF NOT EXISTS {trino_table} (")

        col_defs = []
        for c in cols:
            raw_type = c["data_type"]
            trino_type = TRINO_TYPE_MAP.get(raw_type, "VARCHAR")
            col_defs.append(f"    {sanitize_ident(c['column_name'])} {trino_type}")

        if not col_defs:
            col_defs.append("    \"id\" BIGINT")

        trino_sql_lines.append(",\n".join(col_defs))
        trino_sql_lines.append(") WITH (format = 'PARQUET');\n")

    trino_sql_content = "\n".join(trino_sql_lines)
    trino_sql_path = generated_dir / "ddl_trino_reference.sql"
    with open(trino_sql_path, "w", encoding="utf-8") as f:
        f.write(trino_sql_content)
    print(f"Generated {trino_sql_path} ({len(tables)} tables).")

    # 6. Xây dựng Relationships Join Graph
    # Phân tích các join paths thực tế dựa trên cột khóa
    relationships = {
        "description": "VTNet Mini Core Relationships and Join Graph",
        "total_relationships": 0,
        "join_paths": [],
    }

    # Bảng trung tâm địa phương: f_location_new (hoặc dim_province/dim_area)
    # Xác định các bảng có province_code, area_code
    loc_dim_table = "hive__netbi__f_location_new"
    object_dim_table = "hive__npms__occean_cell"
    cell_inv_table = "hive__geolocation__umts_cell_stats"
    aaa_account_table = "hive__aaa__ftth_account_pppoe"

    paths = [
        # 1. Location Joins
        {
            "id": "rel_loc_kpi5g_peak",
            "source_table": "hive__npms__kpi_access5g_5g_cell_peak_view",
            "target_table": loc_dim_table,
            "join_type": "LEFT JOIN",
            "source_columns": ["province_code"],
            "target_columns": ["province_code"],
            "description": "Join KPI 5G peak view với dimension địa bàn để lấy province_name và cấp địa lý",
            "confidence": 1.0,
        },
        {
            "id": "rel_loc_kpi4g_normal",
            "source_table": "hive__npms__kpi_access4g_all_day_normal",
            "target_table": loc_dim_table,
            "join_type": "LEFT JOIN",
            "source_columns": ["province_code"],
            "target_columns": ["province_code"],
            "description": "Join KPI 4G all-day normal với dimension địa bàn",
            "confidence": 1.0,
        },
        {
            "id": "rel_loc_iptv_qos",
            "source_table": "hive__npms__iptv_qos_data",
            "target_table": loc_dim_table,
            "join_type": "LEFT JOIN",
            "source_columns": ["provincecode"],
            "target_columns": ["province_code"],
            "description": "Join IPTV QoS với địa bàn theo mã tỉnh",
            "confidence": 0.95,
        },
        # 2. Anti-join / Exclusion Joins
        {
            "id": "rel_excl_occean_cell",
            "source_table": "hive__npms__kpi_access5g_5g_cell_peak_view",
            "target_table": object_dim_table,
            "join_type": "NOT EXISTS / ANTI JOIN",
            "source_columns": ["object_id"],
            "target_columns": ["object_id"],
            "description": "Loại trừ các cell thuộc occean_cell trong đánh giá bad cell (theo query mẫu production)",
            "confidence": 1.0,
        },
        # 3. AAA / FBB Joins
        {
            "id": "rel_aaa_auth_accounting",
            "source_table": "hive__aaa__authentication",
            "target_table": "hive__aaa__accounting",
            "join_type": "INNER JOIN",
            "source_columns": ["hostname", "sbr_server", "date_hour"],
            "target_columns": ["hostname", "sbr_server", "date_hour"],
            "description": "Đối chiếu log xác thực AAA với log ghi nhận phiên qua máy chủ và khung giờ",
            "confidence": 1.0,
        },
        # 4. GNOC Alarm Joins
        {
            "id": "rel_gnoc_station_maintain",
            "source_table": "hive__gnoc__gnoc",
            "target_table": "hive__gnoc__icms_maintain_calendar",
            "join_type": "LEFT JOIN",
            "source_columns": ["station_code"],
            "target_columns": ["station_code"],
            "description": "Liên kết thiết bị trạm GNOC với lịch bảo trì trạm",
            "confidence": 0.95,
        },
        {
            "id": "rel_gnoc_history_datehour",
            "source_table": "hive__gnoc__od_history",
            "target_table": "hive__gnoc__gnoc",
            "join_type": "INNER JOIN",
            "source_columns": ["date_hour"],
            "target_columns": ["date_hour"],
            "description": "Lịch sử xử lý sự cố liên kết với sự kiện alarm theo giờ",
            "confidence": 0.9,
        },
    ]

    # Bổ sung các auto-discovered join paths theo tên cột chính
    col_to_tables = defaultdict(list)
    for m in mapping_list:
        t_duck = m["duckdb_table"]
        cols = columns_by_table.get(m["production_fqn"], [])
        for c in cols:
            col_to_tables[c["column_name"].lower()].append((t_duck, c["column_name"]))

    # Tự động phát hiện join theo province_code
    for t_src, col_src in col_to_tables.get("province_code", []):
        if t_src != loc_dim_table and "npms" not in t_src:
            paths.append({
                "id": f"rel_auto_province_{t_src}",
                "source_table": t_src,
                "target_table": loc_dim_table,
                "join_type": "LEFT JOIN",
                "source_columns": [col_src],
                "target_columns": ["province_code"],
                "description": f"Liên kết địa bàn cấp tỉnh từ {t_src} tới f_location_new",
                "confidence": 0.85,
            })

    relationships["total_relationships"] = len(paths)
    relationships["join_paths"] = paths

    rel_path = generated_dir / "relationships.json"
    with open(rel_path, "w", encoding="utf-8") as f:
        json.dump(relationships, f, ensure_ascii=False, indent=2)
    print(f"Generated {rel_path} ({len(paths)} join paths defined).")

    # 7. Verification test trên DuckDB in-memory
    print("\n--- Verifying DuckDB DDL Execution ---")
    con = duckdb.connect(":memory:")
    con.execute(duckdb_sql_content)
    created_tables = con.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in created_tables]
    print(f"DuckDB in-memory tables successfully created: {len(table_names)}/{len(tables)}")
    assert len(table_names) == len(tables), f"Expected {len(tables)} tables, got {len(table_names)}"
    print("Verification PASSED: All tables exist and DDL is 100% valid in DuckDB!\n")


if __name__ == "__main__":
    main()
