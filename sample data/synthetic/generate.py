"""Deterministic, connected telecom lakehouse fixture. Python standard library only."""
from __future__ import annotations

import csv
import datetime as dt
import json
import random
import sqlite3
import unicodedata
from pathlib import Path
from extended_tables import GEO_HIERARCHY, PRUNED_TABLES, TABLE_NAMES, anchor_for, extend_specs, is_stream, table_kind
from relationship_model import metadata as relationship_metadata
from source_metadata import read_source_catalog
from source_enrichment import SOURCE_TABLES, enrich_specs, source_default

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent
OUT = ROOT / "generated"
RNG = random.Random(20260921)
HOURS = [dt.datetime(2026, 8, 18) + dt.timedelta(hours=i) for i in range(72)]
AREAS = [("KV1", "DBN", "Điện Biên"), ("KV1", "SLA", "Sơn La"),
         ("KV3", "CMU", "Cà Mau"), ("KV1", "NBH", "Ninh Bình"),
         ("KV3", "HCM", "Hồ Chí Minh"), ("KV2", "KHA", "Khánh Hòa")]
COORDS = {"DBN":(21.38,103.02),"SLA":(21.33,103.91),"CMU":(9.18,105.15),
          "NBH":(20.25,105.97),"HCM":(10.82,106.63),"KHA":(12.26,109.19)}
SCHEMA_DESCRIPTIONS = {
 "aaa":"Tài khoản PPPoE, xác thực, phiên truy cập và các chỉ số AAA.",
 "aam":"Định nghĩa KPI, kết quả tổng hợp và kiểm soát chất lượng KPI.",
 "acs":"Thiết bị CPE/ONT, uptime, Wi-Fi và quản lý cấu hình từ ACS.",
 "geo":"Phân cấp địa giới, vị trí trạm, vùng phủ và dữ liệu địa lý tham chiếu.",
 "inventory":"Trạm, thiết bị vật lý, phụ tùng và tài sản hạ tầng.",
 "ran":"Cấu hình cell vô tuyến, sóng mang, láng giềng và tham số điều khiển.",
 "ran_kpi":"Các phép đo lưu lượng, truy nhập, chất lượng và khả dụng cell theo thời gian.",
 "transport":"Đường truyền quang/vô tuyến, cổng mạng, định tuyến và chỉ số truyền dẫn.",
 "core":"Nút mạng lõi, phiên dữ liệu, gateway và hiệu năng hệ thống lõi.",
 "qos":"Chính sách SLA và các thước đo chất lượng dịch vụ theo ứng dụng.",
 "fault":"Cảnh báo, phân loại nguyên nhân, sự cố và tác động đến dịch vụ.",
 "ops":"Ticket, điều phối, kỹ thuật viên và KPI vận hành NOC.",
 "maintenance":"Kế hoạch, công việc và kết quả kiểm tra/bảo trì hạ tầng.",
 "customer":"Thuê bao, hồ sơ, tương tác và các chỉ báo khách hàng.",
 "product":"Gói cước, giá, ưu đãi, quyền lợi và danh mục sản phẩm.",
 "billing":"Hóa đơn, thanh toán, doanh thu, chi phí và ngân sách.",
 "service":"Đăng ký, kích hoạt, cấu hình và sử dụng dịch vụ.",
 "experience":"Khiếu nại, khảo sát, kiểm tra tốc độ và trải nghiệm khách hàng.",
 "energy":"Đo điện năng, nguồn điện, pin/máy phát và chi phí vận hành trạm.",
 "capacity":"Nhu cầu, dự báo, giới hạn tài nguyên và kế hoạch mở rộng.",
}

# Each table has a business grain and 10–40 typed columns. Foreign-key-like
# identifiers are shared across schemas; Hive/Trino do not enforce FKs.
SPECS = {
 "aaa": {
  "ftth_account_pppoe": "account_id:text,customer_id:text,username:text,groupname:text,loginlimit:int,connection_count:int,activation_date:date,status:text,plan_id:text,province_code:text,area_code:text,last_login_at:timestamp,created_at:timestamp,updated_at:timestamp",
  "authentication": "auth_id:text,account_id:text,session_id:text,event_time:timestamp,date_hour:text,hostname:text,nas_ip:text,result:text,reject_reason:text,request_count:int,accept_count:int,reject_count:int,latency_ms:real,retry_count:int,province_code:text",
  "accounting": "accounting_id:text,session_id:text,account_id:text,start_time:timestamp,stop_time:timestamp,date_hour:text,nas_ip:text,assigned_ip:text,upload_mb:real,download_mb:real,duration_s:int,terminate_cause:text,retry_count:int,dropped_packet:int,province_code:text",
  "access_event": "event_id:text,account_id:text,customer_id:text,province_code:text,event_time:timestamp,source_ip:text,event_type:text,result:text,risk_score:int,failed_attempts:int,device_id:text,rule_id:text,investigation_status:text"},
 "aam": {"kpi_aam_daily_tdxl": "kpi_id:text,kpi_code:text,location_level:text,location_code:text,area_code:text,area_name:text,province_code:text,province_name:text,date_hour:text,kpi_value:real,unit:text,threshold:real,breach_count:int,source_system:text,computed_at:timestamp",
         "kpi_aam_daily_tlgd": "kpi_id:text,kpi_code:text,location_level:text,location_code:text,area_code:text,province_code:text,date_hour:text,request_count:int,success_count:int,duration_ms:real,success_rate:real,source_system:text,computed_at:timestamp"},
 "acs": {"device_info": "device_id:text,ne_id:text,serial_number:text,customer_id:text,account_id:text,model:text,manufacturer:text,firmware_version:text,province_code:text,station_id:text,install_date:date,status:text,wan_type:text,last_contact_at:timestamp",
         "f_uptime": "uptime_id:text,device_id:text,ne_id:text,record_time:timestamp,date_hour:text,uptime_s:int,uptime_delta_s:int,wan_uptime_s:int,connect_status:text,ip_address:text,province_code:text,station_id:text,firmware_version:text,temperature_c:real",
         "g_uptime": "date_hour_o:text,record_time:text,duration:text,ne_id:text,created_date:text,uptime:text,uptime_delta:text,uptime_wanppp:text,uptime_wanppp_delta:text,date_hour:text",
         "f_wifi": "wifi_id:text,device_id:text,record_time:timestamp,date_hour:text,ssid:text,band:text,channel:int,standard:text,signal_dbm:real,noise_dbm:real,client_count:int,tx_rate_mbps:real,rx_rate_mbps:real,retry_rate:real,province_code:text"},
 "geo": {"location": "location_id:text,country_code:text,area_code:text,area_name:text,province_code:text,province_name:text,district_code:text,district_name:text,latitude:real,longitude:real,urban_flag:int,timezone:text,active_from:date"},
 "inventory": {"station": "station_id:text,location_id:text,province_code:text,station_name:text,station_type:text,latitude:real,longitude:real,commissioned_date:date,power_source:text,backhaul_type:text,status:text,vendor:text,site_capacity:int"},
 "ran": {"cell": "cell_id:text,station_id:text,province_code:text,object_id:text,technology:text,band:text,frequency_mhz:int,bandwidth_mhz:int,vendor:text,sector:int,azimuth_deg:int,launch_date:date,status:text,capacity_users:int,area_code:text"},
 "ran_kpi": {"cell_hourly": "cell_id:text,station_id:text,province_code:text,area_code:text,date_hour:text,utc_time_ms:bigint,availability_pct:real,dl_traffic_gb:real,ul_traffic_gb:real,dl_throughput_mbps:real,ul_throughput_mbps:real,rrc_attempt:int,rrc_success:int,ho_attempt:int,ho_success:int,prb_dl_util_pct:real,latency_ms:real,packet_loss_pct:real,active_users:int,kpi_quality_flag:text"},
 "transport": {"link_hourly": "link_id:text,from_station_id:text,to_station_id:text,province_code:text,date_hour:text,capacity_mbps:real,utilization_pct:real,latency_ms:real,packet_loss_pct:real,availability_pct:real,link_type:text,vendor:text,status:text"},
 "core": {"gateway_hourly": "gateway_id:text,province_code:text,area_code:text,date_hour:text,active_sessions:int,attach_attempt:int,attach_success:int,traffic_gb:real,cpu_pct:real,memory_pct:real,latency_ms:real,drop_count:int,status:text"},
 "qos": {"service_hourly": "service_id:text,plan_id:text,province_code:text,date_hour:text,technology:text,request_count:int,success_count:int,p95_latency_ms:real,jitter_ms:real,packet_loss_pct:real,availability_pct:real,breach_count:int,status:text"},
 "fault": {"alarm": "alarm_id:text,entity_type:text,entity_id:text,station_id:text,province_code:text,opened_at:timestamp,closed_at:timestamp,severity:text,alarm_code:text,root_cause:text,status:text,source_system:text,impact_users:int,ticket_id:text"},
 "ops": {"ticket": "ticket_id:text,alarm_id:text,station_id:text,province_code:text,opened_at:timestamp,acknowledged_at:timestamp,resolved_at:timestamp,priority:text,category:text,assigned_team:text,status:text,sla_deadline:timestamp,resolution_code:text,repeat_incident:int",
         "technician_visit": "visit_id:text,work_order_id:text,ticket_id:text,station_id:text,province_code:text,technician_id:text,scheduled_at:timestamp,arrived_at:timestamp,completed_at:timestamp,visit_type:text,result:text,travel_km:real,parts_used_count:int"},
 "maintenance": {"work_order": "work_order_id:text,station_id:text,province_code:text,ticket_id:text,scheduled_start:timestamp,scheduled_end:timestamp,actual_start:timestamp,actual_end:timestamp,work_type:text,crew_id:text,status:text,downtime_min:int,planned_flag:int"},
 "customer": {"subscriber": "customer_id:text,province_code:text,area_code:text,segment:text,join_date:date,status:text,household_size:int,preferred_channel:text,consent_analytics:int,risk_band:text,account_manager_id:text,service_address_zone:text"},
 "product": {"plan": "plan_id:text,service_id:text,plan_name:text,technology:text,monthly_fee_vnd:int,down_mbps:int,up_mbps:int,data_cap_gb:int,contract_months:int,active_from:date,active_to:date,status:text"},
 "billing": {"invoice": "invoice_id:text,customer_id:text,account_id:text,plan_id:text,billing_month:text,issued_date:date,due_date:date,base_amount_vnd:int,adjustment_vnd:int,tax_vnd:int,total_vnd:int,paid_vnd:int,status:text,province_code:text",
             "cost_center_daily": "cost_center_id:text,province_code:text,station_id:text,cost_date:date,energy_cost_vnd:int,maintenance_cost_vnd:int,transport_cost_vnd:int,depreciation_vnd:int,total_cost_vnd:int,budget_vnd:int,variance_vnd:int,currency:text,approval_status:text"},
 "service": {"subscription": "subscription_id:text,customer_id:text,account_id:text,plan_id:text,service_id:text,province_code:text,start_date:date,end_date:date,status:text,access_technology:text,station_id:text,last_change_at:timestamp,monthly_fee_vnd:int"},
 "experience": {"complaint": "complaint_id:text,customer_id:text,account_id:text,station_id:text,province_code:text,opened_at:timestamp,closed_at:timestamp,category:text,channel:text,severity:text,status:text,satisfaction_score:int,ticket_id:text,repeat_contact:int"},
 "energy": {"station_hourly": "station_id:text,province_code:text,date_hour:text,grid_kwh:real,generator_kwh:real,solar_kwh:real,battery_soc_pct:real,load_kw:real,ambient_temp_c:real,site_temp_c:real,power_outage_min:int,alarm_flag:int,cost_vnd:int"},
 "capacity": {"forecast_daily": "station_id:text,province_code:text,forecast_date:date,technology:text,forecast_traffic_gb:real,forecast_peak_users:int,available_capacity_mbps:real,projected_util_pct:real,model_version:text,generated_at:timestamp,confidence_low:real,confidence_high:real,risk_level:text"},
}
enrich_specs(SPECS)
extend_specs(SPECS)

def columns(spec): return [tuple(x.split(":")) for x in spec.split(",")]
def iso(t): return t.strftime("%Y-%m-%d %H:%M:%S")
def hour(t): return t.strftime("%Y-%m-%d-%H")
def num(x, n=2): return round(x, n)
def row(table, **values):
    schema,spec = next((schema,ts[table]) for schema,ts in SPECS.items() if table in ts)
    full=schema+"."+table
    for name,dtype in columns(spec):
        if name not in values and full in SOURCE_TABLES:
            values[name]=source_default(full,name,dtype,values)
    missing = [name for name, _ in columns(spec) if name not in values]
    if missing: raise ValueError(f"{table}: missing {missing}")
    return {name: values[name] for name, _ in columns(spec)}

def build():
 RNG.seed(20260921)
 rows = {f"{s}.{t}": [] for s, ts in SPECS.items() for t in ts}
 def add(s,t,**kw): rows[f"{s}.{t}"].append(row(t,**kw))
 sample_cells=[]
 with (SOURCE/"sample_data_100_rows(1).csv").open(encoding="utf-8-sig",newline="") as f:
  sample_cells=list(csv.DictReader(f))
 sample_kpis=[]
 with (SOURCE/"Query result 20-08-2026(1).csv").open(encoding="utf-8-sig",newline="") as f:
  sample_kpis=list(csv.DictReader(f))
 sample_by_object={r["object_id"]:r for r in sample_cells}
 stations=[]; cells=[]; customers=[]; accounts=[]; devices=[]
 for p,(area,prov,pname) in enumerate(AREAS):
  loc=f"LOC{p+1:03d}"; lat,lon=COORDS[prov]
  add("geo","location",location_id=loc,country_code="VNM",area_code=area,area_name=area,province_code=prov,province_name=pname,district_code=f"{prov}001",district_name=f"Quận/Huyện 1 {pname}",latitude=lat,longitude=lon,urban_flag=int(prov in ("HCM","NBH")),timezone="Asia/Ho_Chi_Minh",active_from="2024-01-01")
  for j in range(2):
   station=f"ST{p+1:02d}{j+1:02d}"; stations.append((station,prov,area))
   add("inventory","station",station_id=station,location_id=loc,province_code=prov,station_name=f"Trạm {prov}-{j+1}",station_type="macro" if j==0 else "rooftop",latitude=lat+j*.01,longitude=lon+j*.01,commissioned_date="2024-06-01",power_source="grid",backhaul_type="fiber",status="active",vendor="zte" if j==0 else "nokia",site_capacity=1200)
   for k in range(2):
    matching=[r for r in sample_cells if r["province_code"]==prov]
    obj=matching[(j*2+k)%len(matching)]["object_id"] if matching else f"SYNTH-{prov}-{j+1}-{k+1}"
    cell=f"CELL{p+1:02d}{j+1:02d}{k+1:02d}"; cells.append((cell,station,prov,area,obj))
    add("ran","cell",cell_id=cell,station_id=station,province_code=prov,object_id=obj,technology="5G",band="n78",frequency_mhz=3500,bandwidth_mhz=100,vendor="zte" if j==0 else "nokia",sector=k+1,azimuth_deg=k*120,launch_date="2025-01-01",status="active",capacity_users=600,area_code=area)
  for j in range(5):
   ix=p*5+j; customer=f"CUS{ix+1:04d}"; account=f"ACC{ix+1:04d}"; device=f"CPE{ix+1:04d}"; plan=f"PLAN{j%3+1:02d}"; station=stations[p*2+j%2][0]
   customers.append((customer,prov,area,account,device,plan,station)); accounts.append(account); devices.append((device,station,prov,account))
   add("customer","subscriber",customer_id=customer,province_code=prov,area_code=area,segment="household" if j<4 else "business",join_date="2025-05-01",status="active",household_size=2+j,preferred_channel="app",consent_analytics=1,risk_band="low",account_manager_id="TEAM01",service_address_zone=f"{prov}-ZONE-{j+1}")
   add("aaa","ftth_account_pppoe",account_id=account,customer_id=customer,username=f"demo_{account.lower()}",groupname="ftth",loginlimit=1,connection_count=1,activation_date="2025-05-01",status="active",plan_id=plan,province_code=prov,area_code=area,last_login_at=iso(HOURS[-1]),created_at="2025-05-01 09:00:00",updated_at="2026-08-18 00:00:00")
   add("acs","device_info",device_id=device,ne_id=f"NE{ix+1:04d}",serial_number=f"SYNTH{ix+1:08d}",customer_id=customer,account_id=account,model="F680",manufacturer="ZTE",firmware_version="1.2.1",province_code=prov,station_id=station,install_date="2025-05-02",status="active",wan_type="PPPoE",last_contact_at=iso(HOURS[-1]))
   add("service","subscription",subscription_id=f"SUB{ix+1:04d}",customer_id=customer,account_id=account,plan_id=plan,service_id="SVC-FTTH",province_code=prov,start_date="2025-05-01",end_date="",status="active",access_technology="FTTH",station_id=station,last_change_at="2026-01-01 00:00:00",monthly_fee_vnd=[220000,300000,450000][j%3])
 for j,fee in enumerate((220000,300000,450000),1):
  add("product","plan",plan_id=f"PLAN{j:02d}",service_id="SVC-FTTH",plan_name=f"FTTH {100*j} Mbps",technology="FTTH",monthly_fee_vnd=fee,down_mbps=100*j,up_mbps=50*j,data_cap_gb=0,contract_months=12,active_from="2025-01-01",active_to=None,status="active")
 for i,(cell,station,prov,area,obj) in enumerate(cells):
  sample=sample_by_object.get(obj,{})
  def sample_float(key,default):
   try: return float(sample[key])
   except (ValueError,KeyError): return default
  baseline=max(0.1,min(12,sample_float("nr_ps_traffic_total_gb",2)))
  for h,t in enumerate(HOURS):
   busy=1.55 if 18<=t.hour<=22 else (.55 if t.hour<7 else 1.0)
   incident=(i==0 and 25<=h<=28) or (i==7 and 45<=h<=47)
   dl=num(baseline*busy*RNG.uniform(.65,1.3)*(0.12 if incident else 1))
   ul=num(dl*RNG.uniform(.22,.38)); attempts=RNG.randint(70,220)
   success=attempts-RNG.randint(1,6)-(RNG.randint(15,35) if incident else 0)
   ho=RNG.randint(20,90); ho_success=ho-RNG.randint(0,4)-(10 if incident else 0)
   avail=98.0 if incident else num(RNG.uniform(99.2,100))
   add("ran_kpi","cell_hourly",cell_id=cell,station_id=station,province_code=prov,area_code=area,date_hour=hour(t),utc_time_ms=int((t-dt.timedelta(hours=7)).replace(tzinfo=dt.timezone.utc).timestamp()*1000),availability_pct=avail,dl_traffic_gb=dl,ul_traffic_gb=ul,dl_throughput_mbps=num(dl*18),ul_throughput_mbps=num(ul*12),rrc_attempt=attempts,rrc_success=success,ho_attempt=ho,ho_success=ho_success,prb_dl_util_pct=num(min(99,35*busy+(20 if incident else 0)+RNG.uniform(-8,8))),latency_ms=num(RNG.uniform(12,30)+(65 if incident else 0)),packet_loss_pct=num(RNG.uniform(.01,.2)+(3 if incident else 0)),active_users=RNG.randint(30,160),kpi_quality_flag="degraded" if incident else "normal")
 last_uptime_by_device={}
 for h,t in enumerate(HOURS):
  dh=hour(t)
  for n,(station,prov,area) in enumerate(stations):
   broken=(n==0 and 25<=h<=28) or (n==3 and 45<=h<=47)
   load=num(RNG.uniform(3,9)*(1.4 if 18<=t.hour<=22 else 1))
   outage=30 if broken else 0; energy=num(load*.85); energy_cost=round(energy*2300)
   add("energy","station_hourly",station_id=station,province_code=prov,date_hour=dh,grid_kwh=energy,generator_kwh=num(load*.15) if broken else 0,solar_kwh=0,battery_soc_pct=55 if broken else 95,load_kw=load,ambient_temp_c=num(RNG.uniform(25,35)),site_temp_c=num(RNG.uniform(29,39)),power_outage_min=outage,alarm_flag=int(broken),cost_vnd=energy_cost)
   add("transport","link_hourly",link_id=f"LINK{n+1:02d}",from_station_id=station,to_station_id=stations[(n+1)%len(stations)][0],province_code=prov,date_hour=dh,capacity_mbps=1000,utilization_pct=num(RNG.uniform(25,65)),latency_ms=num(RNG.uniform(2,10)+(30 if broken else 0)),packet_loss_pct=2.5 if broken else .05,availability_pct=95 if broken else 99.9,link_type="fiber",vendor="zte",status="degraded" if broken else "up")
   if h==24:
    peak=round(RNG.uniform(8,25),2)
    add("capacity","forecast_daily",station_id=station,province_code=prov,forecast_date="2026-08-21",technology="5G",forecast_traffic_gb=peak,forecast_peak_users=RNG.randint(150,400),available_capacity_mbps=1000,projected_util_pct=num(peak*2),model_version="synthetic-v1",generated_at=iso(t),confidence_low=num(peak*.8),confidence_high=num(peak*1.2),risk_level="medium" if peak>18 else "low")
   if h==48:
    maint=10000 if broken else 2000; total=energy_cost+maint+5000+12000
    add("billing","cost_center_daily",cost_center_id=f"CC{n+1:02d}",province_code=prov,station_id=station,cost_date="2026-08-20",energy_cost_vnd=energy_cost,maintenance_cost_vnd=maint,transport_cost_vnd=5000,depreciation_vnd=12000,total_cost_vnd=total,budget_vnd=35000,variance_vnd=total-35000,currency="VND",approval_status="approved")
  for p,(area,prov,_) in enumerate(AREAS):
   attempts=RNG.randint(300,700); success=attempts-RNG.randint(2,15)
   add("core","gateway_hourly",gateway_id=f"GW{p+1:02d}",province_code=prov,area_code=area,date_hour=dh,active_sessions=RNG.randint(150,350),attach_attempt=attempts,attach_success=success,traffic_gb=num(RNG.uniform(20,70)),cpu_pct=num(RNG.uniform(20,70)),memory_pct=num(RNG.uniform(35,75)),latency_ms=num(RNG.uniform(5,25)),drop_count=attempts-success,status="up")
   add("qos","service_hourly",service_id="SVC-FTTH",plan_id="PLAN01",province_code=prov,date_hour=dh,technology="FTTH",request_count=attempts,success_count=success,p95_latency_ms=num(RNG.uniform(12,40)),jitter_ms=num(RNG.uniform(1,8)),packet_loss_pct=num(RNG.uniform(.01,.2)),availability_pct=99.9,breach_count=int(success/attempts<.97),status="normal")
   add("aam","kpi_aam_daily_tlgd",kpi_id=f"TLGD{p:02d}{h:03d}",kpi_code="request_success_rate",location_level="province",location_code=prov,area_code=area,province_code=prov,date_hour=dh,request_count=attempts,success_count=success,duration_ms=num(attempts*RNG.uniform(8,20)),success_rate=num(success/attempts*100,4),source_system="synthetic_core",computed_at=iso(t+dt.timedelta(hours=1)))
  for j,(customer,prov,area,account,device,plan,station) in enumerate(customers):
   if j%3 != h%3 and not (j==0 and h in (25,26)): continue
   session=f"SES{j:03d}{h:03d}"; auth=f"AUTH{j:03d}{h:03d}"; ok=(j==0 and h in (24,25,26)) is False
   add("aaa","authentication",auth_id=auth,account_id=account,session_id=session,event_time=iso(t),date_hour=dh,hostname=f"radius-{area.lower()}",nas_ip=f"10.{j//255}.{j%255}.1",result="accept" if ok else "reject",reject_reason="" if ok else "invalid_credentials",request_count=1,accept_count=int(ok),reject_count=int(not ok),latency_ms=num(RNG.uniform(5,35)),retry_count=int(not ok),province_code=prov)
   if ok:
    duration=RNG.randint(1200,3500)
    add("aaa","accounting",accounting_id=f"ACCT{j:03d}{h:03d}",session_id=session,account_id=account,start_time=iso(t),stop_time=iso(t+dt.timedelta(seconds=duration)),date_hour=dh,nas_ip=f"10.{j//255}.{j%255}.1",assigned_ip=f"100.64.{j//255}.{j%255}",upload_mb=num(RNG.uniform(20,500)),download_mb=num(RNG.uniform(100,3000)),duration_s=duration,terminate_cause="user_request",retry_count=0,dropped_packet=RNG.randint(0,3),province_code=prov)
   uptime=86400+h*3600
   prior_uptime=last_uptime_by_device.get(device)
   uptime_delta=uptime-prior_uptime if prior_uptime is not None else 3600
   last_uptime_by_device[device]=uptime
   add("acs","f_uptime",uptime_id=f"UP{j:03d}{h:03d}",device_id=device,ne_id=f"NE{j+1:04d}",record_time=iso(t),date_hour=dh,uptime_s=uptime,uptime_delta_s=uptime_delta,wan_uptime_s=uptime-100,connect_status="connected",ip_address=f"100.64.{j//255}.{j%255}",province_code=prov,station_id=station,firmware_version="1.2.1",temperature_c=num(RNG.uniform(35,55)))
   add("acs","f_wifi",wifi_id=f"WIFI{j:03d}{h:03d}",device_id=device,record_time=iso(t),date_hour=dh,ssid=f"SYNTH-{j:03d}",band="5GHz",channel=36+(j%4)*4,standard="802.11ac",signal_dbm=num(RNG.uniform(-72,-45)),noise_dbm=-90,client_count=RNG.randint(1,9),tx_rate_mbps=num(RNG.uniform(80,400)),rx_rate_mbps=num(RNG.uniform(80,400)),retry_rate=num(RNG.uniform(.01,.12)),province_code=prov,ip_address=f"100.64.{j//255}.{j%255}")
 for h in (24,25,26):
  customer,prov,area,account,device,plan,station=customers[0]
  add("aaa","access_event",event_id=f"SEC{h:03d}",account_id=account,customer_id=customer,province_code=prov,event_time=iso(HOURS[h]),source_ip="198.51.100.12",event_type="login",result="blocked",risk_score=85,failed_attempts=h-23,device_id=device,rule_id="RULE-LOGIN-01",investigation_status="open")
 for j,(customer,prov,area,account,device,plan,station) in enumerate(customers):
  fee=[220000,300000,450000][j%5%3]; tax=round(fee*.1)
  add("billing","invoice",invoice_id=f"INV{j+1:04d}",customer_id=customer,account_id=account,plan_id=plan,billing_month="2026-08",issued_date="2026-08-20",due_date="2026-09-05",base_amount_vnd=fee,adjustment_vnd=0,tax_vnd=tax,total_vnd=fee+tax,paid_vnd=fee+tax if j%5 else 0,status="paid" if j%5 else "unpaid",province_code=prov)
 for i,(cell,station,prov,area,obj) in enumerate(cells):
  if i not in (0,7): continue
  h=25 if i==0 else 45; opened=HOURS[h]; closed=HOURS[h+4]
  alarm=f"ALM{i:03d}"; ticket=f"TKT{i:03d}"; wo=f"WO{i:03d}"
  add("fault","alarm",alarm_id=alarm,entity_type="cell",entity_id=cell,station_id=station,province_code=prov,opened_at=iso(opened),closed_at=iso(closed),severity="major",alarm_code="CELL_DEGRADED",root_cause="power" if i==0 else "transport",status="closed",source_system="ran_monitor",impact_users=130,ticket_id=ticket)
  add("ops","ticket",ticket_id=ticket,alarm_id=alarm,station_id=station,province_code=prov,opened_at=iso(opened),acknowledged_at=iso(opened+dt.timedelta(minutes=10)),resolved_at=iso(closed),priority="P1",category="network",assigned_team="NOC",status="resolved",sla_deadline=iso(opened+dt.timedelta(hours=6)),resolution_code="repaired",repeat_incident=0)
  add("maintenance","work_order",work_order_id=wo,station_id=station,province_code=prov,ticket_id=ticket,scheduled_start=iso(opened+dt.timedelta(minutes=30)),scheduled_end=iso(closed),actual_start=iso(opened+dt.timedelta(minutes=40)),actual_end=iso(closed),work_type="repair",crew_id="CREW01",status="completed",downtime_min=180,planned_flag=0)
  add("ops","technician_visit",visit_id=f"VIS{i:03d}",work_order_id=wo,ticket_id=ticket,station_id=station,province_code=prov,technician_id=f"TECH{i+1:03d}",scheduled_at=iso(opened+dt.timedelta(minutes=30)),arrived_at=iso(opened+dt.timedelta(minutes=40)),completed_at=iso(closed),visit_type="repair",result="fixed",travel_km=12.5,parts_used_count=1)
  customer,_,_,account,_,_,_=next(c for c in customers if c[6]==station)
  add("experience","complaint",complaint_id=f"COMP{i:03d}",customer_id=customer,account_id=account,station_id=station,province_code=prov,opened_at=iso(opened+dt.timedelta(hours=1)),closed_at=iso(closed),category="slow_internet",channel="app",severity="medium",status="closed",satisfaction_score=3,ticket_id=ticket if i==0 else None,repeat_contact=0)
 for uptime in rows["acs.f_uptime"]:
  add("acs","g_uptime",date_hour_o=uptime["date_hour"],record_time=uptime["record_time"],duration=str(uptime["duration"]),ne_id=uptime["ne_id"],created_date=uptime["record_time"],uptime=str(uptime["uptime_s"]),uptime_delta=str(uptime["uptime_delta_s"]),uptime_wanppp=str(uptime["wan_uptime_s"]),uptime_wanppp_delta=str(uptime["uptime_wanppp_delta"]),date_hour=uptime["date_hour"])
 # Preserve the supplied province KPI values as a separate dated snapshot.
 for i,r in enumerate(sample_kpis):
  raw=r["kpi_value"].strip(); value=float(raw) if raw and raw.lower()!="null" else None
  add("aam","kpi_aam_daily_tdxl",kpi_id=f"SRC{i+1:03d}",kpi_code=r["kpi_code"],location_level=r["location_level"],location_code=r["province_code"] if r["location_level"]=="province" else (r["area_name"] if r["location_level"]=="area" else "VNM"),area_code=r["area_name"] if r["area_name"] not in ("","null") else "",area_name=r["area_name"] if r["area_name"] not in ("","null") else "",province_code=r["province_code"] if r["province_code"] not in ("","null") else "",province_name=r["province_name"] if r["province_name"] not in ("","null") else "",date_hour=r["date_hour"],kpi_value=value,unit="cell_count",threshold=None,breach_count=0,source_system="provided_sample",computed_at="2026-08-20 01:00:00")
 add("geo","country",country_code="VNM",country_name="Việt Nam",iso2="VN",region="Southeast Asia",currency="VND",timezone="Asia/Ho_Chi_Minh",active_from="2024-01-01",active_to=None,status="active",source_system="synthetic_geo")
 for n,area in enumerate(dict.fromkeys(a for a,_,_ in AREAS),1):
  add("geo","area",area_code=area,country_code="VNM",area_name=area,sort_order=n,province_count=sum(a==area for a,_,_ in AREAS),timezone="Asia/Ho_Chi_Minh",active_from="2024-01-01",active_to=None,status="active",source_system="synthetic_geo")
 for p,(area,prov,pname) in enumerate(AREAS):
  lat,lon=COORDS[prov]; district=f"{prov}001"; ward=district+"W01"
  add("geo","province",province_code=prov,area_code=area,country_code="VNM",province_name=pname,urban_flag=int(prov in ("HCM","NBH")),latitude=lat,longitude=lon,district_count=1,active_from="2024-01-01",status="active",source_system="synthetic_geo")
  add("geo","district",district_code=district,province_code=prov,district_name=f"Quận/Huyện 1 {pname}",administrative_type="district",latitude=lat,longitude=lon,ward_count=1,active_from="2024-01-01",status="active",source_system="synthetic_geo")
  add("geo","ward",ward_code=ward,district_code=district,ward_name=f"Phường/Xã 1 {pname}",administrative_type="ward",latitude=lat,longitude=lon,population_est=10000+p*2000,active_from="2024-01-01",status="active",source_system="synthetic_geo")
  add("geo","village",village_code=ward+"V01",ward_code=ward,village_name=f"Thôn/Tổ 1 {pname}",latitude=lat,longitude=lon,population_est=1000+p*200,active_from="2024-01-01",status="active",source_system="synthetic_geo",village_type="residential")
 # Supplementary entities and subject streams use one explicit domain anchor.
 for schema,names in TABLE_NAMES.items():
  for table in names.split():
   if table not in SPECS[schema]: continue
   if schema=="geo" and table in GEO_HIERARCHY: continue
   spec=columns(SPECS[schema][table])
   for p,(area,prov,pname) in enumerate(AREAS):
    anchor_key=anchor_for(schema,table)[1]
    if anchor_key in ("alarm_id","ticket_id","work_order_id","complaint_id"):
     hours=(27,) if p==0 else ((45,) if p==1 else ())
    elif schema=="fault" and table_kind(table,schema)=="event":
     hours=(27,) if p==0 else ((45,) if p==1 else ())
    elif schema=="geo" and table=="geo_boundary_history": hours=(0,)
    elif schema=="billing" and table in ("payment","payment_attempt"): hours=range(0,45,9)
    elif schema=="maintenance" and "inspection" in table: hours=(9,33,57)
    elif "_hourly" in table: hours=range(72)
    elif "_daily" in table: hours=(0,24,48)
    elif "_monthly" in table: hours=(0,)
    elif is_stream(table,schema): hours=range(0,72,9)
    else: hours=(0,)
    for sample_idx,h in enumerate(hours):
     t=HOURS[h]
     customer_index=p%5
     if schema=="billing" and table in ("payment","payment_attempt"): customer_index=sample_idx%5
     if p==0 and h==27: customer_index=0
     if p==1 and h==45: customer_index=1
     customer,_,_,account,device,plan,station=customers[p*5+customer_index]
     cell=next(c[0] for c in cells if c[1]==station)
     incident=(station=="ST0101" and h==27) or (station=="ST0202" and h==45)
     value=num(RNG.uniform(15,85)*(1.45 if incident else 1))
     anchor_value={"account_id":account,"location_id":f"LOC{p+1:03d}","device_id":device,"station_id":station,"cell_id":cell,"plan_id":plan,"customer_id":customer,"invoice_id":f"INV{p*5+customer_index+1:04d}","subscription_id":f"SUB{p*5+customer_index+1:04d}","alarm_id":"ALM000" if p==0 else "ALM007","ticket_id":"TKT000" if p==0 else "TKT007","work_order_id":"WO000" if p==0 else "WO007","complaint_id":"COMP000" if p==0 else "COMP007"}[anchor_key]
     kind=table_kind(table,schema)
     values={f"{table}_id":f"{schema.upper()}-{table.upper()}-{p:02d}-{h:02d}",anchor_key:anchor_value,"province_code":prov,"area_code":area,"status":"degraded" if incident else "active","source_system":f"synthetic_{schema}"}
     if kind=="entity": values.update(code=f"{table.upper()}-{p+1:02d}",name=table.replace("_"," ").title(),category=schema,effective_from="2025-01-01",effective_to=None)
     elif kind=="observation": values.update(date_hour=hour(t),observed_at=iso(t),metric_value=value,metric_unit="count" if schema in ("aaa","fault","ops","customer") else "index",quality_flag="degraded" if incident else "valid")
     else: values.update(event_time=iso(t),event_code=table.upper(),severity="major" if incident else "info",outcome="failed" if incident else "success",duration_s=3600 if incident else 60)
     if schema=="aaa":
      req=RNG.randint(50,250); reject=RNG.randint(1,5)+(20 if incident else 0)
      values.update(request_count=req,success_count=req-reject,reject_count=reject,latency_ms=num(RNG.uniform(5,35)+(50 if incident else 0)))
     elif schema=="aam": values.update(sample_count=24,breach_count=int(incident),baseline_value=num(value*.9),change_pct=num(100/9))
     elif schema=="acs": values.update(temperature_c=num(RNG.uniform(35,55)),uptime_s=86400+h*3600,retry_count=RNG.randint(0,5),signal_dbm=num(RNG.uniform(-75,-45)))
     elif schema=="geo": values.update(latitude=COORDS[prov][0],longitude=COORDS[prov][1],population_est=100000+p*25000,coverage_pct=num(RNG.uniform(85,99)))
     elif schema=="inventory": values.update(asset_count=RNG.randint(10,50),installed_count=RNG.randint(5,10),age_days=400+h//24,unit_cost_vnd=RNG.randint(1,20)*1000000)
     elif schema=="ran": values.update(frequency_mhz=3500,bandwidth_mhz=100,tx_power_dbm=num(RNG.uniform(20,45)),sector_count=2)
     elif schema=="ran_kpi":
      attempts=RNG.randint(80,300); values.update(attempt_count=attempts,success_count=attempts-RNG.randint(1,8)-(20 if incident else 0),traffic_gb=num(RNG.uniform(.5,8)),availability_pct=98.0 if incident else 99.9)
     elif schema=="transport": values.update(capacity_mbps=1000,utilization_pct=num(RNG.uniform(25,75)),latency_ms=num(RNG.uniform(2,15)+(30 if incident else 0)),packet_loss_pct=2.5 if incident else .05)
     elif schema=="core":
      req=RNG.randint(200,600); values.update(session_count=RNG.randint(100,300),request_count=req,success_count=req-RNG.randint(1,12),cpu_pct=num(RNG.uniform(20,70)))
     elif schema=="qos":
      req=RNG.randint(100,400); values.update(request_count=req,success_count=req-RNG.randint(1,10),p95_latency_ms=num(RNG.uniform(15,45)+(50 if incident else 0)),breach_count=int(incident))
     elif schema=="fault": values.update(impact_users=130 if incident else 0,duration_min=60 if incident else 0,repeat_count=int(incident),priority_score=90 if incident else 20)
     elif schema=="ops": values.update(sla_minutes=360,response_minutes=10 if incident else 5,resolution_minutes=240 if incident else 30,reopen_count=0)
     elif schema=="maintenance": values.update(planned_duration_min=180,actual_duration_min=200 if incident else 160,part_count=1,labor_cost_vnd=200000)
     elif schema=="customer": values.update(tenure_months=15,interaction_count=RNG.randint(0,5),satisfaction_score=3 if incident else 5,churn_score=num(RNG.uniform(.05,.2)+(0.3 if incident else 0)))
     elif schema=="product":
      tier=customer_index%3+1
      values.update(monthly_fee_vnd=[220000,300000,450000][tier-1],down_mbps=100*tier,up_mbps=50*tier,eligible_count=RNG.randint(50,200))
     elif schema=="billing":
      amount=[220000,300000,450000][customer_index%3]; tax=amount//10
      if anchor_key=="invoice_id":
       paid=amount+tax if customer_index%5 else 0
       if kind=="event" and "payment" in table and not paid:
        values["outcome"]="failed"; values["status"]="rejected"
      else: paid=0
      values.update(amount_vnd=amount,tax_vnd=tax,paid_vnd=paid,outstanding_vnd=amount+tax-paid)
     elif schema=="service":
      req=RNG.randint(50,300); values.update(request_count=req,success_count=req-RNG.randint(1,5),active_count=RNG.randint(20,100),latency_ms=num(RNG.uniform(5,35)))
     elif schema=="experience":
      responses=RNG.randint(10,50); values.update(response_count=responses,positive_count=responses-RNG.randint(1,5),score=3 if incident else 4.5,repeat_count=int(incident))
     elif schema=="energy":
      grid=num(RNG.uniform(3,8)); generator=2 if incident else 0
      values.update(grid_kwh=grid,generator_kwh=generator,load_kw=num(grid+generator),cost_vnd=round(grid*2300+generator*4000))
     elif schema=="capacity":
      demand=num(RNG.uniform(300,800)); available=1000
      values.update(demand_mbps=demand,available_mbps=available,utilization_pct=num(100*demand/available),forecast_error_pct=num(RNG.uniform(-8,8)))
     if schema=="geo" and table=="location_alias":
      normalized="".join(ch for ch in unicodedata.normalize("NFKD",pname) if not unicodedata.combining(ch)).replace("Đ","D").replace("đ","d")
      values.update(alias_name=pname,alias_type="official_name",language_code="vi",normalized_name=normalized.lower())
     if schema=="geo" and table=="geo_boundary_history":
      values.update(boundary_version="2026-01",change_reason="initial_snapshot",area_km2=1000+p*100,effective_date="2026-01-01")
     if schema=="geo" and table in ("district_population_daily","province_population_daily"):
      population=100000+p*25000+h//24*50
      values.update(population_count=population,household_count=population//4,density_per_km2=num(population/(1000+p*100)),metric_value=population,metric_unit="persons")
     if schema=="maintenance" and table=="antenna_inspection":
      values.update(tilt_deg=num(4+p*.3),azimuth_deg=(p%3)*120,vswr=num(RNG.uniform(1.1,1.6)),connector_condition="good",inspection_result="pass",status="completed")
     if schema=="maintenance" and table=="battery_inspection":
      values.update(voltage_v=num(RNG.uniform(47,54)),capacity_pct=num(RNG.uniform(80,98)),terminal_condition="good",inspection_result="pass",status="completed")
     if schema=="maintenance" and table=="generator_inspection":
      values.update(fuel_level_pct=num(RNG.uniform(55,95)),oil_pressure_kpa=num(RNG.uniform(250,400)),start_test_result="passed",inspection_result="pass",status="completed")
     if schema=="maintenance" and table=="fiber_inspection":
      values.update(optical_loss_db=num(RNG.uniform(.1,1.2)),connector_cleanliness="clean",inspection_result="pass",status="completed")
     current={name:values[name] for name,_ in spec}
     rows[f"{schema}.{table}"].append(current)
     if kind=="entity" and p < 2:
      historical=current.copy()
      historical[f"{table}_id"] += "-OLD"
      historical["effective_from"]="2024-01-01"
      historical["effective_to"]="2024-12-31"
      rows[f"{schema}.{table}"].append(historical)
 return rows

def write(rows):
 OUT.mkdir(exist_ok=True)
 db=sqlite3.connect(OUT/"telecom.sqlite")
 ddl=[]; catalog=[]; counts={}
 model=relationship_metadata(SPECS)
 source_catalog=read_source_catalog()
 source_tables={item["table"]:item for item in source_catalog["tables"]}
 keys={x["name"]:x["primary_key"] for x in model["tables"]}
 links={name:[] for name in keys}
 for link in model["relationships"]: links[link["from_table"]].append(link)
 # A previous snapshot may contain tables that were removed from the model.
 for (old_table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
  if old_table not in {f"{s}__{t}" for s, items in SPECS.items() for t in items}:
   db.execute(f'DROP TABLE "{old_table}"')
 old_catalog_path=OUT/"catalog.json"
 if old_catalog_path.exists():
  for item in json.loads(old_catalog_path.read_text(encoding="utf-8")):
   old_name=item["schema"]+"."+item["table"]
   if old_name not in keys:
    (OUT/item["csv"]).unlink(missing_ok=True)
    db.execute(f'DROP TABLE IF EXISTS "{item["sqlite_table"]}"')
 type_map={"text":"VARCHAR","int":"INTEGER","bigint":"BIGINT","real":"DOUBLE","date":"DATE","timestamp":"TIMESTAMP"}
 for schema,tables in SPECS.items():
  folder=OUT/schema; folder.mkdir(exist_ok=True)
  for table,spec in tables.items():
   name=f"{schema}.{table}"; cols=columns(spec); values=rows[name]
   assert 10<=len(cols)<=40,(name,len(cols))
   with (folder/f"{table}.csv").open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fieldnames=[c for c,_ in cols]); w.writeheader(); w.writerows(values)
   fk_comments="\n".join(f"-- FK {link['from_column']} -> {link['to_table']}.{link['to_column']} ({link['basis']})" for link in links[name])
   ddl.append(f"CREATE SCHEMA IF NOT EXISTS {schema};\n-- Logical PK: {', '.join(keys[name])}\n"+(fk_comments+"\n" if fk_comments else "")+f"CREATE TABLE IF NOT EXISTS {name} (\n  "+",\n  ".join(f"{c} {type_map[t]}" for c,t in cols)+"\n);\n")
   sqlname=f"{schema}__{table}"
   db.execute(f'DROP TABLE IF EXISTS "{sqlname}"')
   pk_sql='PRIMARY KEY ('+','.join(f'"{c}"' for c in keys[name])+')'
   unique_sql=[]
   if name=="aaa.authentication": unique_sql.append('UNIQUE ("session_id")')
   if name=="geo.location": unique_sql.append('UNIQUE ("province_code")')
   if name=="acs.device_info": unique_sql.append('UNIQUE ("ne_id")')
   db.execute(f'CREATE TABLE "{sqlname}" ('+", ".join([*(f'"{c}" {"INTEGER" if t in ("int","bigint") else "REAL" if t=="real" else "TEXT"}' for c,t in cols),pk_sql,*unique_sql])+")")
   db.executemany(f'INSERT INTO "{sqlname}" VALUES ('+",".join("?" for _ in cols)+")",[[v[c] for c,_ in cols] for v in values])
   extension=table in TABLE_NAMES[schema].split()
   grain=("one " + table + " code") if schema=="geo" and table in GEO_HIERARCHY else ("one subject observation or event per anchor and time" if is_stream(table,schema) else "one subject entity per anchor")
   origin="synthetic_extension" if extension else ("provided_sample" if name=="aam.kpi_aam_daily_tdxl" else "synthetic_core")
   if name in source_tables:
    description=source_tables[name]["description"]
   elif extension:
    role={"entity":"danh mục", "observation":"chuỗi chỉ số", "event":"sự kiện"}[table_kind(table,schema)]
    if schema=="geo" and table in GEO_HIERARCHY: role="cấp địa giới"
    link=links[name][0] if links[name] else None
    description=f"Bảng {role} {table.replace('_',' ')} của miền {schema}. " + (f"Liên kết đến {link['to_table']} bằng {link['from_column']}. " if link else "") + "Cấu trúc và dữ liệu là giả định tổng hợp để thử truy vấn."
   else:
    description=f"Bảng lõi tổng hợp {name}, dùng để thử truy vấn liên miền. Cấu trúc và dữ liệu là giả định thiết kế."
   source_names={col["name"] for col in source_tables[name]["columns"]} if name in source_tables else set()
   catalog.append({"schema":schema,"table":table,"description":description,"sqlite_table":sqlname,"grain":GRAINS.get(name,grain if extension else "one row per entity or event"),"primary_key":keys[name],"foreign_keys":[{"column":link["from_column"],"references":link["to_table"]+"."+link["to_column"],"basis":link["basis"]} for link in links[name]],"columns":[{"name":c,"type":t,"source_description":next((col["description"] for col in source_tables[name]["columns"] if col["name"]==c),None) if name in source_tables else None} for c,t in cols],"source_column_count":len(source_names) if source_names else None,"exact_source_columns":sorted(source_names.intersection(c for c,_ in cols)) if source_names else None,"row_count":len(values),"csv":f"{schema}/{table}.csv","origin":origin})
   counts[name]=len(values)
 db.commit(); db.close()
 (OUT/"schema_trino.sql").write_text("\n".join(ddl),encoding="utf-8")
 (OUT/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 (OUT/"source_metadata.json").write_text(json.dumps(source_catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 source_schemas={item["schema"]:item for item in source_catalog["schemas"]}
 schema_catalog=[]
 for schema in SPECS:
  items=[item for item in catalog if item["schema"]==schema]
  schema_catalog.append({"schema":schema,"description":SCHEMA_DESCRIPTIONS[schema],"source_description":source_schemas[schema]["description"] if schema in source_schemas else None,"origin":"source_named_with_synthetic_extensions" if schema in source_schemas else "synthetic_assumption","table_count":len(items),"row_count":sum(item["row_count"] for item in items)})
 (OUT/"schema_catalog.json").write_text(json.dumps(schema_catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 with (OUT/"source_mapping.csv").open("w",encoding="utf-8",newline="") as f:
  writer=csv.writer(f); writer.writerow(["table","source_column_count","generated_column_count","exact_name_matches","source_only_columns","generated_only_columns"])
  for item in catalog:
   name=item["schema"]+"."+item["table"]
   if name not in source_tables: continue
   original={col["name"] for col in source_tables[name]["columns"]}
   generated={col["name"] for col in item["columns"]}
   writer.writerow([name,len(original),len(generated),";".join(sorted(original&generated)),";".join(sorted(original-generated)),";".join(sorted(generated-original))])
 (OUT/"schema_relationships.json").write_text(json.dumps(model,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 with (OUT/"relationships_review.csv").open("w",encoding="utf-8",newline="") as f:
  writer=csv.writer(f); writer.writerow(["from_table","primary_key","from_column","to_table","to_column","cardinality","basis"])
  for link in model["relationships"]:
   writer.writerow([link["from_table"],"+".join(keys[link["from_table"]]),link["from_column"],link["to_table"],link["to_column"],link["cardinality"],link["basis"]])
 (OUT/"counts.json").write_text(json.dumps(counts,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 with (OUT/"schema_summary.csv").open("w",encoding="utf-8",newline="") as f:
  writer=csv.writer(f); writer.writerow(["schema","table_count","row_count","relationship_count"])
  for schema in SPECS:
   tables=[item for item in catalog if item["schema"]==schema]
   writer.writerow([schema,len(tables),sum(item["row_count"] for item in tables),sum(link["from_table"].startswith(schema+".") for link in model["relationships"])])
 lines=["# Đối chiếu nguồn và kết quả rà soát", "", "Bộ dữ liệu nguồn gồm Markdown mô tả 3 schema, 8 bảng và 179 cột; CSV KPI cell có 50 dòng × 299 cột; CSV KPI địa bàn có 40 dòng × 8 cột. `query.md` rỗng. Mô tả gốc có nhãn `[AI Gen]`, nên cần xác nhận với catalog công ty trước khi coi là định nghĩa chính thức.", "", "**Điểm không nhất quán trong nguồn:** mô tả `acs.f_wifi` nói chưa xác định được cột nhưng cùng file lại liệt kê 50 cột. Danh sách 8 cột của `aam.kpi_aam_daily_tdxl` trong Markdown cũng khác 8 cột của CSV KPI địa bàn. Bảng thử giữ cột cần thiết từ cả hai nguồn và chuẩn hóa chuỗi `null`/ô trống; CSV gốc không bị sửa.", "", "## Tám bảng trong tài liệu gốc", ""]
 for source_item in source_catalog["tables"]:
  name=source_item["table"]; generated=next(item for item in catalog if item["schema"]+"."+item["table"]==name)
  original={col["name"] for col in source_item["columns"]}; current={col["name"] for col in generated["columns"]}
  lines.extend([f"### `{name}`", "", source_item["description"] or "Tài liệu gốc không có mô tả.", "", f"Cột nguồn: **{len(original)}**; cột trong bảng thử: **{len(current)}**; tên cột giữ nguyên: **{len(original&current)}**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.", ""])
 lines.extend(["## Bảng được bỏ sau rà soát", "", "Các bảng sau từng có trong bản tổng hợp, nhưng trùng vai trò với bảng được giữ hoặc không đủ căn cứ từ mẫu. Mỗi schema vẫn có đúng 20 bảng.", "", "| Schema | Bảng bỏ | Lý do |", "| --- | --- | --- |"])
 for schema,items in PRUNED_TABLES.items():
  for table,reason in items.items(): lines.append(f"| `{schema}` | `{table}` | {reason} |")
 lines.extend(["", "## Cách kiểm chứng", "", "- `generated/source_metadata.json` lưu nguyên mô tả của 3 schema, 8 bảng và 179 cột từ Markdown gốc.", "- `generated/source_mapping.csv` so tên cột nguồn và bảng thử; `acs.f_wifi` gốc có 50 cột nên bảng thử giữ tối đa 40 cột theo giới hạn đã yêu cầu.", "- `generated/validation_report.json` ghi số bảng, số dòng, quan hệ và các kiểm tra đạt.", "- Các bảng còn lại là giả định để làm dữ liệu thử. Không thể chứng minh chúng trùng cấu trúc hệ thống công ty chỉ từ những file mẫu hiện có.", ""])
 (ROOT/"SOURCE_AND_REVIEW.md").write_text("\n".join(lines),encoding="utf-8")
 return counts

GRAINS={
 "ran_kpi.cell_hourly":"one cell per hour", "energy.station_hourly":"one station per hour",
 "transport.link_hourly":"one link per hour", "core.gateway_hourly":"one gateway per hour",
 "qos.service_hourly":"one service and province per hour",
 "aam.kpi_aam_daily_tdxl":"one KPI and location per hour from source snapshot",
 "aam.kpi_aam_daily_tlgd":"one KPI and province per hour",
 "aaa.authentication":"one login attempt", "aaa.accounting":"one completed session",
 "acs.f_uptime":"one device observation", "acs.f_wifi":"one device Wi-Fi observation",
 "billing.invoice":"one customer invoice per billing month",
}

if __name__=="__main__":
 result=write(build())
 print(f"Generated {len(SPECS)} schemas, {len(result)} tables, {sum(result.values())} rows in {OUT}")
