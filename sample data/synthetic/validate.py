"""Validate the generated fixture and its intended cross-schema relationships."""
import json
import sqlite3
import collections
import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent / "generated"
catalog = json.loads((OUT / "catalog.json").read_text(encoding="utf-8"))
model = json.loads((OUT / "schema_relationships.json").read_text(encoding="utf-8"))
source = json.loads((OUT / "source_metadata.json").read_text(encoding="utf-8"))
con = sqlite3.connect(OUT / "telecom.sqlite")
issues = []
check_count = 0

def check(label, sql):
    global check_count
    check_count += 1
    count = con.execute(sql).fetchone()[0]
    if count: issues.append(f"{label}: {count} bad rows")

assert len({x["schema"] for x in catalog}) == 20
by_schema = {s: sum(x["schema"] == s for x in catalog) for s in {x["schema"] for x in catalog}}
assert all(n == 20 for n in by_schema.values()), by_schema
physical = {name for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert physical == {x["sqlite_table"] for x in catalog}, "SQLite tables differ from catalog"
assert len(catalog) == 400
assert con.execute("SELECT COUNT(*) FROM experience__complaint WHERE ticket_id IS NULL").fetchone()[0] > 0
for x in catalog:
    if any(c["name"] == "effective_to" for c in x["columns"]):
        table = x["sqlite_table"]
        current, closed = con.execute(
            f'SELECT SUM(effective_to IS NULL), SUM(effective_to IS NOT NULL) FROM "{table}"'
        ).fetchone()
        assert current and closed, table
assert len(source["tables"]) == 8
assert sum(len(t["columns"]) for t in source["tables"]) == 179
for x in catalog:
    assert 10 <= len(x["columns"]) <= 40
    actual = con.execute(f'SELECT COUNT(*) FROM "{x["sqlite_table"]}"').fetchone()[0]
    assert actual == x["row_count"] and actual > 0, x["sqlite_table"]
    csv_path=OUT/x["csv"]
    with csv_path.open(encoding="utf-8",newline="") as f:
        reader=csv.reader(f)
        header=next(reader)
        expected=[col["name"] for col in x["columns"]]
        assert header==expected, csv_path
        count=0
        for record in reader:
            count+=1
            if len(record)!=len(header): issues.append(f"{csv_path}: row {count} width {len(record)} != {len(header)}")
        if count!=actual: issues.append(f"{csv_path}: CSV rows {count} != SQLite rows {actual}")
assert len(list(OUT.glob("*/*.csv")))==len(catalog)

check("cell to station", 'SELECT COUNT(*) FROM ran__cell c LEFT JOIN inventory__station s ON c.station_id=s.station_id WHERE s.station_id IS NULL')
check("cell KPI to cell", 'SELECT COUNT(*) FROM ran_kpi__cell_hourly k LEFT JOIN ran__cell c ON k.cell_id=c.cell_id WHERE c.cell_id IS NULL')
check("cell KPI duplicate grain", 'SELECT COUNT(*) FROM (SELECT cell_id,date_hour,COUNT(*) n FROM ran_kpi__cell_hourly GROUP BY 1,2 HAVING n>1)')
check("cell KPI bounds", 'SELECT COUNT(*) FROM ran_kpi__cell_hourly WHERE rrc_success>rrc_attempt OR ho_success>ho_attempt OR availability_pct<0 OR availability_pct>100 OR dl_traffic_gb<0 OR ul_traffic_gb<0')
check("cell KPI UTC offset", "SELECT COUNT(*) FROM ran_kpi__cell_hourly WHERE strftime('%Y-%m-%d-%H',utc_time_ms/1000,'unixepoch','+7 hours')<>date_hour")
check("account to customer", 'SELECT COUNT(*) FROM aaa__ftth_account_pppoe a LEFT JOIN customer__subscriber c ON a.customer_id=c.customer_id WHERE c.customer_id IS NULL')
check("subscription keys", 'SELECT COUNT(*) FROM service__subscription s LEFT JOIN customer__subscriber c ON s.customer_id=c.customer_id LEFT JOIN product__plan p ON s.plan_id=p.plan_id WHERE c.customer_id IS NULL OR p.plan_id IS NULL')
check("authentication account", 'SELECT COUNT(*) FROM aaa__authentication a LEFT JOIN aaa__ftth_account_pppoe p ON a.account_id=p.account_id WHERE p.account_id IS NULL')
check("accounting to accepted auth", "SELECT COUNT(*) FROM aaa__accounting a LEFT JOIN aaa__authentication h ON a.session_id=h.session_id AND h.result='accept' WHERE h.session_id IS NULL")
check("invoice arithmetic", 'SELECT COUNT(*) FROM billing__invoice WHERE total_vnd<>base_amount_vnd+adjustment_vnd+tax_vnd OR paid_vnd>total_vnd')
check("invoice plan fee", 'SELECT COUNT(*) FROM billing__invoice i JOIN product__plan p ON i.plan_id=p.plan_id WHERE i.base_amount_vnd<>p.monthly_fee_vnd')
check("KPI ratio", 'SELECT COUNT(*) FROM aam__kpi_aam_daily_tlgd WHERE ABS(success_rate - 100.0*success_count/request_count)>.0001')
check("cost arithmetic", 'SELECT COUNT(*) FROM billing__cost_center_daily WHERE total_cost_vnd<>energy_cost_vnd+maintenance_cost_vnd+transport_cost_vnd+depreciation_vnd OR variance_vnd<>total_cost_vnd-budget_vnd')
check("alarm to ticket", 'SELECT COUNT(*) FROM fault__alarm a LEFT JOIN ops__ticket t ON a.ticket_id=t.ticket_id WHERE t.ticket_id IS NULL')
check("ticket to work order", 'SELECT COUNT(*) FROM maintenance__work_order w LEFT JOIN ops__ticket t ON w.ticket_id=t.ticket_id WHERE t.ticket_id IS NULL')
check("device to station", 'SELECT COUNT(*) FROM acs__device_info d LEFT JOIN inventory__station s ON d.station_id=s.station_id WHERE s.station_id IS NULL')
check("station hourly grain", 'SELECT COUNT(*) FROM (SELECT station_id,date_hour,COUNT(*) n FROM energy__station_hourly GROUP BY 1,2 HAVING n>1)')
check("uptime rollup to observation", 'SELECT COUNT(*) FROM acs__g_uptime g LEFT JOIN acs__f_uptime f ON g.ne_id=f.ne_id AND g.date_hour=f.date_hour WHERE f.ne_id IS NULL OR CAST(g.uptime AS INTEGER)<>f.uptime_s OR CAST(g.uptime_delta AS INTEGER)<>f.uptime_delta_s')
check("uptime delta between observations", 'SELECT COUNT(*) FROM (SELECT device_id,uptime_s,uptime_delta_s,LAG(uptime_s) OVER (PARTITION BY device_id ORDER BY record_time) prior FROM acs__f_uptime) WHERE prior IS NOT NULL AND uptime_delta_s<>uptime_s-prior')
check("three blocked access events", 'SELECT ABS(COUNT(*)-3) FROM aaa__access_event WHERE result="blocked"')
check("blocked events to rejected authentication", "SELECT COUNT(*) FROM aaa__access_event e LEFT JOIN aaa__authentication a ON e.account_id=a.account_id AND e.event_time=a.event_time AND a.result='reject' WHERE a.auth_id IS NULL")
check("Wi-Fi NE to device", 'SELECT COUNT(*) FROM acs__f_wifi w JOIN acs__device_info d ON w.device_id=d.device_id WHERE w.ne_id<>d.ne_id')
check("source KPI row count", 'SELECT ABS(COUNT(*)-40) FROM aam__kpi_aam_daily_tdxl')
check("antenna inspection bounds", 'SELECT COUNT(*) FROM maintenance__antenna_inspection WHERE vswr<1 OR vswr>2 OR tilt_deg<0 OR tilt_deg>20 OR inspection_result NOT IN ("pass","fail")')
check("district population consistency", 'SELECT COUNT(*) FROM geo__district_population_daily WHERE metric_value<>population_count OR household_count>population_count OR density_per_km2<=0')
by_name={x["schema"]+"."+x["table"]:x for x in catalog}
assert len(model["tables"])==len(catalog)
for x in catalog:
    table = x["sqlite_table"]
    names = {c["name"] for c in x["columns"]}
    assert set(x["primary_key"])<=names
    check(f"{table} null PK", f'SELECT COUNT(*) FROM "{table}" WHERE '+" OR ".join(f'"{c}" IS NULL' for c in x["primary_key"]))
    if x.get("origin") != "synthetic_extension":
        continue
    assert x["description"]
    if "date_hour" in names:
        check(f"{table} time", f'SELECT COUNT(*) FROM "{table}" WHERE strftime("%Y-%m-%d-%H",observed_at)<>date_hour')
        if "_daily" in x["table"] or "_monthly" in x["table"]:
            check(f"{table} daily/monthly boundary", f'SELECT COUNT(*) FROM "{table}" WHERE substr(date_hour,12,2)<>"00"')
        incident_anchor=bool(x["foreign_keys"] and x["foreign_keys"][0]["column"] in ("alarm_id","ticket_id","work_order_id","complaint_id"))
        if not incident_anchor and "_hourly" in x["table"]:
            if x["row_count"]!=432: issues.append(f"{table}: hourly stream has {x['row_count']} rows, expected 432")
        elif not incident_anchor and "_daily" in x["table"]:
            if x["row_count"]!=18: issues.append(f"{table}: daily stream has {x['row_count']} rows, expected 18")
        elif not incident_anchor and "_monthly" in x["table"]:
            if x["row_count"]!=6: issues.append(f"{table}: monthly stream has {x['row_count']} rows, expected 6")
    if "event_time" in names:
        check(f"{table} event time", f'SELECT COUNT(*) FROM "{table}" WHERE event_time IS NULL')
    if "effective_from" in names:
        check(f"{table} effective date", f'SELECT COUNT(*) FROM "{table}" WHERE effective_from IS NULL')
    if "date_hour" in names:
        anchor=x["foreign_keys"][0]["column"] if x["foreign_keys"] else None
        if anchor:
            check(f"{table} business grain", f'SELECT COUNT(*) FROM (SELECT "{anchor}",province_code,date_hour,COUNT(*) n FROM "{table}" GROUP BY 1,2,3 HAVING n>1)')
    if "request_count" in names and "success_count" in names:
        check(f"{table} outcome", f'SELECT COUNT(*) FROM "{table}" WHERE success_count>request_count OR success_count<0')
    if "amount_vnd" in names:
        check(f"{table} balance", f'SELECT COUNT(*) FROM "{table}" WHERE outstanding_vnd<>amount_vnd+tax_vnd-paid_vnd')
    if "demand_mbps" in names:
        check(f"{table} utilization", f'SELECT COUNT(*) FROM "{table}" WHERE ABS(utilization_pct - 100.0*demand_mbps/available_mbps)>.01')
    if x["schema"]=="product":
        check(f"{table} plan values",f'SELECT COUNT(*) FROM "{table}" e JOIN product__plan p ON e.plan_id=p.plan_id WHERE e.monthly_fee_vnd<>p.monthly_fee_vnd OR e.down_mbps<>p.down_mbps OR e.up_mbps<>p.up_mbps')
    if x["schema"]=="billing" and "invoice_id" in names:
        check(f"{table} invoice values",f'SELECT COUNT(*) FROM "{table}" e JOIN billing__invoice i ON e.invoice_id=i.invoice_id WHERE e.amount_vnd<>i.base_amount_vnd OR e.tax_vnd<>i.tax_vnd OR e.paid_vnd<>i.paid_vnd')
    if x["schema"]=="energy":
        check(f"{table} energy cost",f'SELECT COUNT(*) FROM "{table}" WHERE cost_vnd<>ROUND(grid_kwh*2300+generator_kwh*4000)')
    if x["table"]=="antenna_inspection":
        check("antenna inspection daily cadence",f'SELECT ABS(COUNT(*)-18) FROM "{table}"')
for link in model["relationships"]:
    src=link["from_table"].replace(".","__")
    dst=link["to_table"].replace(".","__")
    src_col=link["from_column"]; dst_col=link["to_column"]
    check(f"{src}.{src_col} -> {dst}.{dst_col}",f'SELECT COUNT(*) FROM "{src}" s LEFT JOIN "{dst}" d ON s."{src_col}"=d."{dst_col}" WHERE s."{src_col}" IS NOT NULL AND d."{dst_col}" IS NULL')
    if src_col!="to_station_id" and "province_code" in {c["name"] for c in by_name[link["from_table"]]["columns"]} and "province_code" in {c["name"] for c in by_name[link["to_table"]]["columns"]}:
        check(f"{src}.{src_col} province",f'SELECT COUNT(*) FROM "{src}" s JOIN "{dst}" d ON s."{src_col}"=d."{dst_col}" WHERE s.province_code<>d.province_code')
con.close()
source_coverage={}
by_name={x["schema"]+"."+x["table"]:x for x in catalog}
for item in source["tables"]:
    name=item["table"]
    generated=by_name[name]
    source_names={c["name"] for c in item["columns"]}
    generated_names={c["name"] for c in generated["columns"]}
    source_coverage[name]={"source_columns":len(source_names),"generated_columns":len(generated_names),"exact_name_matches":len(source_names&generated_names)}
    if not generated["description"]:
        issues.append(f"{name}: missing source description")
with (OUT.parent.parent/"Query result 20-08-2026(1).csv").open(encoding="utf-8-sig",newline="") as f:
    sample_rows=list(csv.DictReader(f))
snapshot=[]
with (OUT/"aam"/"kpi_aam_daily_tdxl.csv").open(encoding="utf-8",newline="") as f:
    snapshot=list(csv.DictReader(f))
if len(sample_rows)!=len(snapshot): issues.append("source KPI snapshot row count differs")
else:
    for i,(original,generated) in enumerate(zip(sample_rows,snapshot),1):
        for field in ("kpi_code","location_level","date_hour"):
            if original[field]!=generated[field]: issues.append(f"source KPI row {i}: {field} changed")
        for field in ("area_name","province_name","province_code"):
            cleaned="" if original[field] in ("","null") else original[field]
            if cleaned!=generated[field]: issues.append(f"source KPI row {i}: {field} changed beyond null normalization")
        if original["kpi_value"] not in ("","null") and float(original["kpi_value"])!=float(generated["kpi_value"]): issues.append(f"source KPI row {i}: value changed")
with (OUT.parent.parent/"sample_data_100_rows(1).csv").open(encoding="utf-8-sig",newline="") as f:
    sample_cells={r["object_id"]:r for r in csv.DictReader(f)}
with (OUT/"ran"/"cell.csv").open(encoding="utf-8",newline="") as f:
    for generated in csv.DictReader(f):
        oid=generated["object_id"]
        if not oid.startswith("SYNTH-") and (oid not in sample_cells or sample_cells[oid]["province_code"]!=generated["province_code"]):
            issues.append(f"ran.cell: source object {oid} has incorrect province")
required_matches={"aaa.ftth_account_pppoe":6,"aaa.authentication":27,"aaa.accounting":29,"aam.kpi_aam_daily_tdxl":8,"aam.kpi_aam_daily_tlgd":9,"acs.f_uptime":32,"acs.g_uptime":10,"acs.f_wifi":26}
for name,minimum in required_matches.items():
    if source_coverage[name]["exact_name_matches"]<minimum: issues.append(f"{name}: source column coverage below {minimum}")
report={"status":"fail" if issues else "pass","schemas":len(by_schema),"tables":len(catalog),"rows":sum(x["row_count"] for x in catalog),"relationships":len(model["relationships"]),"sql_checks_run":check_count,"csv_tables_checked":len(catalog),"source_kpi_rows_compared":len(sample_rows),"tables_per_schema":dict(sorted(by_schema.items())),"source_metadata_tables":len(source["tables"]),"source_metadata_columns":sum(len(t["columns"]) for t in source["tables"]),"source_column_coverage":source_coverage,"issues":issues}
(OUT/"validation_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if issues:
    raise SystemExit("FAIL\n" + "\n".join(issues))
print(f"PASS: {len(by_schema)} schemas, {len(catalog)} tables, {report['rows']} rows, {len(model['relationships'])} relationships, {check_count} checks")
