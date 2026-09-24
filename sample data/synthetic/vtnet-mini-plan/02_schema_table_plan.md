# Schema Và Table Plan

## Nguyên Tắc Thiết Kế

Schema/table plan bám theo Excel OM nhưng không bê nguyên toàn bộ 8k+ tables. V1 chọn một lát cắt đủ gần production, có domain rõ và có nhiễu vừa đủ để test NL2SQL.

Nguyên tắc:

- Giữ tên catalog/schema/table gần OM thật.
- Mỗi domain bắt buộc có tối thiểu 20 tables.
- Network KPI/5G là domain chính.
- Có bảng dimension dùng chung cho join location.
- Có schema noisy giống `hive_geo_old.pm_counter` để test retrieval.
- Không phải mọi table đều cần nhiều rows; một số table chỉ cần metadata và ít data.

## Phân Bố Schema Theo Excel OM

Thống kê từ Excel OM:

| Bucket table/schema | Số schema |
| --- | ---: |
| 0 table | 5 |
| 1-10 tables | 62 |
| 11-50 tables | 26 |
| 51-100 tables | 12 |
| 101-300 tables | 14 |
| 301-1000 tables | 3 |
| >1000 tables | 2 |

Vì median chỉ khoảng 9 tables/schema, mini v1 không nên tạo mọi schema đều 20 tables. Tuy nhiên yêu cầu domain tối thiểu 20 tables vẫn được đáp ứng bằng các schema/domain chính.

## Catalog Và Schema V1

| Catalog | Schema | Domain | Tables v1 | Vai trò |
| --- | --- | --- | ---: | --- |
| `hive` | `npms` | Network KPI/5G | 25-35 | KPI cell, traffic, blacklist |
| `hive` | `kpi_reports` | Network KPI/5G | 8-12 | bảng summary/report |
| `hive` | `netbi` | Common/location | 8-12 | province, area, district, date |
| `hive` | `geolocation` | Common/location | 8-12 | cell/site inventory |
| `hive` | `gnoc` | Alarm | 20-30 | alarm, ticket, outage, SLA |
| `hive` | `fbb` | FBB | 20-30 | FTTH, PPPoE, modem, QoE |
| `mysql_datamon` | `data_monitoring` | Data Monitoring | 20-30 | freshness, quality, campaign |
| `hive_geo_old` | `pm_counter` | Noisy metadata | 20-50 | bảng nhiễu, metadata-heavy |

Tổng v1:

```text
Executable core tables: 90-120
Noisy/metadata-only tables: 20-40
Total: 120-160 tables
```

## Network KPI/5G Tables

Các bảng tối thiểu:

| Table | Grain | Vai trò |
| --- | --- | --- |
| `hive.npms.kpi_access5g_5g_cell_peak_view` | cell-hour/day snapshot | bảng hard-case chính |
| `hive.npms.kpi_access5g_cell_daily` | cell-day | KPI 5G ngày |
| `hive.npms.kpi_access4g_cell_daily` | cell-day | KPI 4G để gây nhiễu |
| `hive.npms.kpi_cell_traffic_hourly` | cell-hour | traffic |
| `hive.npms.kpi_cell_throughput_hourly` | cell-hour | throughput |
| `hive.npms.kpi_cell_availability_daily` | cell-day | availability |
| `hive.npms.kpi_cell_latency_daily` | cell-day | latency |
| `hive.npms.kpi_cell_packet_loss_daily` | cell-day | packet loss |
| `hive.npms.kpi_cell_drop_call_daily` | cell-day | drop call |
| `hive.npms.kpi_cell_handover_daily` | cell-day | handover |
| `hive.npms.occean_cell` | cell snapshot | exclusion table như query mẫu |
| `hive.npms.cell_blacklist` | cell-date | blacklist mở rộng |
| `hive.npms.site_blacklist` | site-date | site exclusion |
| `hive.npms.cell_kpi_threshold` | metric/technology | threshold config |
| `hive.npms.cell_vendor_mapping` | cell | vendor |
| `hive.npms.cell_technology_mapping` | cell | 4G/5G |
| `hive.kpi_reports.daily_network_kpi` | date/location/metric | summary |
| `hive.kpi_reports.province_kpi_summary` | date/province | province report |
| `hive.kpi_reports.area_kpi_summary` | date/area | area report |
| `hive.kpi_reports.bad_cell_daily` | date/cell | bad cell output |
| `hive.kpi_reports.bad_cell_weekly` | week/cell | weekly bad cell |
| `hive.kpi_reports.network_quality_score` | date/location | score |

## Alarm Tables

| Table | Grain | Vai trò |
| --- | --- | --- |
| `hive.gnoc.network_alarm` | alarm event | alarm chính |
| `hive.gnoc.alarm_history` | alarm event state | lịch sử alarm |
| `hive.gnoc.alarm_ticket` | ticket | ticket xử lý |
| `hive.gnoc.alarm_rule` | rule | rule mapping |
| `hive.gnoc.alarm_severity_mapping` | alarm type | severity |
| `hive.gnoc.alarm_sla_policy` | severity/domain | SLA |
| `hive.gnoc.site_outage_event` | site outage | mất trạm |
| `hive.gnoc.cell_outage_event` | cell outage | mất cell |
| `hive.gnoc.transmission_alarm` | event | truyền dẫn |
| `hive.gnoc.power_alarm` | event | nguồn điện |
| `hive.gnoc.alarm_clear_log` | event | clear log |
| `hive.gnoc.alarm_ack_log` | event | ack log |
| `hive.gnoc.work_order` | work order | xử lý sự cố |
| `hive.gnoc.work_order_task` | task | chi tiết WO |
| `hive.gnoc.incident_daily_summary` | date/location | incident summary |
| `hive.gnoc.alarm_province_summary` | date/province | province summary |
| `hive.gnoc.alarm_area_summary` | date/area | area summary |
| `hive.gnoc.noc_shift` | shift | ca trực |
| `hive.gnoc.vendor_alarm_mapping` | alarm/vendor | mapping vendor |
| `hive.gnoc.alarm_root_cause` | alarm/ticket | root cause |

## FBB Tables

| Table | Grain | Vai trò |
| --- | --- | --- |
| `hive.fbb.ftth_subscriber` | subscriber | thuê bao |
| `hive.fbb.ftth_account_pppoe` | account | account PPPoE |
| `hive.fbb.pppoe_session_daily` | account-day | session ngày |
| `hive.fbb.pppoe_session_hourly` | account-hour | session giờ |
| `hive.fbb.modem_inventory` | device | modem |
| `hive.fbb.olt_inventory` | OLT | thiết bị OLT |
| `hive.fbb.pon_port_inventory` | port | PON port |
| `hive.fbb.ftth_service_order` | order | lệnh dịch vụ |
| `hive.fbb.ftth_trouble_ticket` | ticket | ticket FBB |
| `hive.fbb.ftth_speed_test` | test | speedtest |
| `hive.fbb.ftth_package` | package | gói cước |
| `hive.fbb.ftth_billing_daily` | account-day | billing |
| `hive.fbb.ftth_customer_profile` | customer | profile |
| `hive.fbb.ftth_churn_signal` | subscriber-date | churn signal |
| `hive.fbb.ftth_qoe_daily` | subscriber-day | QoE |
| `hive.fbb.ftth_area_summary` | date/area | summary area |
| `hive.fbb.ftth_province_summary` | date/province | summary province |
| `hive.fbb.ftth_installation_log` | order | installation |
| `hive.fbb.ftth_payment_status` | invoice/account | payment |
| `hive.fbb.ftth_device_event` | device event | device log |

## Data Monitoring Tables

| Table | Grain | Vai trò |
| --- | --- | --- |
| `mysql_datamon.data_monitoring.usersinarea_campaigns` | campaign/user-area | bảng gần OM thật |
| `mysql_datamon.data_monitoring.data_quality_check` | check config | rule DQ |
| `mysql_datamon.data_monitoring.data_quality_result` | check run | kết quả DQ |
| `mysql_datamon.data_monitoring.ingestion_job` | job | job ingest |
| `mysql_datamon.data_monitoring.ingestion_job_run` | job run | run history |
| `mysql_datamon.data_monitoring.source_table_profile` | table profile | profile nguồn |
| `mysql_datamon.data_monitoring.table_freshness_daily` | table-date | freshness |
| `mysql_datamon.data_monitoring.column_null_rate_daily` | column-date | null rate |
| `mysql_datamon.data_monitoring.column_anomaly_daily` | column-date | anomaly |
| `mysql_datamon.data_monitoring.pipeline_error_log` | error event | lỗi pipeline |
| `mysql_datamon.data_monitoring.campaign_target_area` | campaign-area | target |
| `mysql_datamon.data_monitoring.campaign_result` | campaign result | kết quả |
| `mysql_datamon.data_monitoring.user_area_mapping` | user-area | mapping |
| `mysql_datamon.data_monitoring.data_owner_registry` | table/owner | owner |
| `mysql_datamon.data_monitoring.sla_monitoring` | table/job | SLA |
| `mysql_datamon.data_monitoring.metric_catalog` | metric | metric registry |
| `mysql_datamon.data_monitoring.report_usage_log` | report event | usage |
| `mysql_datamon.data_monitoring.query_audit_log` | query event | audit |
| `mysql_datamon.data_monitoring.table_access_daily` | table-date | access |
| `mysql_datamon.data_monitoring.metadata_change_log` | metadata event | metadata changes |

## Common Dimension Tables

| Table | Grain | Vai trò |
| --- | --- | --- |
| `hive.netbi.f_location_new` | province | bảng join trong query mẫu |
| `hive.netbi.dim_province` | province | dimension |
| `hive.netbi.dim_area` | area | dimension |
| `hive.netbi.dim_district` | district | dimension |
| `hive.netbi.dim_date` | date | calendar |
| `hive.netbi.dim_hour` | date_hour | hour calendar |
| `hive.geolocation.cell_inventory` | cell | cell inventory |
| `hive.geolocation.site_inventory` | site | site inventory |
| `hive.geolocation.cell_location_history` | cell-date | lịch sử location |
| `hive.geolocation.vendor_mapping` | vendor | vendor mapping |

## Schema Noisy

`hive_geo_old.pm_counter` dùng để tạo nhiễu retrieval:

- Nhiều bảng có tên gần giống metric thật.
- Có description/tag nhưng dữ liệu ít hoặc metadata-only.
- Một số bảng cùng keyword `throughput`, `traffic`, `handover`, `counter`.
- Mục tiêu là test model có chọn đúng `hive.npms...` thay vì bảng counter cũ không.

Ví dụ:

```text
hive_geo_old.pm_counter.pm_5g_throughput_counter_daily
hive_geo_old.pm_counter.pm_5g_traffic_counter_hourly
hive_geo_old.pm_counter.pm_cell_handover_counter_daily
hive_geo_old.pm_counter.pm_cell_availability_counter_daily
```
