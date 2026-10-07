"""Preserve as many supplied table columns as the 10–40-column limit permits."""
from source_metadata import read_source_catalog

SOURCE_CATALOG = read_source_catalog()
SOURCE_TABLES = {item["table"]: item for item in SOURCE_CATALOG["tables"]}

UPTIME_EXCLUDE = {"hardware_version","url_connection","port_logic","port","splitter_code","village_name","village_code","location_name"}
WIFI_KEEP = {"duration","ne_id","created_date","wifi_name","wifi_max_bit_rate","wifi_channel","wifi_ssid","wifi_standard","wifi_total_bytes_sent","wifi_total_bytes_received","wifi_total_packets_sent","wifi_total_packets_received","wifi_total_associations","wifi_error_sent","wifi_error_received","wifi_total_psk_failures","wifi_total_integrity_failures","wifi_transmit_power","ip_address","connect_status","product_class","sw_version","hardware_version","manufacture","wifi_regulatory_domain"}
PROVINCE_NAMES = {"DBN":"Điện Biên","SLA":"Sơn La","CMU":"Cà Mau","NBH":"Ninh Bình","HCM":"Hồ Chí Minh","KHA":"Khánh Hòa"}

def type_name(source_type):
    t=source_type.upper()
    if t in ("BIGINT",): return "bigint"
    if t in ("INT","INTEGER","SMALLINT","TINYINT"): return "int"
    if t in ("DOUBLE","FLOAT","REAL","DECIMAL"): return "real"
    if t.startswith("TIMESTAMP"): return "timestamp"
    if t=="DATE": return "date"
    return "text"

def enrich_specs(specs):
    for full, item in SOURCE_TABLES.items():
        schema,table=full.split(".")
        if full=="aaa.accounting":
            current=[x for x in specs[schema][table].split(",") if x.split(":")[0] not in ("retry_count","province_code")]
        else:
            current=specs[schema][table].split(",")
        have={x.split(":")[0] for x in current}
        for col in item["columns"]:
            name=col["name"]
            if name in have: continue
            if full=="acs.f_uptime" and name in UPTIME_EXCLUDE: continue
            if full=="acs.f_wifi" and name not in WIFI_KEEP: continue
            current.append(f"{name}:{type_name(col['data_type'])}")
            have.add(name)
        if len(current)>40:
            raise ValueError(f"{full} exceeds 40 columns: {len(current)}")
        specs[schema][table]=",".join(current)

def source_default(table, name, dtype, v):
    """Derived values for additional source-named columns in synthetic rows."""
    prov=v.get("province_code","")
    event=v.get("event_time") or v.get("record_time") or v.get("start_time") or v.get("last_login_at") or v.get("computed_at") or "2026-08-20 00:00:00"
    if name=="date_hour": return str(event)[:13].replace(" ","-")
    if name in ("timestamp","created_date","last_contact_time"): return event
    if name=="country" or name=="country_code": return "VNM"
    if name=="country_name": return "Việt Nam"
    if name=="area_name": return v.get("area_code","")
    if name=="province_name": return PROVINCE_NAMES.get(prov,"")
    if name=="district_code": return prov+"001" if prov else ""
    if name=="district_name": return "Quận/Huyện 1 "+PROVINCE_NAMES.get(prov,"")
    if name=="village_code": return prov+"001W01V01" if prov else ""
    if name=="location_id" or name=="location_code":
        index=list(PROVINCE_NAMES).index(prov)+1 if prov in PROVINCE_NAMES else 0
        return f"LOC{index:03d}" if index else ""
    if name=="station_code": return v.get("station_id","")
    if name=="ne_id": return "NE"+str(v.get("device_id","")).removeprefix("CPE")
    if name=="serial_number": return "SYNTH"+str(v.get("device_id","")).removeprefix("CPE").zfill(8)
    if name=="pppoe_username": return "demo_acc"+str(v.get("device_id","")).removeprefix("CPE")
    if name=="ip": return v.get("nas_ip", "10.0.0.1")
    if name=="sbr_server": return "radius-"+str(prov).lower()
    if name=="hostname": return "radius-"+str(prov).lower()
    if name=="count": return v.get("connection_count",1)
    if name=="count_time": return "hourly"
    if name in ("accept","success_count","n_request_success"): return v.get("accept_count",v.get("success_count",0))
    if name=="reject": return v.get("reject_count",0)
    if name in ("request_current_rate","request_average_rate","request_peak_rate","t_request","total_transactions"):
        return v.get("request_count",1)
    if name.startswith("accept_"): return v.get("accept_count",0)
    if name.startswith("reject_"): return v.get("reject_count",0)
    if name in ("transactions_retried","total_retry_packets"): return v.get("retry_count",0)
    if name=="failed_authentication": return v.get("reject_count",0)
    if name=="start": return 1
    if name=="stop": return 1
    if name=="interim": return 0
    if name=="duration": return v.get("duration_s",v.get("uptime_delta_s",v.get("duration_ms",3600)))
    if name=="n_count": return 1
    if name=="type": return "synthetic"
    if name=="thread_hold": return v.get("threshold",0) or 0
    if name=="uptime": return v.get("uptime_s",0)
    if name=="uptime_delta": return v.get("uptime_delta_s",0)
    if name=="uptime_wanppp": return v.get("wan_uptime_s",0)
    if name=="uptime_wanppp_delta": return v.get("uptime_delta_s",0)
    if name=="sw_version": return v.get("firmware_version","1.2.1")
    if name=="manufacture": return "ZTE"
    if name=="product_class": return "CPE"
    if name=="network_type": return "FTTH"
    if name=="network_class": return "access"
    if name=="device_code" or name=="device_type_code": return "ONT"
    if name=="wifi_name" or name=="wifi_ssid": return v.get("ssid","")
    if name=="wifi_channel": return v.get("channel",36)
    if name=="wifi_standard": return v.get("standard","802.11ac")
    if name=="wifi_max_bit_rate": return v.get("tx_rate_mbps",100)
    if name=="wifi_regulatory_domain": return "VN"
    if name=="wifi_transmit_power": return 18
    if name=="wifi_total_associations": return v.get("client_count",0)
    if name=="wifi_total_bytes_sent": return v.get("client_count",0)*50_000_000
    if name=="wifi_total_bytes_received": return v.get("client_count",0)*150_000_000
    if name=="wifi_total_packets_sent": return v.get("client_count",0)*50_000
    if name=="wifi_total_packets_received": return v.get("client_count",0)*150_000
    if name in ("wifi_error_sent","wifi_error_received","wifi_total_psk_failures","wifi_total_integrity_failures"): return 0
    if name=="ip_address": return v.get("ip_address","100.64.0.1")
    if name=="connect_status": return "connected"
    if dtype in ("int","bigint","real"): return 0
    if dtype in ("timestamp","date"): return event
    return "0" if name.endswith(("rate","count","packet")) else ""
