"""Explicit keys, join paths and grains for the synthetic lakehouse."""
from extended_tables import GEO_HIERARCHY, anchor_for, table_kind

CORE_KEYS = {
 "aaa.ftth_account_pppoe": ["account_id"], "aaa.authentication": ["auth_id"],
 "aaa.accounting": ["accounting_id"], "aaa.access_event": ["event_id"],
 "aam.kpi_aam_daily_tdxl": ["kpi_id"], "aam.kpi_aam_daily_tlgd": ["kpi_id"],
 "acs.device_info": ["device_id"], "acs.f_uptime": ["uptime_id"],
 "acs.g_uptime": ["ne_id", "date_hour"], "acs.f_wifi": ["wifi_id"],
 "geo.location": ["location_id"], "inventory.station": ["station_id"],
 "ran.cell": ["cell_id"], "ran_kpi.cell_hourly": ["cell_id", "date_hour"],
 "transport.link_hourly": ["link_id", "date_hour"], "core.gateway_hourly": ["gateway_id", "date_hour"],
 "qos.service_hourly": ["service_id", "plan_id", "province_code", "date_hour"],
 "fault.alarm": ["alarm_id"], "ops.ticket": ["ticket_id"],
 "ops.technician_visit": ["visit_id"], "maintenance.work_order": ["work_order_id"],
 "customer.subscriber": ["customer_id"], "product.plan": ["plan_id"],
 "billing.invoice": ["invoice_id"], "billing.cost_center_daily": ["station_id", "cost_date"],
 "service.subscription": ["subscription_id"], "experience.complaint": ["complaint_id"],
 "energy.station_hourly": ["station_id", "date_hour"],
 "capacity.forecast_daily": ["station_id", "forecast_date"],
}
GEO_KEYS = {f"geo.{table}":[f"{table}_code"] for table in GEO_HIERARCHY}

# (source table, source column, target table, target unique column).
CORE_LINKS = [
 ("geo.area","country_code","geo.country","country_code"),
 ("geo.province","area_code","geo.area","area_code"),
 ("geo.province","country_code","geo.country","country_code"),
 ("geo.district","province_code","geo.province","province_code"),
 ("geo.ward","district_code","geo.district","district_code"),
 ("geo.village","ward_code","geo.ward","ward_code"),
 ("geo.location","country_code","geo.country","country_code"),
 ("geo.location","area_code","geo.area","area_code"),
 ("geo.location","province_code","geo.province","province_code"),
 ("geo.location","district_code","geo.district","district_code"),
 ("aaa.ftth_account_pppoe","customer_id","customer.subscriber","customer_id"),
 ("aaa.ftth_account_pppoe","plan_id","product.plan","plan_id"),
 ("aaa.authentication","account_id","aaa.ftth_account_pppoe","account_id"),
 ("aaa.accounting","account_id","aaa.ftth_account_pppoe","account_id"),
 ("aaa.accounting","session_id","aaa.authentication","session_id"),
 ("aaa.access_event","account_id","aaa.ftth_account_pppoe","account_id"),
 ("aaa.access_event","customer_id","customer.subscriber","customer_id"),
 ("aaa.access_event","device_id","acs.device_info","device_id"),
 ("aam.kpi_aam_daily_tlgd","province_code","geo.province","province_code"),
 ("acs.device_info","customer_id","customer.subscriber","customer_id"),
 ("acs.device_info","account_id","aaa.ftth_account_pppoe","account_id"),
 ("acs.device_info","station_id","inventory.station","station_id"),
 ("acs.f_uptime","device_id","acs.device_info","device_id"),
 ("acs.f_uptime","station_id","inventory.station","station_id"),
 ("acs.g_uptime","ne_id","acs.device_info","ne_id"),
 ("acs.f_wifi","device_id","acs.device_info","device_id"),
 ("inventory.station","location_id","geo.location","location_id"),
 ("ran.cell","station_id","inventory.station","station_id"),
 ("ran_kpi.cell_hourly","cell_id","ran.cell","cell_id"),
 ("ran_kpi.cell_hourly","station_id","inventory.station","station_id"),
 ("transport.link_hourly","from_station_id","inventory.station","station_id"),
 ("transport.link_hourly","to_station_id","inventory.station","station_id"),
 ("core.gateway_hourly","province_code","geo.province","province_code"),
 ("qos.service_hourly","plan_id","product.plan","plan_id"),
 ("qos.service_hourly","province_code","geo.province","province_code"),
 ("fault.alarm","entity_id","ran.cell","cell_id"),
 ("fault.alarm","station_id","inventory.station","station_id"),
 ("fault.alarm","ticket_id","ops.ticket","ticket_id"),
 ("ops.ticket","alarm_id","fault.alarm","alarm_id"),
 ("ops.ticket","station_id","inventory.station","station_id"),
 ("ops.technician_visit","work_order_id","maintenance.work_order","work_order_id"),
 ("ops.technician_visit","ticket_id","ops.ticket","ticket_id"),
 ("ops.technician_visit","station_id","inventory.station","station_id"),
 ("maintenance.work_order","ticket_id","ops.ticket","ticket_id"),
 ("maintenance.work_order","station_id","inventory.station","station_id"),
 ("customer.subscriber","province_code","geo.province","province_code"),
 ("billing.invoice","customer_id","customer.subscriber","customer_id"),
 ("billing.invoice","account_id","aaa.ftth_account_pppoe","account_id"),
 ("billing.invoice","plan_id","product.plan","plan_id"),
 ("billing.invoice","province_code","geo.province","province_code"),
 ("billing.cost_center_daily","station_id","inventory.station","station_id"),
 ("service.subscription","customer_id","customer.subscriber","customer_id"),
 ("service.subscription","account_id","aaa.ftth_account_pppoe","account_id"),
 ("service.subscription","plan_id","product.plan","plan_id"),
 ("service.subscription","station_id","inventory.station","station_id"),
 ("experience.complaint","customer_id","customer.subscriber","customer_id"),
 ("experience.complaint","account_id","aaa.ftth_account_pppoe","account_id"),
 ("experience.complaint","station_id","inventory.station","station_id"),
 ("experience.complaint","ticket_id","ops.ticket","ticket_id"),
 ("energy.station_hourly","station_id","inventory.station","station_id"),
 ("capacity.forecast_daily","station_id","inventory.station","station_id"),
]

def metadata(specs):
    tables=[]
    relationships=[{"from_table":s,"from_column":sc,"to_table":t,"to_column":tc,"cardinality":"many_to_one","basis":"synthetic_core"} for s,sc,t,tc in CORE_LINKS]
    for schema, items in specs.items():
        for table in items:
            name=f"{schema}.{table}"
            if name in CORE_KEYS:
                key=CORE_KEYS[name]; kind="core"
            elif name in GEO_KEYS:
                key=GEO_KEYS[name]; kind="hierarchy"
            else:
                key=[f"{table}_id"]; kind=table_kind(table,schema)
                target, anchor=anchor_for(schema,table)
                relationships.append({"from_table":name,"from_column":anchor,"to_table":target,"to_column":anchor,"cardinality":"many_to_one","basis":"synthetic_assumption"})
            tables.append({"name":name,"primary_key":key,"kind":kind,"grain":("unique by "+", ".join(key)),"provenance":"source_derived" if name=="aam.kpi_aam_daily_tdxl" else "synthetic_assumption"})
    return {"tables":tables,"relationships":relationships,"caveats":[
        "Only 8 tables in the supplied metadata and 2 CSV samples are source-derived; remaining table definitions and relationships are design assumptions.",
        "The source KPI snapshot contains area and network rows without province codes; it has no province foreign key.",
        "Hive/Trino does not enforce the logical foreign keys; validate.py checks them against generated SQLite data.",
    ]}
