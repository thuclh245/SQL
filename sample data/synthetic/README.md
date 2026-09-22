# Bộ dữ liệu viễn thông tổng hợp

Bộ dữ liệu này dành cho thử nghiệm text-to-SQL và thiết kế benchmark. Nó **không phải dữ liệu sản xuất** và không xác nhận rằng các mã, ngưỡng KPI hay quy trình vận hành phản ánh chính xác hệ thống công ty. Dữ liệu được sinh cố định bằng seed `20260921`.

## Quy mô và cách dùng

- 20 schema, **400 bảng (20 bảng/schema)**, 49.033 dòng; mỗi bảng có 10–40 cột.
- 72 giờ từ `2026-08-18 00:00` đến `2026-08-20 23:00`, giờ Việt Nam (`UTC+07:00`).
- CSV: `generated/<schema>/<table>.csv`; mô tả schema: `generated/schema_catalog.json`; danh mục bảng, cột và khóa: `generated/catalog.json`; toàn bộ quan hệ: `generated/schema_relationships.json` và `generated/relationships_review.csv`; DDL Trino mang tính tham khảo: `generated/schema_trino.sql`.
- Đối chiếu 8 bảng gốc và danh sách bảng đã bỏ: [`SOURCE_AND_REVIEW.md`](SOURCE_AND_REVIEW.md). Kết quả kiểm tra: `generated/validation_report.json`.
- SQLite chạy ngay: `generated/telecom.sqlite`. Tên bảng SQLite dùng `schema__table`, ví dụ `ran_kpi__cell_hourly`.

Chạy lại:

```bash
python3 'sample data/synthetic/generate.py'
python3 'sample data/synthetic/validate.py'
```

## 20 schema

| Nhóm | Schema |
| --- | --- |
| Có trong tài liệu mẫu | `aaa`, `aam`, `acs` |
| Địa lý và hạ tầng | `geo`, `inventory`, `ran`, `ran_kpi`, `transport`, `core`, `energy`, `capacity` |
| Dịch vụ và khách hàng | `customer`, `product`, `service`, `qos`, `experience` |
| Vận hành và tài chính | `fault`, `ops`, `maintenance`, `billing` |

## Quan hệ chính

- `geo.country → geo.area → geo.province → geo.district → geo.ward → geo.village`; `geo.location → inventory.station → ran.cell → ran_kpi.cell_hourly`.
- `customer.subscriber → aaa.ftth_account_pppoe → aaa.authentication → aaa.accounting` theo `customer_id`, `account_id`, `session_id`.
- `customer.subscriber` và `product.plan` cùng nối tới `service.subscription`; `billing.invoice` dùng `customer_id`, `account_id`, `plan_id`.
- `acs.device_info → acs.f_uptime / acs.f_wifi` theo `device_id`; `acs.g_uptime` nối với thiết bị qua `ne_id` và được tổng hợp từ `f_uptime`.
- `fault.alarm → ops.ticket → maintenance.work_order → ops.technician_visit` theo `ticket_id`, `work_order_id`.
- Các bảng giờ dùng `date_hour` dạng `YYYY-MM-DD-HH`; các bảng ngày dùng `DATE`.

Các quan hệ là quy ước dữ liệu; Trino/Hive không cưỡng chế khóa ngoại. [`RELATIONSHIPS.md`](RELATIONSHIPS.md) có sơ đồ và các đường join chính. `catalog.json` ghi khóa chính, khóa ngoại và grain của từng bảng. Bảng KPI 5G 299 cột trong file mẫu được dùng làm nguồn cho `object_id` và phân bố lưu lượng ban đầu; bảng mới `ran_kpi.cell_hourly` tách thành các thước đo dễ truy vấn. Không suy diễn rằng KPI 299 cột có cùng công thức hoặc đơn vị với các KPI mới.

Trong 400 bảng, 29 bảng lõi có cấu trúc riêng; 371 bảng mở rộng là các chủ đề được khai báo tại `extended_tables.py`. Bảng mở rộng được chia thành danh mục, sự kiện và chỉ số; mỗi bảng có khóa chính riêng và khóa cha theo miền dữ liệu. Sáu bảng phân cấp địa lý có cột và quan hệ riêng. `origin` trong `catalog.json` phân biệt `provided_sample`, `synthetic_core` và `synthetic_extension`. Bảng có hậu tố `hourly` được sinh theo giờ, `daily` theo ngày, `monthly` theo tháng; lịch sử sự cố và công việc chỉ xuất hiện khi có sự kiện liên quan. Các bảng mở rộng **chưa phải bản sao của bảng thật trong công ty**.

## Dữ liệu nguồn và giả định

- `../sample_data_100_rows(1).csv` thực tế có **50** dòng, 299 cột. Có giá trị chuỗi `null`, số 0 ở nhiều KPI và một số `date_hour` không khớp `local_time`. Bộ sinh dùng `object_id` và `nr_ps_traffic_total_gb` làm điểm tựa; thời gian mới được tạo nhất quán.
- `../Query result 20-08-2026(1).csv` có **40** dòng. Toàn bộ giá trị KPI được đưa vào `aam.kpi_aam_daily_tdxl` với `source_system='provided_sample'`, giữ các cấp `province`, `area`, `network`. Mã tỉnh trống ở cấp tổng hợp được giữ trống. Danh mục `geo.location` chỉ gồm sáu tỉnh dùng trong phần dữ liệu tổng hợp, vì vậy **không** join toàn bộ snapshot nguồn với `geo.location` theo tỉnh.
- Tài liệu Markdown gốc mô tả 8 bảng/179 cột. Mô tả đầy đủ nằm trong `generated/source_metadata.json`; cột khớp và cột chưa đưa vào bảng thử nằm trong `generated/source_mapping.csv`. Markdown và CSV KPI địa bàn có danh sách cột khác nhau; [`SOURCE_AND_REVIEW.md`](SOURCE_AND_REVIEW.md) ghi rõ sự khác biệt này.
- Giá cước, địa điểm, số khách hàng, mã trạm, ngưỡng, phân bố sự cố, sự kiện đăng nhập và công thức KPI mới là giả định để tạo bài kiểm tra. Địa chỉ IP sử dụng dải dành cho ví dụ; tên khách hàng và số serial đều giả.
- Có hai đợt suy giảm cell được cài có chủ đích, liên kết đến cảnh báo, ticket, work order và complaint. Dữ liệu có giờ cao điểm, một số hóa đơn chưa thanh toán và ba lần đăng nhập thất bại.

## Giới hạn trước khi dùng tại công ty

Trước khi chạy trên hệ thống thật, cần đối chiếu tên bảng/cột với catalog công ty; xác nhận đơn vị đo và công thức KPI; ánh xạ đúng danh mục địa bàn, thiết bị và gói cước; kiểm tra chính sách dữ liệu của công ty. DDL tham khảo chưa có thuộc tính lưu trữ, phân vùng hay định dạng file cụ thể của một môi trường Hive/Trino. [Bộ benchmark 100 case](benchmark/README.md) đã có câu hỏi, SQL chuẩn và đáp án thực thi trên SQLite; SQL Trino chưa được kiểm chứng trên cụm công ty.
