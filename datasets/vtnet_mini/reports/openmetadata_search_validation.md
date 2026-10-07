# OpenMetadata Search Retrieval Validation Report

**Ngày tạo**: 2026-09-23 20:18:20
**Target System**: OpenMetadata v1.4.x / Search Cluster (OpenSearch/Elasticsearch)
**Số lượng bảng đã lập chỉ mục**: 148
**Số lượng cột đã lập chỉ mục**: 5864

## 1. Tóm Tắt Độ Chính Xác Retrieval

- **Top-1 Accuracy**: 83.3% (5/6)
- **Top-3 Accuracy**: 83.3% (5/6)
- **Top-5 Accuracy**: 100.0% (6/6)

## 2. Chi Tiết Kết Quả Kiểm Tra Theo Câu Hỏi

| STT | Domain | Query Search | Bảng Mong Muốn | Rank Kết Quả | Top 1 Trả Về |
|---|---|---|---|---|---|
| 1 | Network KPI 5G | `bad cell throughput 5g` | `kpi_access5g_5g_cell_peak_view` | **Rank 1** | `kpi_access5g_5g_cell_peak_view` |
| 2 | Network Cell Exclusion | `cell exclusion occean` | `occean_cell` | **Rank 1** | `occean_cell` |
| 3 | Common Location | `danh mục tỉnh thành location province area` | `f_location_new` | **Rank 1** | `f_location_new` |
| 4 | Alarm / GNOC | `alarm SLA GNOC department tickets` | `gnoc` | **Rank 4** | `cat_department` |
| 5 | Fixed Broadband (FBB) | `FBB PPPoE session subscriber FTTH` | `ftth_account_pppoe` | **Rank 1** | `ftth_account_pppoe` |
| 6 | Data Governance / Monitoring | `kqi alarm monitoring quality performance` | `kqi_alarm` | **Rank 1** | `kqi_alarm` |

## 3. Phân Tích & Đánh Giá Trap Cases

### Trap 1: `f_location` vs `f_location_new`
- **Hiện tượng**: Trong metadata tồn tại cả `f_location` cũ và `f_location_new` mới.
- **Kết quả**: Truy vấn địa bàn có chứa keyword `area code` hoặc `location new` giúp OM đẩy `f_location_new` lên vị trí Rank 1 nhờ glossary term `common_location`.

### Trap 2: `occean_cell` vs Các bảng Cell khác
- **Hiện tượng**: Bảng `occean_cell` là bảng phụ trợ blacklist cell biển/đảo.
- **Kết quả**: Truy vấn tìm cell exclusion đạt Rank 1 chính xác nhờ description và tag `Data-Category.Location.Loc-Precise`.

## 4. Hướng Dẫn Cấu Hình API NL2SQL Trên VM

Để hệ thống NL2SQL tích hợp với OpenMetadata trên VM, cấu hình endpoint như sau:
```yaml
openmetadata:
  host_port: 'http://<VM_IP>:8585'
  api_version: 'v1'
  jwt_token: '${OPENMETADATA_JWT_TOKEN}'
  search_endpoint: '/api/v1/search/query'
  index: 'table_search_index'
  query_params:
    size: 5
    fields: 'name,displayName,description,columns,tags,glossaryTerms'
```

