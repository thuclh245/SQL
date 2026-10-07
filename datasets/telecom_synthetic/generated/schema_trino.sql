CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: account_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_core)
-- FK plan_id -> product.plan.plan_id (synthetic_core)
CREATE TABLE IF NOT EXISTS aaa.ftth_account_pppoe (
  account_id VARCHAR,
  customer_id VARCHAR,
  username VARCHAR,
  groupname VARCHAR,
  loginlimit INTEGER,
  connection_count INTEGER,
  activation_date DATE,
  status VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  last_login_at TIMESTAMP,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  count INTEGER,
  count_time VARCHAR,
  date_hour VARCHAR
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: auth_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_core)
CREATE TABLE IF NOT EXISTS aaa.authentication (
  auth_id VARCHAR,
  account_id VARCHAR,
  session_id VARCHAR,
  event_time TIMESTAMP,
  date_hour VARCHAR,
  hostname VARCHAR,
  nas_ip VARCHAR,
  result VARCHAR,
  reject_reason VARCHAR,
  request_count INTEGER,
  accept_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE,
  retry_count INTEGER,
  province_code VARCHAR,
  timestamp VARCHAR,
  ip VARCHAR,
  sbr_server VARCHAR,
  request_current_rate VARCHAR,
  request_average_rate VARCHAR,
  request_peak_rate VARCHAR,
  accept VARCHAR,
  accept_current_rate VARCHAR,
  accept_average_rate VARCHAR,
  accept_peak_rate VARCHAR,
  reject VARCHAR,
  reject_current_rate VARCHAR,
  reject_average_rate VARCHAR,
  reject_peak_rate VARCHAR,
  invalid_request VARCHAR,
  failed_authentication VARCHAR,
  total_transactions VARCHAR,
  transactions_retried VARCHAR,
  dropped_packet VARCHAR,
  total_retry_packets VARCHAR,
  failed_on_check_list VARCHAR,
  insufficient_resources VARCHAR,
  silent_discard VARCHAR,
  proxy_failure VARCHAR,
  rejected_by_proxy VARCHAR
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: accounting_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_core)
-- FK session_id -> aaa.authentication.session_id (synthetic_core)
CREATE TABLE IF NOT EXISTS aaa.accounting (
  accounting_id VARCHAR,
  session_id VARCHAR,
  account_id VARCHAR,
  start_time TIMESTAMP,
  stop_time TIMESTAMP,
  date_hour VARCHAR,
  nas_ip VARCHAR,
  assigned_ip VARCHAR,
  upload_mb DOUBLE,
  download_mb DOUBLE,
  duration_s INTEGER,
  terminate_cause VARCHAR,
  dropped_packet INTEGER,
  timestamp VARCHAR,
  hostname VARCHAR,
  ip VARCHAR,
  sbr_server VARCHAR,
  start VARCHAR,
  acct_start_current_rate VARCHAR,
  acct_start_average_rate VARCHAR,
  acct_start_peak_rate VARCHAR,
  stop VARCHAR,
  acct_stop_current_rate VARCHAR,
  acct_stop_average_rate VARCHAR,
  acct_stop_peak_rate VARCHAR,
  interim VARCHAR,
  _acct_interim_current_rate VARCHAR,
  acct_interim_average_rate VARCHAR,
  acct_interim_peak_rate VARCHAR,
  invalid_request VARCHAR,
  invalid_client VARCHAR,
  total_retry_packets VARCHAR,
  total_transactions VARCHAR,
  transactions_retried VARCHAR,
  on_status VARCHAR,
  off_status VARCHAR,
  invalid_shared_secret VARCHAR,
  insufficient_resources VARCHAR,
  proxy_failure VARCHAR,
  acct_interim_current_rate VARCHAR
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: event_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_core)
-- FK customer_id -> customer.subscriber.customer_id (synthetic_core)
-- FK device_id -> acs.device_info.device_id (synthetic_core)
CREATE TABLE IF NOT EXISTS aaa.access_event (
  event_id VARCHAR,
  account_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  event_time TIMESTAMP,
  source_ip VARCHAR,
  event_type VARCHAR,
  result VARCHAR,
  risk_score INTEGER,
  failed_attempts INTEGER,
  device_id VARCHAR,
  rule_id VARCHAR,
  investigation_status VARCHAR
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: radius_server_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.radius_server (
  radius_server_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: radius_request_hourly_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.radius_request_hourly (
  radius_request_hourly_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: radius_reject_hourly_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.radius_reject_hourly (
  radius_reject_hourly_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: radius_timeout_hourly_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.radius_timeout_hourly (
  radius_timeout_hourly_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: pppoe_session_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.pppoe_session (
  pppoe_session_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: nas_device_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.nas_device (
  nas_device_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: nas_port_history_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.nas_port_history (
  nas_port_history_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: ip_assignment_history_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.ip_assignment_history (
  ip_assignment_history_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: ip_pool_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.ip_pool (
  ip_pool_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: ip_pool_hourly_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.ip_pool_hourly (
  ip_pool_hourly_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: auth_policy_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.auth_policy (
  auth_policy_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: auth_policy_change_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.auth_policy_change (
  auth_policy_change_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: credential_reset_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.credential_reset (
  credential_reset_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: login_failure_hourly_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.login_failure_hourly (
  login_failure_hourly_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: concurrent_session_hourly_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.concurrent_session_hourly (
  concurrent_session_hourly_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aaa;
-- Logical PK: account_lockout_hourly_id
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aaa.account_lockout_hourly (
  account_lockout_hourly_id VARCHAR,
  account_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  reject_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_id
CREATE TABLE IF NOT EXISTS aam.kpi_aam_daily_tdxl (
  kpi_id VARCHAR,
  kpi_code VARCHAR,
  location_level VARCHAR,
  location_code VARCHAR,
  area_code VARCHAR,
  area_name VARCHAR,
  province_code VARCHAR,
  province_name VARCHAR,
  date_hour VARCHAR,
  kpi_value DOUBLE,
  unit VARCHAR,
  threshold DOUBLE,
  breach_count INTEGER,
  source_system VARCHAR,
  computed_at TIMESTAMP,
  country VARCHAR,
  duration VARCHAR,
  n_count VARCHAR,
  type VARCHAR,
  thread_hold VARCHAR
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_id
-- FK province_code -> geo.province.province_code (synthetic_core)
CREATE TABLE IF NOT EXISTS aam.kpi_aam_daily_tlgd (
  kpi_id VARCHAR,
  kpi_code VARCHAR,
  location_level VARCHAR,
  location_code VARCHAR,
  area_code VARCHAR,
  province_code VARCHAR,
  date_hour VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  duration_ms DOUBLE,
  success_rate DOUBLE,
  source_system VARCHAR,
  computed_at TIMESTAMP,
  country VARCHAR,
  t_request VARCHAR,
  n_request_success VARCHAR,
  duration VARCHAR,
  n_count VARCHAR,
  type VARCHAR
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_definition_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_definition (
  kpi_definition_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_threshold_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_threshold (
  kpi_threshold_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_hourly_province_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_hourly_province (
  kpi_hourly_province_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_daily_province_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_daily_province (
  kpi_daily_province_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_hourly_area_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_hourly_area (
  kpi_hourly_area_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_daily_area_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_daily_area (
  kpi_daily_area_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_hourly_network_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_hourly_network (
  kpi_hourly_network_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_daily_network_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_daily_network (
  kpi_daily_network_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_breach_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_breach_hourly (
  kpi_breach_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_breach_daily_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_breach_daily (
  kpi_breach_daily_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_rollup_job_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_rollup_job (
  kpi_rollup_job_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_quality_audit_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_quality_audit (
  kpi_quality_audit_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_source_mapping_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_source_mapping (
  kpi_source_mapping_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_target_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_target (
  kpi_target_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_trend_daily_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_trend_daily (
  kpi_trend_daily_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_baseline_daily_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_baseline_daily (
  kpi_baseline_daily_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_anomaly_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_anomaly_hourly (
  kpi_anomaly_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS aam;
-- Logical PK: kpi_alert_history_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS aam.kpi_alert_history (
  kpi_alert_history_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sample_count INTEGER,
  breach_count INTEGER,
  baseline_value DOUBLE,
  change_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: device_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_core)
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS acs.device_info (
  device_id VARCHAR,
  ne_id VARCHAR,
  serial_number VARCHAR,
  customer_id VARCHAR,
  account_id VARCHAR,
  model VARCHAR,
  manufacturer VARCHAR,
  firmware_version VARCHAR,
  province_code VARCHAR,
  station_id VARCHAR,
  install_date DATE,
  status VARCHAR,
  wan_type VARCHAR,
  last_contact_at TIMESTAMP
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: uptime_id
-- FK device_id -> acs.device_info.device_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS acs.f_uptime (
  uptime_id VARCHAR,
  device_id VARCHAR,
  ne_id VARCHAR,
  record_time TIMESTAMP,
  date_hour VARCHAR,
  uptime_s INTEGER,
  uptime_delta_s INTEGER,
  wan_uptime_s INTEGER,
  connect_status VARCHAR,
  ip_address VARCHAR,
  province_code VARCHAR,
  station_id VARCHAR,
  firmware_version VARCHAR,
  temperature_c DOUBLE,
  duration BIGINT,
  created_date TIMESTAMP,
  uptime BIGINT,
  uptime_delta BIGINT,
  uptime_wanppp BIGINT,
  uptime_wanppp_delta BIGINT,
  product_class VARCHAR,
  sw_version VARCHAR,
  manufacture VARCHAR,
  serial_number VARCHAR,
  last_contact_time VARCHAR,
  pppoe_username VARCHAR,
  device_code VARCHAR,
  device_type_code VARCHAR,
  network_type VARCHAR,
  network_class VARCHAR,
  station_code VARCHAR,
  location_id VARCHAR,
  location_code VARCHAR,
  country_name VARCHAR,
  area_name VARCHAR,
  province_name VARCHAR,
  district_name VARCHAR,
  country_code VARCHAR,
  area_code VARCHAR,
  district_code VARCHAR
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: ne_id, date_hour
-- FK ne_id -> acs.device_info.ne_id (synthetic_core)
CREATE TABLE IF NOT EXISTS acs.g_uptime (
  date_hour_o VARCHAR,
  record_time VARCHAR,
  duration VARCHAR,
  ne_id VARCHAR,
  created_date VARCHAR,
  uptime VARCHAR,
  uptime_delta VARCHAR,
  uptime_wanppp VARCHAR,
  uptime_wanppp_delta VARCHAR,
  date_hour VARCHAR
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: wifi_id
-- FK device_id -> acs.device_info.device_id (synthetic_core)
CREATE TABLE IF NOT EXISTS acs.f_wifi (
  wifi_id VARCHAR,
  device_id VARCHAR,
  record_time TIMESTAMP,
  date_hour VARCHAR,
  ssid VARCHAR,
  band VARCHAR,
  channel INTEGER,
  standard VARCHAR,
  signal_dbm DOUBLE,
  noise_dbm DOUBLE,
  client_count INTEGER,
  tx_rate_mbps DOUBLE,
  rx_rate_mbps DOUBLE,
  retry_rate DOUBLE,
  province_code VARCHAR,
  duration BIGINT,
  ne_id BIGINT,
  created_date TIMESTAMP,
  wifi_name VARCHAR,
  wifi_max_bit_rate VARCHAR,
  wifi_channel BIGINT,
  wifi_ssid VARCHAR,
  wifi_standard VARCHAR,
  wifi_regulatory_domain VARCHAR,
  wifi_total_bytes_sent BIGINT,
  wifi_total_bytes_received BIGINT,
  wifi_total_packets_sent BIGINT,
  wifi_total_packets_received BIGINT,
  wifi_total_associations BIGINT,
  wifi_error_sent BIGINT,
  wifi_error_received BIGINT,
  wifi_total_psk_failures BIGINT,
  wifi_total_integrity_failures BIGINT,
  wifi_transmit_power BIGINT,
  ip_address VARCHAR,
  connect_status VARCHAR,
  product_class VARCHAR,
  sw_version VARCHAR,
  hardware_version VARCHAR,
  manufacture VARCHAR
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: cpe_config_history_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.cpe_config_history (
  cpe_config_history_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: firmware_catalog_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.firmware_catalog (
  firmware_catalog_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: firmware_rollout_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.firmware_rollout (
  firmware_rollout_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: firmware_upgrade_event_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.firmware_upgrade_event (
  firmware_upgrade_event_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: wan_interface_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.wan_interface (
  wan_interface_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: wan_hourly_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.wan_hourly (
  wan_hourly_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: lan_port_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.lan_port (
  lan_port_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: wifi_radio_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.wifi_radio (
  wifi_radio_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: wifi_client_hourly_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.wifi_client_hourly (
  wifi_client_hourly_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: optical_rx_hourly_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.optical_rx_hourly (
  optical_rx_hourly_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: optical_tx_hourly_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.optical_tx_hourly (
  optical_tx_hourly_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: reboot_event_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.reboot_event (
  reboot_event_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: configuration_change_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.configuration_change (
  configuration_change_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: remote_command_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.remote_command (
  remote_command_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: provisioning_event_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.provisioning_event (
  provisioning_event_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS acs;
-- Logical PK: device_fault_id
-- FK device_id -> acs.device_info.device_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS acs.device_fault (
  device_fault_id VARCHAR,
  device_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  temperature_c DOUBLE,
  uptime_s INTEGER,
  retry_count INTEGER,
  signal_dbm DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: location_id
-- FK country_code -> geo.country.country_code (synthetic_core)
-- FK area_code -> geo.area.area_code (synthetic_core)
-- FK province_code -> geo.province.province_code (synthetic_core)
-- FK district_code -> geo.district.district_code (synthetic_core)
CREATE TABLE IF NOT EXISTS geo.location (
  location_id VARCHAR,
  country_code VARCHAR,
  area_code VARCHAR,
  area_name VARCHAR,
  province_code VARCHAR,
  province_name VARCHAR,
  district_code VARCHAR,
  district_name VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  urban_flag INTEGER,
  timezone VARCHAR,
  active_from DATE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: country_code
CREATE TABLE IF NOT EXISTS geo.country (
  country_code VARCHAR,
  country_name VARCHAR,
  iso2 VARCHAR,
  region VARCHAR,
  currency VARCHAR,
  timezone VARCHAR,
  active_from DATE,
  active_to DATE,
  status VARCHAR,
  source_system VARCHAR
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: area_code
-- FK country_code -> geo.country.country_code (synthetic_core)
CREATE TABLE IF NOT EXISTS geo.area (
  area_code VARCHAR,
  country_code VARCHAR,
  area_name VARCHAR,
  sort_order INTEGER,
  province_count INTEGER,
  timezone VARCHAR,
  active_from DATE,
  active_to DATE,
  status VARCHAR,
  source_system VARCHAR
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: province_code
-- FK area_code -> geo.area.area_code (synthetic_core)
-- FK country_code -> geo.country.country_code (synthetic_core)
CREATE TABLE IF NOT EXISTS geo.province (
  province_code VARCHAR,
  area_code VARCHAR,
  country_code VARCHAR,
  province_name VARCHAR,
  urban_flag INTEGER,
  latitude DOUBLE,
  longitude DOUBLE,
  district_count INTEGER,
  active_from DATE,
  status VARCHAR,
  source_system VARCHAR
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: district_code
-- FK province_code -> geo.province.province_code (synthetic_core)
CREATE TABLE IF NOT EXISTS geo.district (
  district_code VARCHAR,
  province_code VARCHAR,
  district_name VARCHAR,
  administrative_type VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  ward_count INTEGER,
  active_from DATE,
  status VARCHAR,
  source_system VARCHAR
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: ward_code
-- FK district_code -> geo.district.district_code (synthetic_core)
CREATE TABLE IF NOT EXISTS geo.ward (
  ward_code VARCHAR,
  district_code VARCHAR,
  ward_name VARCHAR,
  administrative_type VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  active_from DATE,
  status VARCHAR,
  source_system VARCHAR
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: village_code
-- FK ward_code -> geo.ward.ward_code (synthetic_core)
CREATE TABLE IF NOT EXISTS geo.village (
  village_code VARCHAR,
  ward_code VARCHAR,
  village_name VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  active_from DATE,
  status VARCHAR,
  source_system VARCHAR,
  village_type VARCHAR
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: geo_boundary_history_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.geo_boundary_history (
  geo_boundary_history_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE,
  boundary_version VARCHAR,
  change_reason VARCHAR,
  area_km2 DOUBLE,
  effective_date DATE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: province_population_daily_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.province_population_daily (
  province_population_daily_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE,
  population_count INTEGER,
  household_count INTEGER,
  density_per_km2 DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: district_population_daily_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.district_population_daily (
  district_population_daily_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE,
  population_count INTEGER,
  household_count INTEGER,
  density_per_km2 DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: urban_classification_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.urban_classification (
  urban_classification_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: terrain_profile_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.terrain_profile (
  terrain_profile_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: climate_zone_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.climate_zone (
  climate_zone_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: weather_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.weather_hourly (
  weather_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: rainfall_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.rainfall_hourly (
  rainfall_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: temperature_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.temperature_hourly (
  temperature_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: location_alias_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.location_alias (
  location_alias_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE,
  alias_name VARCHAR,
  alias_type VARCHAR,
  language_code VARCHAR,
  normalized_name VARCHAR
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: station_coverage_area_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.station_coverage_area (
  station_coverage_area_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: cell_coverage_area_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.cell_coverage_area (
  cell_coverage_area_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS geo;
-- Logical PK: service_zone_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS geo.service_zone (
  service_zone_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  population_est INTEGER,
  coverage_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: station_id
-- FK location_id -> geo.location.location_id (synthetic_core)
CREATE TABLE IF NOT EXISTS inventory.station (
  station_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  station_name VARCHAR,
  station_type VARCHAR,
  latitude DOUBLE,
  longitude DOUBLE,
  commissioned_date DATE,
  power_source VARCHAR,
  backhaul_type VARCHAR,
  status VARCHAR,
  vendor VARCHAR,
  site_capacity INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: equipment_rack_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.equipment_rack (
  equipment_rack_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: equipment_card_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.equipment_card (
  equipment_card_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: equipment_port_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.equipment_port (
  equipment_port_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: antenna_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.antenna (
  antenna_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: cable_segment_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.cable_segment (
  cable_segment_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: splitter_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.splitter (
  splitter_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: fiber_core_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.fiber_core (
  fiber_core_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: optical_module_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.optical_module (
  optical_module_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: battery_unit_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.battery_unit (
  battery_unit_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: generator_unit_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.generator_unit (
  generator_unit_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: rectifier_unit_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.rectifier_unit (
  rectifier_unit_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: air_conditioner_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.air_conditioner (
  air_conditioner_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: spare_part_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.spare_part (
  spare_part_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: stock_balance_daily_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.stock_balance_daily (
  stock_balance_daily_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: warehouse_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.warehouse (
  warehouse_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: supplier_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.supplier (
  supplier_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: purchase_order_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.purchase_order (
  purchase_order_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: asset_movement_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.asset_movement (
  asset_movement_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS inventory;
-- Logical PK: site_lease_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS inventory.site_lease (
  site_lease_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  asset_count INTEGER,
  installed_count INTEGER,
  age_days INTEGER,
  unit_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: cell_id
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS ran.cell (
  cell_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  object_id VARCHAR,
  technology VARCHAR,
  band VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  vendor VARCHAR,
  sector INTEGER,
  azimuth_deg INTEGER,
  launch_date DATE,
  status VARCHAR,
  capacity_users INTEGER,
  area_code VARCHAR
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: sector_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.sector (
  sector_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: carrier_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.carrier (
  carrier_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: neighbor_relation_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.neighbor_relation (
  neighbor_relation_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: intra_freq_neighbor_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.intra_freq_neighbor (
  intra_freq_neighbor_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: inter_freq_neighbor_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.inter_freq_neighbor (
  inter_freq_neighbor_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: handover_relation_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.handover_relation (
  handover_relation_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: pci_assignment_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.pci_assignment (
  pci_assignment_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: tac_assignment_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.tac_assignment (
  tac_assignment_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: frequency_plan_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.frequency_plan (
  frequency_plan_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: antenna_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.antenna_config (
  antenna_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: mimo_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.mimo_config (
  mimo_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: beam_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.beam_config (
  beam_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: power_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.power_config (
  power_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: rach_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.rach_config (
  rach_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: scheduler_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.scheduler_config (
  scheduler_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: admission_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.admission_config (
  admission_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: cell_state_history_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.cell_state_history (
  cell_state_history_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: cell_activation_event_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.cell_activation_event (
  cell_activation_event_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran;
-- Logical PK: carrier_aggregation_config_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran.carrier_aggregation_config (
  carrier_aggregation_config_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  frequency_mhz INTEGER,
  bandwidth_mhz INTEGER,
  tx_power_dbm DOUBLE,
  sector_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_id, date_hour
-- FK cell_id -> ran.cell.cell_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_hourly (
  cell_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  date_hour VARCHAR,
  utc_time_ms BIGINT,
  availability_pct DOUBLE,
  dl_traffic_gb DOUBLE,
  ul_traffic_gb DOUBLE,
  dl_throughput_mbps DOUBLE,
  ul_throughput_mbps DOUBLE,
  rrc_attempt INTEGER,
  rrc_success INTEGER,
  ho_attempt INTEGER,
  ho_success INTEGER,
  prb_dl_util_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE,
  active_users INTEGER,
  kpi_quality_flag VARCHAR
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_traffic_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_traffic_hourly (
  cell_traffic_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_access_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_access_hourly (
  cell_access_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_retention_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_retention_hourly (
  cell_retention_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_mobility_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_mobility_hourly (
  cell_mobility_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_availability_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_availability_hourly (
  cell_availability_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_prb_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_prb_hourly (
  cell_prb_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_throughput_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_throughput_hourly (
  cell_throughput_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_latency_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_latency_hourly (
  cell_latency_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_packet_loss_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_packet_loss_hourly (
  cell_packet_loss_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_rach_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_rach_hourly (
  cell_rach_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_rrc_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_rrc_hourly (
  cell_rrc_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_handover_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_handover_hourly (
  cell_handover_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_sinr_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_sinr_hourly (
  cell_sinr_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_cqi_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_cqi_hourly (
  cell_cqi_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_bler_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_bler_hourly (
  cell_bler_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_mcs_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_mcs_hourly (
  cell_mcs_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_modulation_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_modulation_hourly (
  cell_modulation_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_users_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_users_hourly (
  cell_users_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS ran_kpi;
-- Logical PK: cell_congestion_hourly_id
-- FK cell_id -> ran.cell.cell_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ran_kpi.cell_congestion_hourly (
  cell_congestion_hourly_id VARCHAR,
  cell_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  attempt_count INTEGER,
  success_count INTEGER,
  traffic_gb DOUBLE,
  availability_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: link_id, date_hour
-- FK from_station_id -> inventory.station.station_id (synthetic_core)
-- FK to_station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS transport.link_hourly (
  link_id VARCHAR,
  from_station_id VARCHAR,
  to_station_id VARCHAR,
  province_code VARCHAR,
  date_hour VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE,
  availability_pct DOUBLE,
  link_type VARCHAR,
  vendor VARCHAR,
  status VARCHAR
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: fiber_route_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.fiber_route (
  fiber_route_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: fiber_span_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.fiber_span (
  fiber_span_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: fiber_fault_event_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.fiber_fault_event (
  fiber_fault_event_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: microwave_link_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.microwave_link (
  microwave_link_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: microwave_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.microwave_hourly (
  microwave_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: router_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.router (
  router_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: switch_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.switch (
  switch_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: port_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.port (
  port_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: port_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.port_hourly (
  port_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: vlan_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.vlan (
  vlan_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: mpls_tunnel_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.mpls_tunnel (
  mpls_tunnel_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: mpls_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.mpls_hourly (
  mpls_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: bgp_peer_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.bgp_peer (
  bgp_peer_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: bgp_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.bgp_hourly (
  bgp_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: optical_channel_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.optical_channel (
  optical_channel_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: optical_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.optical_hourly (
  optical_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: link_alarm_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.link_alarm (
  link_alarm_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: path_reroute_event_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.path_reroute_event (
  path_reroute_event_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS transport;
-- Logical PK: backbone_node_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS transport.backbone_node (
  backbone_node_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  capacity_mbps DOUBLE,
  utilization_pct DOUBLE,
  latency_ms DOUBLE,
  packet_loss_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: gateway_id, date_hour
-- FK province_code -> geo.province.province_code (synthetic_core)
CREATE TABLE IF NOT EXISTS core.gateway_hourly (
  gateway_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  date_hour VARCHAR,
  active_sessions INTEGER,
  attach_attempt INTEGER,
  attach_success INTEGER,
  traffic_gb DOUBLE,
  cpu_pct DOUBLE,
  memory_pct DOUBLE,
  latency_ms DOUBLE,
  drop_count INTEGER,
  status VARCHAR
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: amf_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.amf_node (
  amf_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: smf_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.smf_node (
  smf_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: upf_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.upf_node (
  upf_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: mme_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.mme_node (
  mme_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: sgw_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.sgw_node (
  sgw_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: pgw_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.pgw_node (
  pgw_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: dns_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.dns_node (
  dns_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: dhcp_node_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.dhcp_node (
  dhcp_node_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: subscriber_attach_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.subscriber_attach_hourly (
  subscriber_attach_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: bearer_setup_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.bearer_setup_hourly (
  bearer_setup_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: session_setup_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.session_setup_hourly (
  session_setup_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: session_drop_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.session_drop_hourly (
  session_drop_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: core_latency_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.core_latency_hourly (
  core_latency_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: core_memory_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.core_memory_hourly (
  core_memory_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: core_traffic_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.core_traffic_hourly (
  core_traffic_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: apn_usage_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.apn_usage_hourly (
  apn_usage_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: slice_usage_hourly_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.slice_usage_hourly (
  slice_usage_hourly_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: gateway_alarm_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.gateway_alarm (
  gateway_alarm_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS core;
-- Logical PK: core_config_change_id
-- FK location_id -> geo.location.location_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS core.core_config_change (
  core_config_change_id VARCHAR,
  location_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  session_count INTEGER,
  request_count INTEGER,
  success_count INTEGER,
  cpu_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: service_id, plan_id, province_code, date_hour
-- FK plan_id -> product.plan.plan_id (synthetic_core)
-- FK province_code -> geo.province.province_code (synthetic_core)
CREATE TABLE IF NOT EXISTS qos.service_hourly (
  service_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  date_hour VARCHAR,
  technology VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  jitter_ms DOUBLE,
  packet_loss_pct DOUBLE,
  availability_pct DOUBLE,
  breach_count INTEGER,
  status VARCHAR
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: sla_policy_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.sla_policy (
  sla_policy_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: sla_target_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.sla_target (
  sla_target_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: sla_result_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.sla_result_hourly (
  sla_result_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: sla_result_daily_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.sla_result_daily (
  sla_result_daily_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: application_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.application_hourly (
  application_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: video_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.video_hourly (
  video_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: gaming_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.gaming_hourly (
  gaming_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: web_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.web_hourly (
  web_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: voice_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.voice_hourly (
  voice_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: download_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.download_hourly (
  download_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: upload_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.upload_hourly (
  upload_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: dns_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.dns_hourly (
  dns_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: tcp_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.tcp_hourly (
  tcp_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: udp_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.udp_hourly (
  udp_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: jitter_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.jitter_hourly (
  jitter_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: packet_loss_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.packet_loss_hourly (
  packet_loss_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: latency_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.latency_hourly (
  latency_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: throughput_hourly_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.throughput_hourly (
  throughput_hourly_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS qos;
-- Logical PK: qos_breach_event_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS qos.qos_breach_event (
  qos_breach_event_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  p95_latency_ms DOUBLE,
  breach_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: alarm_id
-- FK entity_id -> ran.cell.cell_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_core)
CREATE TABLE IF NOT EXISTS fault.alarm (
  alarm_id VARCHAR,
  entity_type VARCHAR,
  entity_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  opened_at TIMESTAMP,
  closed_at TIMESTAMP,
  severity VARCHAR,
  alarm_code VARCHAR,
  root_cause VARCHAR,
  status VARCHAR,
  source_system VARCHAR,
  impact_users INTEGER,
  ticket_id VARCHAR
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: alarm_rule_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.alarm_rule (
  alarm_rule_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: alarm_suppression_id
-- FK alarm_id -> fault.alarm.alarm_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.alarm_suppression (
  alarm_suppression_id VARCHAR,
  alarm_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: alarm_correlation_id
-- FK alarm_id -> fault.alarm.alarm_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.alarm_correlation (
  alarm_correlation_id VARCHAR,
  alarm_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: alarm_escalation_id
-- FK alarm_id -> fault.alarm.alarm_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.alarm_escalation (
  alarm_escalation_id VARCHAR,
  alarm_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: alarm_history_id
-- FK alarm_id -> fault.alarm.alarm_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.alarm_history (
  alarm_history_id VARCHAR,
  alarm_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: fault_class_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.fault_class (
  fault_class_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: fault_root_cause_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.fault_root_cause (
  fault_root_cause_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: fault_impact_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.fault_impact_hourly (
  fault_impact_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: fault_impact_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.fault_impact_daily (
  fault_impact_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: cell_outage_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.cell_outage (
  cell_outage_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: station_outage_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.station_outage (
  station_outage_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: power_fault_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.power_fault (
  power_fault_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: transport_fault_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.transport_fault (
  transport_fault_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: device_fault_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.device_fault (
  device_fault_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: fiber_cut_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.fiber_cut (
  fiber_cut_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: degradation_event_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.degradation_event (
  degradation_event_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: recurring_fault_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.recurring_fault (
  recurring_fault_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: weather_related_fault_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.weather_related_fault (
  weather_related_fault_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS fault;
-- Logical PK: maintenance_related_fault_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS fault.maintenance_related_fault (
  maintenance_related_fault_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  impact_users INTEGER,
  duration_min INTEGER,
  repeat_count INTEGER,
  priority_score INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: ticket_id
-- FK alarm_id -> fault.alarm.alarm_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS ops.ticket (
  ticket_id VARCHAR,
  alarm_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  opened_at TIMESTAMP,
  acknowledged_at TIMESTAMP,
  resolved_at TIMESTAMP,
  priority VARCHAR,
  category VARCHAR,
  assigned_team VARCHAR,
  status VARCHAR,
  sla_deadline TIMESTAMP,
  resolution_code VARCHAR,
  repeat_incident INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: visit_id
-- FK work_order_id -> maintenance.work_order.work_order_id (synthetic_core)
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS ops.technician_visit (
  visit_id VARCHAR,
  work_order_id VARCHAR,
  ticket_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  technician_id VARCHAR,
  scheduled_at TIMESTAMP,
  arrived_at TIMESTAMP,
  completed_at TIMESTAMP,
  visit_type VARCHAR,
  result VARCHAR,
  travel_km DOUBLE,
  parts_used_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: noc_shift_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.noc_shift (
  noc_shift_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: noc_shift_handover_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.noc_shift_handover (
  noc_shift_handover_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: ticket_history_id
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.ticket_history (
  ticket_history_id VARCHAR,
  ticket_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: ticket_comment_id
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.ticket_comment (
  ticket_comment_id VARCHAR,
  ticket_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: ticket_assignment_id
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.ticket_assignment (
  ticket_assignment_id VARCHAR,
  ticket_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: ticket_escalation_id
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.ticket_escalation (
  ticket_escalation_id VARCHAR,
  ticket_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: ticket_sla_hourly_id
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.ticket_sla_hourly (
  ticket_sla_hourly_id VARCHAR,
  ticket_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: dispatch_request_id
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.dispatch_request (
  dispatch_request_id VARCHAR,
  ticket_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: crew_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.crew (
  crew_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: roster_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.roster (
  roster_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: technician_skill_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.technician_skill (
  technician_skill_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: technician_certification_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.technician_certification (
  technician_certification_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: visit_checklist_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.visit_checklist (
  visit_checklist_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: spare_part_usage_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.spare_part_usage (
  spare_part_usage_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: repair_action_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.repair_action (
  repair_action_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: incident_timeline_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.incident_timeline (
  incident_timeline_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: operational_kpi_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.operational_kpi_daily (
  operational_kpi_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS ops;
-- Logical PK: escalation_policy_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS ops.escalation_policy (
  escalation_policy_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  sla_minutes INTEGER,
  response_minutes INTEGER,
  resolution_minutes INTEGER,
  reopen_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: work_order_id
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS maintenance.work_order (
  work_order_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  ticket_id VARCHAR,
  scheduled_start TIMESTAMP,
  scheduled_end TIMESTAMP,
  actual_start TIMESTAMP,
  actual_end TIMESTAMP,
  work_type VARCHAR,
  crew_id VARCHAR,
  status VARCHAR,
  downtime_min INTEGER,
  planned_flag INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: maintenance_plan_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.maintenance_plan (
  maintenance_plan_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: preventive_schedule_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.preventive_schedule (
  preventive_schedule_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: corrective_schedule_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.corrective_schedule (
  corrective_schedule_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: inspection_schedule_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.inspection_schedule (
  inspection_schedule_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: inspection_result_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.inspection_result (
  inspection_result_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: work_order_history_id
-- FK work_order_id -> maintenance.work_order.work_order_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.work_order_history (
  work_order_history_id VARCHAR,
  work_order_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: work_order_task_id
-- FK work_order_id -> maintenance.work_order.work_order_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.work_order_task (
  work_order_task_id VARCHAR,
  work_order_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: work_order_material_id
-- FK work_order_id -> maintenance.work_order.work_order_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.work_order_material (
  work_order_material_id VARCHAR,
  work_order_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: work_order_labor_id
-- FK work_order_id -> maintenance.work_order.work_order_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.work_order_labor (
  work_order_labor_id VARCHAR,
  work_order_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: site_access_permit_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.site_access_permit (
  site_access_permit_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: vendor_contract_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.vendor_contract (
  vendor_contract_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: warranty_claim_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.warranty_claim (
  warranty_claim_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: repair_log_id
-- FK work_order_id -> maintenance.work_order.work_order_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.repair_log (
  repair_log_id VARCHAR,
  work_order_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: preventive_checklist_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.preventive_checklist (
  preventive_checklist_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: battery_inspection_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.battery_inspection (
  battery_inspection_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER,
  voltage_v DOUBLE,
  capacity_pct DOUBLE,
  terminal_condition VARCHAR,
  inspection_result VARCHAR
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: generator_inspection_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.generator_inspection (
  generator_inspection_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER,
  fuel_level_pct DOUBLE,
  oil_pressure_kpa DOUBLE,
  start_test_result VARCHAR,
  inspection_result VARCHAR
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: fiber_inspection_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.fiber_inspection (
  fiber_inspection_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER,
  optical_loss_db DOUBLE,
  connector_cleanliness VARCHAR,
  inspection_result VARCHAR
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: antenna_inspection_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.antenna_inspection (
  antenna_inspection_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER,
  tilt_deg DOUBLE,
  azimuth_deg INTEGER,
  vswr DOUBLE,
  connector_condition VARCHAR,
  inspection_result VARCHAR
);

CREATE SCHEMA IF NOT EXISTS maintenance;
-- Logical PK: maintenance_kpi_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS maintenance.maintenance_kpi_daily (
  maintenance_kpi_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  planned_duration_min INTEGER,
  actual_duration_min INTEGER,
  part_count INTEGER,
  labor_cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_id
-- FK province_code -> geo.province.province_code (synthetic_core)
CREATE TABLE IF NOT EXISTS customer.subscriber (
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  segment VARCHAR,
  join_date DATE,
  status VARCHAR,
  household_size INTEGER,
  preferred_channel VARCHAR,
  consent_analytics INTEGER,
  risk_band VARCHAR,
  account_manager_id VARCHAR,
  service_address_zone VARCHAR
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: household_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.household (
  household_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_contact_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_contact (
  customer_contact_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_contact_history_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_contact_history (
  customer_contact_history_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_segment_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_segment (
  customer_segment_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_segment_history_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_segment_history (
  customer_segment_history_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_risk_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_risk_daily (
  customer_risk_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_value_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_value_daily (
  customer_value_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_churn_score_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_churn_score (
  customer_churn_score_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_consent_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_consent (
  customer_consent_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_preference_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_preference (
  customer_preference_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_address_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_address (
  customer_address_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_device_map_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_device_map (
  customer_device_map_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: subscriber_status_history_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.subscriber_status_history (
  subscriber_status_history_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: onboarding_event_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.onboarding_event (
  onboarding_event_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: retention_offer_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.retention_offer (
  retention_offer_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: campaign_exposure_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.campaign_exposure (
  campaign_exposure_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_feedback_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_feedback (
  customer_feedback_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: customer_interaction_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.customer_interaction (
  customer_interaction_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS customer;
-- Logical PK: channel_usage_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS customer.channel_usage_daily (
  channel_usage_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  tenure_months INTEGER,
  interaction_count INTEGER,
  satisfaction_score INTEGER,
  churn_score DOUBLE
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: plan_id
CREATE TABLE IF NOT EXISTS product.plan (
  plan_id VARCHAR,
  service_id VARCHAR,
  plan_name VARCHAR,
  technology VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  data_cap_gb INTEGER,
  contract_months INTEGER,
  active_from DATE,
  active_to DATE,
  status VARCHAR
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: product_catalog_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.product_catalog (
  product_catalog_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: product_bundle_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.product_bundle (
  product_bundle_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: product_feature_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.product_feature (
  product_feature_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: plan_history_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.plan_history (
  plan_history_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: plan_price_history_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.plan_price_history (
  plan_price_history_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: plan_eligibility_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.plan_eligibility (
  plan_eligibility_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: plan_upgrade_rule_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.plan_upgrade_rule (
  plan_upgrade_rule_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: plan_discount_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.plan_discount (
  plan_discount_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: promotion_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.promotion (
  promotion_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: promotion_eligibility_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.promotion_eligibility (
  promotion_eligibility_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: addon_catalog_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.addon_catalog (
  addon_catalog_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: addon_subscription_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.addon_subscription (
  addon_subscription_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: tariff_band_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.tariff_band (
  tariff_band_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: speed_tier_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.speed_tier (
  speed_tier_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: data_allowance_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.data_allowance (
  data_allowance_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: contract_template_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.contract_template (
  contract_template_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: service_entitlement_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.service_entitlement (
  service_entitlement_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: product_availability_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.product_availability (
  product_availability_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS product;
-- Logical PK: product_usage_daily_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS product.product_usage_daily (
  product_usage_daily_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  monthly_fee_vnd INTEGER,
  down_mbps INTEGER,
  up_mbps INTEGER,
  eligible_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: invoice_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_core)
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_core)
-- FK plan_id -> product.plan.plan_id (synthetic_core)
-- FK province_code -> geo.province.province_code (synthetic_core)
CREATE TABLE IF NOT EXISTS billing.invoice (
  invoice_id VARCHAR,
  customer_id VARCHAR,
  account_id VARCHAR,
  plan_id VARCHAR,
  billing_month VARCHAR,
  issued_date DATE,
  due_date DATE,
  base_amount_vnd INTEGER,
  adjustment_vnd INTEGER,
  tax_vnd INTEGER,
  total_vnd INTEGER,
  paid_vnd INTEGER,
  status VARCHAR,
  province_code VARCHAR
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: station_id, cost_date
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS billing.cost_center_daily (
  cost_center_id VARCHAR,
  province_code VARCHAR,
  station_id VARCHAR,
  cost_date DATE,
  energy_cost_vnd INTEGER,
  maintenance_cost_vnd INTEGER,
  transport_cost_vnd INTEGER,
  depreciation_vnd INTEGER,
  total_cost_vnd INTEGER,
  budget_vnd INTEGER,
  variance_vnd INTEGER,
  currency VARCHAR,
  approval_status VARCHAR
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: invoice_line_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.invoice_line (
  invoice_line_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: payment_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.payment (
  payment_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: payment_attempt_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.payment_attempt (
  payment_attempt_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: payment_method_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.payment_method (
  payment_method_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: payment_reversal_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.payment_reversal (
  payment_reversal_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: refund_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.refund (
  refund_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: credit_note_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.credit_note (
  credit_note_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: discount_applied_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.discount_applied (
  discount_applied_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: tax_rule_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.tax_rule (
  tax_rule_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: billing_cycle_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.billing_cycle (
  billing_cycle_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: billing_adjustment_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.billing_adjustment (
  billing_adjustment_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: overdue_balance_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.overdue_balance (
  overdue_balance_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: revenue_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.revenue_daily (
  revenue_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: revenue_monthly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.revenue_monthly (
  revenue_monthly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: collection_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.collection_daily (
  collection_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: writeoff_event_id
-- FK invoice_id -> billing.invoice.invoice_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.writeoff_event (
  writeoff_event_id VARCHAR,
  invoice_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: cost_allocation_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.cost_allocation (
  cost_allocation_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS billing;
-- Logical PK: budget_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS billing.budget_daily (
  budget_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  amount_vnd INTEGER,
  tax_vnd INTEGER,
  paid_vnd INTEGER,
  outstanding_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: subscription_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_core)
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_core)
-- FK plan_id -> product.plan.plan_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS service.subscription (
  subscription_id VARCHAR,
  customer_id VARCHAR,
  account_id VARCHAR,
  plan_id VARCHAR,
  service_id VARCHAR,
  province_code VARCHAR,
  start_date DATE,
  end_date DATE,
  status VARCHAR,
  access_technology VARCHAR,
  station_id VARCHAR,
  last_change_at TIMESTAMP,
  monthly_fee_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_catalog_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_catalog (
  service_catalog_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_order_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_order (
  service_order_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: order_item_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.order_item (
  order_item_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: activation_event_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.activation_event (
  activation_event_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: provisioning_task_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.provisioning_task (
  provisioning_task_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: suspension_event_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.suspension_event (
  suspension_event_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: restoration_event_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.restoration_event (
  restoration_event_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: termination_event_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.termination_event (
  termination_event_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: subscription_history_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.subscription_history (
  subscription_history_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_migration_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_migration (
  service_migration_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_health_hourly_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_health_hourly (
  service_health_hourly_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_usage_hourly_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_usage_hourly (
  service_usage_hourly_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_eligibility_id
-- FK plan_id -> product.plan.plan_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_eligibility (
  service_eligibility_id VARCHAR,
  plan_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_sla_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_sla (
  service_sla_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_dependency_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_dependency (
  service_dependency_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_endpoint_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_endpoint (
  service_endpoint_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_config_history_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_config_history (
  service_config_history_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_notification_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_notification (
  service_notification_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS service;
-- Logical PK: service_incident_link_id
-- FK subscription_id -> service.subscription.subscription_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS service.service_incident_link (
  service_incident_link_id VARCHAR,
  subscription_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  request_count INTEGER,
  success_count INTEGER,
  active_count INTEGER,
  latency_ms DOUBLE
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: complaint_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_core)
-- FK account_id -> aaa.ftth_account_pppoe.account_id (synthetic_core)
-- FK station_id -> inventory.station.station_id (synthetic_core)
-- FK ticket_id -> ops.ticket.ticket_id (synthetic_core)
CREATE TABLE IF NOT EXISTS experience.complaint (
  complaint_id VARCHAR,
  customer_id VARCHAR,
  account_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  opened_at TIMESTAMP,
  closed_at TIMESTAMP,
  category VARCHAR,
  channel VARCHAR,
  severity VARCHAR,
  status VARCHAR,
  satisfaction_score INTEGER,
  ticket_id VARCHAR,
  repeat_contact INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: survey_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.survey (
  survey_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: survey_response_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.survey_response (
  survey_response_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: nps_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.nps_daily (
  nps_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: csat_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.csat_daily (
  csat_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: complaint_history_id
-- FK complaint_id -> experience.complaint.complaint_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.complaint_history (
  complaint_history_id VARCHAR,
  complaint_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: complaint_category_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.complaint_category (
  complaint_category_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: complaint_resolution_id
-- FK complaint_id -> experience.complaint.complaint_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.complaint_resolution (
  complaint_resolution_id VARCHAR,
  complaint_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: complaint_sla_id
-- FK complaint_id -> experience.complaint.complaint_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.complaint_sla (
  complaint_sla_id VARCHAR,
  complaint_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: complaint_escalation_id
-- FK complaint_id -> experience.complaint.complaint_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.complaint_escalation (
  complaint_escalation_id VARCHAR,
  complaint_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: contact_center_call_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.contact_center_call (
  contact_center_call_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: chat_session_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.chat_session (
  chat_session_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: app_feedback_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.app_feedback (
  app_feedback_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: network_experience_hourly_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.network_experience_hourly (
  network_experience_hourly_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: speed_test_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.speed_test (
  speed_test_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: outage_notification_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.outage_notification (
  outage_notification_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: sentiment_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.sentiment_daily (
  sentiment_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: repeat_contact_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.repeat_contact_daily (
  repeat_contact_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: journey_event_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.journey_event (
  journey_event_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS experience;
-- Logical PK: customer_effort_daily_id
-- FK customer_id -> customer.subscriber.customer_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS experience.customer_effort_daily (
  customer_effort_daily_id VARCHAR,
  customer_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  response_count INTEGER,
  positive_count INTEGER,
  score DOUBLE,
  repeat_count INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: station_id, date_hour
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS energy.station_hourly (
  station_id VARCHAR,
  province_code VARCHAR,
  date_hour VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  solar_kwh DOUBLE,
  battery_soc_pct DOUBLE,
  load_kw DOUBLE,
  ambient_temp_c DOUBLE,
  site_temp_c DOUBLE,
  power_outage_min INTEGER,
  alarm_flag INTEGER,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: meter_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.meter (
  meter_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: meter_reading_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.meter_reading_hourly (
  meter_reading_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: grid_supply_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.grid_supply_hourly (
  grid_supply_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: generator_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.generator_hourly (
  generator_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: solar_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.solar_hourly (
  solar_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: battery_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.battery_hourly (
  battery_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: load_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.load_hourly (
  load_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: power_quality_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.power_quality_hourly (
  power_quality_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: energy_cost_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.energy_cost_daily (
  energy_cost_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: carbon_emission_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.carbon_emission_daily (
  carbon_emission_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: cooling_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.cooling_hourly (
  cooling_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: temperature_alarm_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.temperature_alarm (
  temperature_alarm_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: power_outage_event_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.power_outage_event (
  power_outage_event_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: fuel_refill_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.fuel_refill (
  fuel_refill_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: generator_maintenance_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.generator_maintenance (
  generator_maintenance_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: battery_health_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.battery_health_daily (
  battery_health_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: renewable_mix_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.renewable_mix_daily (
  renewable_mix_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: energy_anomaly_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.energy_anomaly_hourly (
  energy_anomaly_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS energy;
-- Logical PK: tariff_history_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS energy.tariff_history (
  tariff_history_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  grid_kwh DOUBLE,
  generator_kwh DOUBLE,
  load_kw DOUBLE,
  cost_vnd INTEGER
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: station_id, forecast_date
-- FK station_id -> inventory.station.station_id (synthetic_core)
CREATE TABLE IF NOT EXISTS capacity.forecast_daily (
  station_id VARCHAR,
  province_code VARCHAR,
  forecast_date DATE,
  technology VARCHAR,
  forecast_traffic_gb DOUBLE,
  forecast_peak_users INTEGER,
  available_capacity_mbps DOUBLE,
  projected_util_pct DOUBLE,
  model_version VARCHAR,
  generated_at TIMESTAMP,
  confidence_low DOUBLE,
  confidence_high DOUBLE,
  risk_level VARCHAR
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: cell_capacity_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.cell_capacity_daily (
  cell_capacity_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: station_capacity_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.station_capacity_daily (
  station_capacity_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: backhaul_capacity_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.backhaul_capacity_daily (
  backhaul_capacity_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: core_capacity_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.core_capacity_daily (
  core_capacity_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: spectrum_capacity_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.spectrum_capacity_daily (
  spectrum_capacity_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: port_capacity_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.port_capacity_daily (
  port_capacity_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: storage_capacity_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.storage_capacity_daily (
  storage_capacity_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: forecast_hourly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.forecast_hourly (
  forecast_hourly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: forecast_monthly_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.forecast_monthly (
  forecast_monthly_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: demand_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.demand_daily (
  demand_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: utilization_daily_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.utilization_daily (
  utilization_daily_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  date_hour VARCHAR,
  observed_at TIMESTAMP,
  metric_value DOUBLE,
  metric_unit VARCHAR,
  quality_flag VARCHAR,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: saturation_event_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.saturation_event (
  saturation_event_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: expansion_plan_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.expansion_plan (
  expansion_plan_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: expansion_project_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.expansion_project (
  expansion_project_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: upgrade_candidate_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.upgrade_candidate (
  upgrade_candidate_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: planning_scenario_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.planning_scenario (
  planning_scenario_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: investment_case_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.investment_case (
  investment_case_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: capacity_alert_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.capacity_alert (
  capacity_alert_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  event_time TIMESTAMP,
  event_code VARCHAR,
  severity VARCHAR,
  outcome VARCHAR,
  duration_s INTEGER,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);

CREATE SCHEMA IF NOT EXISTS capacity;
-- Logical PK: capacity_model_run_id
-- FK station_id -> inventory.station.station_id (synthetic_assumption)
CREATE TABLE IF NOT EXISTS capacity.capacity_model_run (
  capacity_model_run_id VARCHAR,
  station_id VARCHAR,
  province_code VARCHAR,
  area_code VARCHAR,
  status VARCHAR,
  code VARCHAR,
  name VARCHAR,
  category VARCHAR,
  effective_from DATE,
  effective_to DATE,
  source_system VARCHAR,
  demand_mbps DOUBLE,
  available_mbps DOUBLE,
  utilization_pct DOUBLE,
  forecast_error_pct DOUBLE
);
