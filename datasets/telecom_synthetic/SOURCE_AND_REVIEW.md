# Đối chiếu nguồn và kết quả rà soát

Bộ dữ liệu nguồn gồm Markdown mô tả 3 schema, 8 bảng và 179 cột; CSV KPI cell có 50 dòng × 299 cột; CSV KPI địa bàn có 40 dòng × 8 cột. `query.md` rỗng. Mô tả gốc có nhãn `[AI Gen]`, nên cần xác nhận với catalog công ty trước khi coi là định nghĩa chính thức.

**Điểm không nhất quán trong nguồn:** mô tả `acs.f_wifi` nói chưa xác định được cột nhưng cùng file lại liệt kê 50 cột. Danh sách 8 cột của `aam.kpi_aam_daily_tdxl` trong Markdown cũng khác 8 cột của CSV KPI địa bàn. Bảng thử giữ cột cần thiết từ cả hai nguồn và chuẩn hóa chuỗi `null`/ô trống; CSV gốc không bị sửa.

## Tám bảng trong tài liệu gốc

### `aaa.ftth_account_pppoe`

[AI Gen] Bảng lưu trữ dữ liệu tài khoản FTTH sử dụng kết nối PPPoE trong hệ thống VTNet Datalake, truy cập qua Presto/Hive. Bảng này chứa các thông tin chi tiết về người dùng, nhóm dịch vụ, các giới hạn đăng nhập, số lượng kết nối và thời gian ghi nhận, phục vụ cho việc phân tích, giám sát và báo cáo hoạt động mạng cáp quang.

Cột nguồn: **6**; cột trong bảng thử: **17**; tên cột giữ nguyên: **6**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

### `aaa.authentication`

[AI Gen] Bảng lưu trữ dữ liệu xác thực người dùng trên hệ thống VTNet Datalake, được tạo trong Presto Hive. Mỗi bản ghi đại diện cho một khung thời gian (định dạng giờ-ngày) và cung cấp thống kê chi tiết về các yêu cầu, phản hồi, lỗi và các chỉ số hiệu suất liên quan đến quá trình xác thực.

Cột nguồn: **27**; cột trong bảng thử: **40**; tên cột giữ nguyên: **27**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

### `aaa.accounting`

[AI Gen] Bảng `VTNet Datalake Presto.hive.aaa.accounting` lưu trữ dữ liệu ghi nhận (accounting) các phiên hoạt động của hệ thống AAA (Authentication, Authorization, Accounting). Mỗi bản ghi mô tả chi tiết thời gian, máy chủ, địa chỉ IP, các thông số tốc độ và thống kê lỗi, retry, trạng thái trong một khoảng thời gian nhất định, phục vụ cho việc phân tích hiệu suất, phát hiện sự cố và lập báo cáo tài chính mạng.

Cột nguồn: **29**; cột trong bảng thử: **40**; tên cột giữ nguyên: **29**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

### `aam.kpi_aam_daily_tdxl`

[AI Gen] Bảng này lưu trữ các chỉ số KPI (Key Performance Indicator) hàng ngày của hệ thống AAM (Advanced Analytics Module) trên nền tảng VTNet Datalake, được truy vấn qua Presto. Mỗi bản ghi đại diện cho một KPI tại một thời điểm nhất định, bao gồm thông tin về khu vực, cấp độ vị trí và các giá trị đo lường liên quan.

Cột nguồn: **8**; cột trong bảng thử: **20**; tên cột giữ nguyên: **8**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

### `aam.kpi_aam_daily_tlgd`

[AI Gen] Bảng này lưu trữ dữ liệu KPI hằng ngày của hệ thống AAM (Advanced Analytics Module) tại VTNet, được tổng hợp trên mức giờ (hourly) và phân vùng theo quốc gia, cấp độ vị trí. Dữ liệu được dùng cho việc theo dõi hiệu suất, phân tích xu hướng và báo cáo KPI cho các nhóm kinh doanh và vận hành.

Cột nguồn: **9**; cột trong bảng thử: **19**; tên cột giữ nguyên: **9**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

### `acs.f_uptime`

[AI Gen] Bảng lưu trữ dữ liệu uptime của các thiết bị mạng trong hệ thống VTNet, được thu thập từ các thiết bị ACS và đưa vào Datalake qua Presto. Dữ liệu bao gồm thời gian ghi nhận, thời gian hoạt động, trạng thái kết nối và các thông tin định danh thiết bị, hỗ trợ phân tích hiệu suất và khả năng sẵn sàng của mạng.

Cột nguồn: **40**; cột trong bảng thử: **40**; tên cột giữ nguyên: **32**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

### `acs.g_uptime`

[AI Gen] Bảng này lưu trữ thông tin thời gian hoạt động (uptime) của các thiết bị mạng (NE) theo từng giờ, được thu thập từ hệ thống VTNet Datalake qua Presto. Dữ liệu bao gồm thời gian ghi nhận, thời gian hoạt động tổng cộng, thời gian hoạt động của WAN PPP và các biến thể độ chênh lệch, hỗ trợ phân tích hiệu suất mạng và phát hiện sự cố.

Cột nguồn: **10**; cột trong bảng thử: **10**; tên cột giữ nguyên: **10**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

### `acs.f_wifi`

[AI Gen] Bảng VTNet Datalake Presto.hive.acs.f_wifi chứa dữ liệu mạng không dây (Wi‑Fi) thu thập từ hệ thống ACS, dùng cho phân tích hiệu suất và giám sát. Do thiếu thông tin cấu trúc, các cột hiện không được xác định.

Cột nguồn: **50**; cột trong bảng thử: **40**; tên cột giữ nguyên: **26**. Xem `generated/source_mapping.csv` để biết cột nào được thêm hoặc chưa đưa vào bảng thử.

## Bảng được bỏ sau rà soát

Các bảng sau từng có trong bản tổng hợp, nhưng trùng vai trò với bảng được giữ hoặc không đủ căn cứ từ mẫu. Mỗi schema vẫn có đúng 20 bảng.

| Schema | Bảng bỏ | Lý do |
| --- | --- | --- |
| `aaa` | `radius_response_hourly` | derived from request and outcome counts |
| `aaa` | `radius_retry_hourly` | retry_count is already in authentication |
| `aaa` | `pppoe_disconnect_hourly` | accounting.stop_time covers disconnects |
| `aaa` | `realm_route` | no independent source mapping |
| `aam` | `kpi_dashboard_usage` | application audit outside KPI source |
| `aam` | `kpi_export_history` | application audit outside KPI source |
| `acs` | `ne_info` | overlaps device_info |
| `acs` | `wifi_radio_hourly` | overlaps f_wifi |
| `acs` | `device_temperature_hourly` | temperature already in f_uptime |
| `acs` | `lan_port_hourly` | port-level detail is retained in lan_port |
| `geo` | `postal_zone` | not supported by the supplied geography |
| `inventory` | `equipment_slot` | rack and card retain the hierarchy |
| `inventory` | `feeder` | cable_segment covers this fixture |
| `ran` | `interference_relation` | not supported by the sample KPIs |
| `ran_kpi` | `cell_energy_hourly` | energy.station_hourly covers energy |
| `transport` | `link_utilization_daily` | derivable from link_hourly |
| `core` | `core_cpu_hourly` | cpu_pct already in gateway_hourly |
| `qos` | `availability_hourly` | availability_pct already in service_hourly |
| `ops` | `repair_result` | ticket resolution_code captures outcome |
| `ops` | `incident_bridge` | no independent source evidence |
| `customer` | `customer_profile` | subscriber contains core profile |
| `product` | `price_comparison` | derivable from plan and price history |
| `billing` | `aging_daily` | derivable from overdue_balance |
| `billing` | `debit_note` | no independent source evidence |
| `service` | `service_usage_daily` | derivable from service_usage_hourly |
| `experience` | `speed_test_daily` | derivable from speed_test |
| `energy` | `energy_budget_daily` | budget_daily retained in billing |
| `capacity` | `demand_monthly` | derivable from demand_daily |

## Cách kiểm chứng

- `generated/source_metadata.json` lưu nguyên mô tả của 3 schema, 8 bảng và 179 cột từ Markdown gốc.
- `generated/source_mapping.csv` so tên cột nguồn và bảng thử; `acs.f_wifi` gốc có 50 cột nên bảng thử giữ tối đa 40 cột theo giới hạn đã yêu cầu.
- `generated/validation_report.json` ghi số bảng, số dòng, quan hệ và các kiểm tra đạt.
- Các bảng còn lại là giả định để làm dữ liệu thử. Không thể chứng minh chúng trùng cấu trúc hệ thống công ty chỉ từ những file mẫu hiện có.
