"""Curated supplementary subject tables for each telecom schema.

Each name represents a distinct metric stream or entity history. The records
share a consistent reference spine so they can be joined across domains.
"""

TABLE_NAMES = {
 "aaa": "radius_server radius_request_hourly radius_response_hourly radius_reject_hourly radius_timeout_hourly radius_retry_hourly pppoe_session pppoe_disconnect_hourly nas_device nas_port_history ip_assignment_history ip_pool ip_pool_hourly auth_policy auth_policy_change credential_reset login_failure_hourly concurrent_session_hourly account_lockout_hourly realm_route",
 "aam": "kpi_definition kpi_threshold kpi_hourly_province kpi_daily_province kpi_hourly_area kpi_daily_area kpi_hourly_network kpi_daily_network kpi_breach_hourly kpi_breach_daily kpi_rollup_job kpi_quality_audit kpi_source_mapping kpi_target kpi_trend_daily kpi_baseline_daily kpi_anomaly_hourly kpi_alert_history kpi_dashboard_usage kpi_export_history",
 "acs": "ne_info cpe_config_history firmware_catalog firmware_rollout firmware_upgrade_event wan_interface wan_hourly lan_port lan_port_hourly wifi_radio wifi_radio_hourly wifi_client_hourly optical_rx_hourly optical_tx_hourly reboot_event configuration_change remote_command provisioning_event device_fault device_temperature_hourly",
 "geo": "country area province district ward village geo_boundary_history province_population_daily district_population_daily urban_classification terrain_profile climate_zone weather_hourly rainfall_hourly temperature_hourly location_alias station_coverage_area cell_coverage_area service_zone postal_zone",
 "inventory": "equipment_rack equipment_slot equipment_card equipment_port antenna feeder cable_segment splitter fiber_core optical_module battery_unit generator_unit rectifier_unit air_conditioner spare_part stock_balance_daily warehouse supplier purchase_order asset_movement site_lease",
 "ran": "sector carrier neighbor_relation intra_freq_neighbor inter_freq_neighbor handover_relation pci_assignment tac_assignment frequency_plan antenna_config mimo_config beam_config power_config rach_config scheduler_config admission_config cell_state_history cell_activation_event carrier_aggregation_config interference_relation",
 "ran_kpi": "cell_traffic_hourly cell_access_hourly cell_retention_hourly cell_mobility_hourly cell_availability_hourly cell_prb_hourly cell_throughput_hourly cell_latency_hourly cell_packet_loss_hourly cell_rach_hourly cell_rrc_hourly cell_handover_hourly cell_sinr_hourly cell_cqi_hourly cell_bler_hourly cell_mcs_hourly cell_modulation_hourly cell_energy_hourly cell_users_hourly cell_congestion_hourly",
 "transport": "fiber_route fiber_span fiber_fault_event microwave_link microwave_hourly router switch port port_hourly vlan mpls_tunnel mpls_hourly bgp_peer bgp_hourly optical_channel optical_hourly link_alarm link_utilization_daily path_reroute_event backbone_node",
 "core": "amf_node smf_node upf_node mme_node sgw_node pgw_node dns_node dhcp_node subscriber_attach_hourly bearer_setup_hourly session_setup_hourly session_drop_hourly core_latency_hourly core_cpu_hourly core_memory_hourly core_traffic_hourly apn_usage_hourly slice_usage_hourly gateway_alarm core_config_change",
 "qos": "sla_policy sla_target sla_result_hourly sla_result_daily application_hourly video_hourly gaming_hourly web_hourly voice_hourly download_hourly upload_hourly dns_hourly tcp_hourly udp_hourly jitter_hourly packet_loss_hourly latency_hourly throughput_hourly availability_hourly qos_breach_event",
 "fault": "alarm_rule alarm_suppression alarm_correlation alarm_escalation alarm_history fault_class fault_root_cause fault_impact_hourly fault_impact_daily cell_outage station_outage power_fault transport_fault device_fault fiber_cut degradation_event recurring_fault weather_related_fault maintenance_related_fault",
 "ops": "noc_shift noc_shift_handover ticket_history ticket_comment ticket_assignment ticket_escalation ticket_sla_hourly dispatch_request crew roster technician_skill technician_certification visit_checklist spare_part_usage repair_action repair_result incident_bridge incident_timeline operational_kpi_daily escalation_policy",
 "maintenance": "maintenance_plan preventive_schedule corrective_schedule inspection_schedule inspection_result work_order_history work_order_task work_order_material work_order_labor site_access_permit vendor_contract warranty_claim repair_log preventive_checklist battery_inspection generator_inspection fiber_inspection antenna_inspection maintenance_kpi_daily",
 "customer": "household customer_profile customer_contact customer_contact_history customer_segment customer_segment_history customer_risk_daily customer_value_daily customer_churn_score customer_consent customer_preference customer_address customer_device_map subscriber_status_history onboarding_event retention_offer campaign_exposure customer_feedback customer_interaction channel_usage_daily",
 "product": "product_catalog product_bundle product_feature plan_history plan_price_history plan_eligibility plan_upgrade_rule plan_discount promotion promotion_eligibility addon_catalog addon_subscription tariff_band speed_tier data_allowance contract_template service_entitlement product_availability product_usage_daily price_comparison",
 "billing": "invoice_line payment payment_attempt payment_method payment_reversal refund credit_note debit_note discount_applied tax_rule billing_cycle billing_adjustment overdue_balance aging_daily revenue_daily revenue_monthly collection_daily writeoff_event cost_allocation budget_daily",
 "service": "service_catalog service_order order_item activation_event provisioning_task suspension_event restoration_event termination_event subscription_history service_migration service_health_hourly service_usage_hourly service_usage_daily service_eligibility service_sla service_dependency service_endpoint service_config_history service_notification service_incident_link",
 "experience": "survey survey_response nps_daily csat_daily complaint_history complaint_category complaint_resolution complaint_sla complaint_escalation contact_center_call chat_session app_feedback network_experience_hourly speed_test speed_test_daily outage_notification sentiment_daily repeat_contact_daily journey_event customer_effort_daily",
 "energy": "meter meter_reading_hourly grid_supply_hourly generator_hourly solar_hourly battery_hourly load_hourly power_quality_hourly energy_cost_daily energy_budget_daily carbon_emission_daily cooling_hourly temperature_alarm power_outage_event fuel_refill generator_maintenance battery_health_daily renewable_mix_daily energy_anomaly_hourly tariff_history",
 "capacity": "cell_capacity_daily station_capacity_daily backhaul_capacity_daily core_capacity_daily spectrum_capacity_daily port_capacity_daily storage_capacity_daily forecast_hourly forecast_monthly demand_daily demand_monthly utilization_daily saturation_event expansion_plan expansion_project upgrade_candidate planning_scenario investment_case capacity_alert capacity_model_run",
}

# Keep 20 focused tables per schema. These subjects can be derived from a kept
# table or do not have enough independent source evidence to justify a table.
PRUNED_TABLES = {
 "aaa": {"radius_response_hourly":"derived from request and outcome counts", "radius_retry_hourly":"retry_count is already in authentication", "pppoe_disconnect_hourly":"accounting.stop_time covers disconnects", "realm_route":"no independent source mapping"},
 "aam": {"kpi_dashboard_usage":"application audit outside KPI source", "kpi_export_history":"application audit outside KPI source"},
 "acs": {"ne_info":"overlaps device_info", "wifi_radio_hourly":"overlaps f_wifi", "device_temperature_hourly":"temperature already in f_uptime", "lan_port_hourly":"port-level detail is retained in lan_port"},
 "geo": {"postal_zone":"not supported by the supplied geography"},
 "inventory": {"equipment_slot":"rack and card retain the hierarchy", "feeder":"cable_segment covers this fixture"},
 "ran": {"interference_relation":"not supported by the sample KPIs"},
 "ran_kpi": {"cell_energy_hourly":"energy.station_hourly covers energy"},
 "transport": {"link_utilization_daily":"derivable from link_hourly"},
 "core": {"core_cpu_hourly":"cpu_pct already in gateway_hourly"},
 "qos": {"availability_hourly":"availability_pct already in service_hourly"},
 "ops": {"repair_result":"ticket resolution_code captures outcome", "incident_bridge":"no independent source evidence"},
 "customer": {"customer_profile":"subscriber contains core profile"},
 "product": {"price_comparison":"derivable from plan and price history"},
 "billing": {"aging_daily":"derivable from overdue_balance", "debit_note":"no independent source evidence"},
 "service": {"service_usage_daily":"derivable from service_usage_hourly"},
 "experience": {"speed_test_daily":"derivable from speed_test"},
 "energy": {"energy_budget_daily":"budget_daily retained in billing"},
 "capacity": {"demand_monthly":"derivable from demand_daily"},
}

DOMAIN_COLUMNS = {
 "aaa": "request_count:int,success_count:int,reject_count:int,latency_ms:real",
 "aam": "sample_count:int,breach_count:int,baseline_value:real,change_pct:real",
 "acs": "temperature_c:real,uptime_s:int,retry_count:int,signal_dbm:real",
 "geo": "latitude:real,longitude:real,population_est:int,coverage_pct:real",
 "inventory": "asset_count:int,installed_count:int,age_days:int,unit_cost_vnd:int",
 "ran": "frequency_mhz:int,bandwidth_mhz:int,tx_power_dbm:real,sector_count:int",
 "ran_kpi": "attempt_count:int,success_count:int,traffic_gb:real,availability_pct:real",
 "transport": "capacity_mbps:real,utilization_pct:real,latency_ms:real,packet_loss_pct:real",
 "core": "session_count:int,request_count:int,success_count:int,cpu_pct:real",
 "qos": "request_count:int,success_count:int,p95_latency_ms:real,breach_count:int",
 "fault": "impact_users:int,duration_min:int,repeat_count:int,priority_score:int",
 "ops": "sla_minutes:int,response_minutes:int,resolution_minutes:int,reopen_count:int",
 "maintenance": "planned_duration_min:int,actual_duration_min:int,part_count:int,labor_cost_vnd:int",
 "customer": "tenure_months:int,interaction_count:int,satisfaction_score:int,churn_score:real",
 "product": "monthly_fee_vnd:int,down_mbps:int,up_mbps:int,eligible_count:int",
 "billing": "amount_vnd:int,tax_vnd:int,paid_vnd:int,outstanding_vnd:int",
 "service": "request_count:int,success_count:int,active_count:int,latency_ms:real",
 "experience": "response_count:int,positive_count:int,score:real,repeat_count:int",
 "energy": "grid_kwh:real,generator_kwh:real,load_kw:real,cost_vnd:int",
 "capacity": "demand_mbps:real,available_mbps:real,utilization_pct:real,forecast_error_pct:real",
}

ANCHORS = {
    "aaa": ("aaa.ftth_account_pppoe", "account_id"),
    "aam": ("geo.location", "location_id"),
    "acs": ("acs.device_info", "device_id"),
    "geo": ("geo.location", "location_id"),
    "inventory": ("inventory.station", "station_id"),
    "ran": ("ran.cell", "cell_id"),
    "ran_kpi": ("ran.cell", "cell_id"),
    "transport": ("inventory.station", "station_id"),
    "core": ("geo.location", "location_id"),
    "qos": ("product.plan", "plan_id"),
    "fault": ("inventory.station", "station_id"),
    "ops": ("inventory.station", "station_id"),
    "maintenance": ("inventory.station", "station_id"),
    "customer": ("customer.subscriber", "customer_id"),
    "product": ("product.plan", "plan_id"),
    "billing": ("billing.invoice", "invoice_id"),
    "service": ("service.subscription", "subscription_id"),
    "experience": ("customer.subscriber", "customer_id"),
    "energy": ("inventory.station", "station_id"),
    "capacity": ("inventory.station", "station_id"),
}

GEO_HIERARCHY = {
    "country": "country_code:text,country_name:text,iso2:text,region:text,currency:text,timezone:text,active_from:date,active_to:date,status:text,source_system:text",
    "area": "area_code:text,country_code:text,area_name:text,sort_order:int,province_count:int,timezone:text,active_from:date,active_to:date,status:text,source_system:text",
    "province": "province_code:text,area_code:text,country_code:text,province_name:text,urban_flag:int,latitude:real,longitude:real,district_count:int,active_from:date,status:text,source_system:text",
    "district": "district_code:text,province_code:text,district_name:text,administrative_type:text,latitude:real,longitude:real,ward_count:int,active_from:date,status:text,source_system:text",
    "ward": "ward_code:text,district_code:text,ward_name:text,administrative_type:text,latitude:real,longitude:real,population_est:int,active_from:date,status:text,source_system:text",
    "village": "village_code:text,ward_code:text,village_name:text,latitude:real,longitude:real,population_est:int,active_from:date,status:text,source_system:text,village_type:text",
}

ANCHOR_OVERRIDES = {
    ("aaa", name): ("geo.location", "location_id") for name in
    ("radius_server", "nas_device", "ip_pool", "auth_policy", "realm_route")
} | {
    ("billing", name): ("inventory.station", "station_id") for name in
    ("cost_allocation", "budget_daily", "revenue_daily", "revenue_monthly", "collection_daily")
} | {
    ("inventory", name): ("geo.location", "location_id") for name in
    ("warehouse", "supplier", "purchase_order", "stock_balance_daily")
} | {
    ("service", name): ("product.plan", "plan_id") for name in
    ("service_catalog", "service_eligibility")
} | {
    ("fault", name): ("fault.alarm", "alarm_id") for name in
    ("alarm_history", "alarm_suppression", "alarm_correlation", "alarm_escalation")
} | {
    ("ops", name): ("ops.ticket", "ticket_id") for name in
    ("ticket_history", "ticket_comment", "ticket_assignment", "ticket_escalation", "ticket_sla_hourly", "dispatch_request")
} | {
    ("maintenance", name): ("maintenance.work_order", "work_order_id") for name in
    ("work_order_history", "work_order_task", "work_order_material", "work_order_labor", "repair_log")
} | {
    ("experience", name): ("experience.complaint", "complaint_id") for name in
    ("complaint_history", "complaint_resolution", "complaint_sla", "complaint_escalation")
}

def anchor_for(schema, table):
    return ANCHOR_OVERRIDES.get((schema, table), ANCHORS[schema])

EVENT_MARKERS = ("event", "history", "attempt", "response", "payment", "refund", "call", "session", "complaint", "order", "alert", "fault", "alarm", "ticket", "inspection", "movement", "interaction", "exposure", "outage", "anomaly", "change", "upgrade", "handover", "reset", "rollout", "suspension", "restoration", "termination", "migration", "reversal", "writeoff", "escalation", "dispatch", "visit", "repair", "notification")
OBSERVATION_MARKERS = ("hourly", "daily", "monthly", "reading", "usage", "balance", "score", "forecast", "trend", "audit", "breach", "export", "quality", "traffic", "utilization", "kpi", "result", "survey", "test", "health", "demand", "revenue", "collection")
KIND_OVERRIDES = {
 ("aam","kpi_definition"):"entity", ("aam","kpi_threshold"):"entity", ("aam","kpi_source_mapping"):"entity", ("aam","kpi_target"):"entity",
 ("fault","alarm_rule"):"entity", ("fault","fault_class"):"entity", ("fault","fault_root_cause"):"entity",
 ("ops","escalation_policy"):"entity", ("ops","incident_timeline"):"event",
 ("billing","payment_method"):"entity", ("product","plan_upgrade_rule"):"entity",
 ("experience","complaint_category"):"entity", ("acs","remote_command"):"event",
}
TABLE_EXTRA_COLUMNS = {
 ("geo","location_alias"): "alias_name:text,alias_type:text,language_code:text,normalized_name:text",
 ("geo","geo_boundary_history"): "boundary_version:text,change_reason:text,area_km2:real,effective_date:date",
 ("geo","district_population_daily"): "population_count:int,household_count:int,density_per_km2:real",
 ("geo","province_population_daily"): "population_count:int,household_count:int,density_per_km2:real",
 ("maintenance","antenna_inspection"): "tilt_deg:real,azimuth_deg:int,vswr:real,connector_condition:text,inspection_result:text",
 ("maintenance","battery_inspection"): "voltage_v:real,capacity_pct:real,terminal_condition:text,inspection_result:text",
 ("maintenance","generator_inspection"): "fuel_level_pct:real,oil_pressure_kpa:real,start_test_result:text,inspection_result:text",
 ("maintenance","fiber_inspection"): "optical_loss_db:real,connector_cleanliness:text,inspection_result:text",
}

def table_kind(table, schema=None):
    if schema is not None and (schema,table) in KIND_OVERRIDES:
        return KIND_OVERRIDES[(schema,table)]
    if any(marker in table for marker in ("hourly", "daily", "monthly")):
        return "observation"
    if any(marker in table for marker in EVENT_MARKERS):
        return "event"
    if any(marker in table for marker in OBSERVATION_MARKERS):
        return "observation"
    return "entity"

def is_stream(table, schema=None):
    return table_kind(table,schema) != "entity"

def extension_columns(schema, table):
    if schema == "geo" and table in GEO_HIERARCHY:
        return GEO_HIERARCHY[table]
    anchor = anchor_for(schema, table)[1]
    base = f"{table}_id:text,{anchor}:text,province_code:text,area_code:text,status:text"
    kind = table_kind(table,schema)
    if kind == "entity":
        detail = "code:text,name:text,category:text,effective_from:date,effective_to:date,source_system:text"
    elif kind == "observation":
        detail = "date_hour:text,observed_at:timestamp,metric_value:real,metric_unit:text,quality_flag:text,source_system:text"
    else:
        detail = "event_time:timestamp,event_code:text,severity:text,outcome:text,duration_s:int,source_system:text"
    extra = TABLE_EXTRA_COLUMNS.get((schema,table))
    return base + "," + detail + "," + DOMAIN_COLUMNS[schema] + ("," + extra if extra else "")

def extend_specs(specs):
    for schema, names in TABLE_NAMES.items():
        for name in names.split():
            if name in PRUNED_TABLES.get(schema, {}):
                continue
            if name in specs[schema]:
                raise ValueError(f"Duplicate table: {schema}.{name}")
            specs[schema][name] = extension_columns(schema, name)
    counts = {schema: len(tables) for schema, tables in specs.items()}
    if not all(20 <= count <= 35 for count in counts.values()):
        raise ValueError(f"Expected 20-35 tables per schema: {counts}")
