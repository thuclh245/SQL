"""
parse_om_excel.py
=================
Script phân tích workbook OpenMetadata (VTNet-presto-OM.xlsx),
trích xuất toàn bộ inventory và chọn 120-160 bảng (khoảng 140 bảng) cho VTNet Mini v1
theo đúng thiết kế tại docs và 02_schema_table_plan.md.
"""

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl


def detect_grain(table_name: str, col_names: set) -> str:
    name_lower = table_name.lower()
    if "hour" in name_lower or "date_hour" in col_names:
        if "cell" in name_lower:
            return "cell-hour"
        if "session" in name_lower or "user" in name_lower or "account" in name_lower:
            return "account-hour"
        return "hourly"
    if "daily" in name_lower or "all_day" in name_lower:
        if "cell" in name_lower:
            return "cell-day"
        if "subscriber" in name_lower or "account" in name_lower:
            return "subscriber-day"
        if "province" in name_lower:
            return "province-day"
        return "daily"
    if "monthly" in name_lower or "month" in name_lower:
        return "monthly"
    if "weekly" in name_lower or "week" in name_lower:
        return "weekly"
    if any(k in name_lower for k in ("dim_", "location", "address", "cat_", "department", "template")):
        return "dimension"
    if any(k in name_lower for k in ("rule", "config", "mapping", "policy", "threshold")):
        return "config/mapping"
    if any(k in name_lower for k in ("alarm", "ticket", "event", "log", "history", "order", "audit")):
        return "event"
    return "snapshot/entity"


def is_key_column(col_name: str) -> bool:
    name_lower = col_name.lower()
    if name_lower in ("id", "code", "username", "object_id", "date_hour", "date", "date_key"):
        return True
    if name_lower.endswith("_id") or name_lower.endswith("_code") or name_lower.endswith("_key"):
        return True
    if "province" in name_lower or "district" in name_lower or "area" in name_lower or "cell" in name_lower:
        return True
    return False


def main():
    excel_path = Path("/home/thuclh245/Downloads/VTNet-presto-OM.xlsx")
    if not excel_path.exists():
        print(f"Error: {excel_path} not found!", file=sys.stderr)
        sys.exit(1)

    project_root = Path(__file__).resolve().parents[4]
    output_dir = project_root / "sample data" / "synthetic" / "vtnet-mini" / "metadata"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading workbook: {excel_path}")
    t0 = time.time()
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    sheet = wb["VTNet Datalake Presto_2026-09-1"]
    print(f"Workbook loaded in {time.time() - t0:.2f}s")

    # Data structures
    databases = {}
    schemas = {}
    tables = {}
    columns_by_table = defaultdict(list)
    schema_table_count = Counter()

    row_count = 0
    t_parse = time.time()
    for row in sheet.iter_rows(min_row=2, values_only=True):
        row_count += 1
        etype = row[12]
        if not etype:
            continue

        name = row[0]
        fqn = row[13] or ""
        desc = row[2] or ""

        if etype == "database":
            databases[fqn] = {
                "name": name,
                "fqn": fqn,
                "description": desc,
            }
        elif etype == "databaseSchema":
            parts = fqn.split(".")
            db_fqn = ".".join(parts[:-1]) if len(parts) > 1 else ""
            schemas[fqn] = {
                "name": name,
                "fqn": fqn,
                "database_fqn": db_fqn,
                "database": parts[1] if len(parts) > 1 else "",
                "description": desc,
            }
        elif etype == "table":
            parts = fqn.split(".")
            db_name = parts[1] if len(parts) > 1 else ""
            schema_name = parts[2] if len(parts) > 2 else ""
            schema_fqn = ".".join(parts[:-1]) if len(parts) > 1 else ""
            schema_table_count[schema_fqn] += 1

            tables[fqn] = {
                "name": name,
                "fqn": fqn,
                "catalog": db_name,
                "schema": schema_name,
                "schema_fqn": schema_fqn,
                "description": desc,
                "owner": row[3] or "",
                "tags": row[4] or "",
                "glossary_terms": row[5] or "",
            }
        elif etype == "column":
            parts = fqn.split(".")
            table_fqn = ".".join(parts[:-1]) if len(parts) > 1 else ""
            col_info = {
                "name": name,
                "fqn": fqn,
                "table_fqn": table_fqn,
                "description": desc,
                "data_type_display": row[14] or "",
                "data_type": row[15] or "",
                "array_data_type": row[16] or "",
                "data_length": row[17] or "",
            }
            columns_by_table[table_fqn].append(col_info)

        if row_count % 50000 == 0:
            print(f"Parsed {row_count} rows in {time.time() - t_parse:.2f}s...")

    print(f"Finished parsing {row_count} rows in {time.time() - t_parse:.2f}s")
    print(f"Total databases: {len(databases)}")
    print(f"Total schemas: {len(schemas)}")
    print(f"Total tables: {len(tables)}")
    print(f"Total columns mapped: {sum(len(cols) for cols in columns_by_table.values())}")

    # Build schema inventory summary
    schema_summary = []
    for s_fqn, s_info in schemas.items():
        tbl_cnt = schema_table_count.get(s_fqn, 0)
        schema_summary.append({
            "catalog": s_info["database"],
            "schema": s_info["name"],
            "fqn": s_fqn,
            "table_count": tbl_cnt,
            "description": s_info["description"][:100] + "..." if len(s_info["description"]) > 100 else s_info["description"],
        })
    schema_summary.sort(key=lambda x: (x["catalog"], -x["table_count"]))

    # Table selection according to 02_schema_table_plan.md
    selected_table_keys = []

    # Priority 1: Network KPI/5G (from hive.npms) -> ~30 tables
    npms_priority_names = [
        "kpi_access5g_5g_cell_peak_view",
        "occean_cell",
        "kpi_access4g_all_day_normal",
        "kpi_4g_week_view",
        "kpi_coremobile_gmsc_object_tcat_hour_normal",
        "iptv_bad_kqi",
        "iptv_qos_data",
        "cntt_ram_server_hour",
        "ericsson_vudc_eric_udr_app_counter_grp_hssismactiveusers_group",
        "ericsson_vudc_eric_udr_app_counter_grp_hssesmusersstored_group",
    ]
    npms_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.hive.npms"]
    npms_chosen = []
    for prio in npms_priority_names:
        for t in npms_tables:
            if t["name"].lower() == prio.lower() and t["fqn"] not in [x["fqn"] for x in npms_chosen]:
                npms_chosen.append(t)
    for t in npms_tables:
        if len(npms_chosen) >= 30:
            break
        if t["fqn"] not in [x["fqn"] for x in npms_chosen]:
            cols = columns_by_table.get(t["fqn"], [])
            if 3 <= len(cols) <= 100:
                npms_chosen.append(t)

    for t in npms_chosen:
        t["domain"] = "Network KPI/5G"
        t["is_executable"] = True
        selected_table_keys.append(t)

    # Priority 2: Common Dimensions / Location (from hive.netbi & hive.geolocation) -> ~18 tables
    netbi_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.hive.netbi"]
    geo_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.hive.geolocation"]
    
    loc_chosen = []
    for t in netbi_tables:
        if "location" in t["name"].lower() or "province" in t["name"].lower() or "district" in t["name"].lower():
            loc_chosen.append(t)
    for t in netbi_tables:
        if len(loc_chosen) >= 10:
            break
        if t not in loc_chosen and 3 <= len(columns_by_table.get(t["fqn"], [])) <= 60:
            loc_chosen.append(t)

    for t in geo_tables:
        if len(loc_chosen) >= 18:
            break
        if any(k in t["name"].lower() for k in ("cell", "site", "region", "map", "bin", "umts")):
            loc_chosen.append(t)

    for t in loc_chosen:
        t["domain"] = "Common/Location"
        t["is_executable"] = True
        selected_table_keys.append(t)

    # Priority 3: Alarm & Incident (from hive.gnoc) -> ~25 tables
    gnoc_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.hive.gnoc"]
    gnoc_chosen = []
    for t in gnoc_tables:
        if any(k in t["name"].lower() for k in ("gnoc", "kpi", "maintain", "history", "alarm", "mr", "department", "outage", "ticket", "sla")):
            gnoc_chosen.append(t)
        if len(gnoc_chosen) >= 25:
            break
    for t in gnoc_tables:
        if len(gnoc_chosen) >= 25:
            break
        if t not in gnoc_chosen:
            gnoc_chosen.append(t)

    for t in gnoc_chosen:
        t["domain"] = "Alarm"
        t["is_executable"] = True
        selected_table_keys.append(t)

    # Priority 4: FBB / FTTH (from hive.fbb & hive.aaa) -> ~25 tables
    aaa_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.hive.aaa"]
    fbb_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.hive.fbb"]
    fbb_chosen = list(aaa_tables)
    for t in fbb_tables:
        if len(fbb_chosen) >= 25:
            break
        fbb_chosen.append(t)

    for t in fbb_chosen:
        t["domain"] = "FBB"
        t["is_executable"] = True
        selected_table_keys.append(t)

    # Priority 5: Data Monitoring (from mysql_datamon.data_monitoring) -> ~25 tables
    datamon_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.mysql_datamon.data_monitoring"]
    datamon_chosen = []
    for t in datamon_tables:
        if any(k in t["name"].lower() for k in ("usersinarea", "kqi", "rule", "quality", "job", "freshness", "group", "check", "log")):
            datamon_chosen.append(t)
        if len(datamon_chosen) >= 25:
            break
    for t in datamon_tables:
        if len(datamon_chosen) >= 25:
            break
        if t not in datamon_chosen:
            datamon_chosen.append(t)

    for t in datamon_chosen:
        t["domain"] = "Data Monitoring"
        t["is_executable"] = True
        selected_table_keys.append(t)

    # Priority 6: Noisy Metadata (from hive_geo_old.pm_counter) -> ~25 tables (metadata-only)
    pm_tables = [t for t in tables.values() if t["schema_fqn"] == "VTNet Datalake Presto.hive_geo_old.pm_counter"]
    pm_chosen = []
    for t in pm_tables:
        if any(k in t["name"].lower() for k in ("5g", "traffic", "throughput", "handover", "drop", "succ", "avail", "erlang")):
            pm_chosen.append(t)
        if len(pm_chosen) >= 25:
            break
    for t in pm_tables:
        if len(pm_chosen) >= 25:
            break
        if t not in pm_chosen:
            pm_chosen.append(t)

    for t in pm_chosen:
        t["domain"] = "Noisy Metadata"
        t["is_executable"] = False
        selected_table_keys.append(t)

    print("\n=== Selected Tables for VTNet Mini v1 ===")
    domain_counts = Counter(t["domain"] for t in selected_table_keys)
    executable_counts = Counter(t["is_executable"] for t in selected_table_keys)
    for dom, cnt in domain_counts.items():
        print(f"  Domain: {dom:20} -> {cnt} tables")
    print(f"Total Selected: {len(selected_table_keys)} tables")
    print(f"  Executable: {executable_counts[True]}")
    print(f"  Metadata-only: {executable_counts[False]}")

    # Write output files
    # 1. source_om_inventory.json
    print(f"\nWriting {output_dir / 'source_om_inventory.json'}...")
    inventory_data = {
        "summary": {
            "source_workbook": str(excel_path.name),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
            "total_databases": len(databases),
            "total_schemas": len(schemas),
            "total_tables": len(tables),
            "total_columns": sum(len(cols) for cols in columns_by_table.values()),
            "v1_selected_tables": len(selected_table_keys),
        },
        "databases": list(databases.values()),
        "schemas": schema_summary,
    }
    with open(output_dir / "source_om_inventory.json", "w", encoding="utf-8") as f:
        json.dump(inventory_data, f, ensure_ascii=False, indent=2)

    # 2. selected_tables.csv
    print(f"Writing {output_dir / 'selected_tables.csv'}...")
    with open(output_dir / "selected_tables.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "catalog",
            "schema",
            "table_name",
            "table_fqn",
            "domain",
            "is_executable",
            "primary_grain",
            "column_count",
            "description",
        ])
        for t in selected_table_keys:
            cols = columns_by_table.get(t["fqn"], [])
            col_names = {c["name"] for c in cols}
            grain = detect_grain(t["name"], col_names)
            writer.writerow([
                t["catalog"],
                t["schema"],
                t["name"],
                t["fqn"],
                t["domain"],
                t["is_executable"],
                grain,
                len(cols),
                t["description"].replace("\n", " ").strip(),
            ])

    # 3. selected_columns.csv
    print(f"Writing {output_dir / 'selected_columns.csv'}...")
    total_cols_written = 0
    with open(output_dir / "selected_columns.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "table_fqn",
            "catalog",
            "schema",
            "table_name",
            "domain",
            "column_name",
            "column_fqn",
            "data_type",
            "data_type_display",
            "is_key_candidate",
            "description",
        ])
        for t in selected_table_keys:
            cols = columns_by_table.get(t["fqn"], [])
            for c in cols:
                is_key = is_key_column(c["name"])
                writer.writerow([
                    t["fqn"],
                    t["catalog"],
                    t["schema"],
                    t["name"],
                    t["domain"],
                    c["name"],
                    c["fqn"],
                    c["data_type"],
                    c["data_type_display"],
                    is_key,
                    c["description"].replace("\n", " ").strip(),
                ])
                total_cols_written += 1

    print(f"Total columns written: {total_cols_written}")
    print("\nPhase 1 outputs generated successfully!")


if __name__ == "__main__":
    main()
