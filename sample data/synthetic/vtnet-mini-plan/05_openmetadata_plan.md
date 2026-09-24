# OpenMetadata Integration Plan

## Bối Cảnh

OpenMetadata đã được cài sẵn trên VM. Vì vậy local v1 không cần dựng OM lại. Nhiệm vụ của local v1 là chuẩn bị metadata package đủ sạch để chuyển sang VM và ingest vào OM thật.

## Vai Trò Của OM Trong Dự Án

OM dùng làm metadata/search layer cho NL2SQL:

- Catalog service: `VTNet Datalake Presto`
- Database/catalog: `hive`, `hive_geo_old`, `mysql_datamon`, ...
- Schema/table/column metadata.
- Description tiếng Việt/Anh.
- Tags: sensitivity, PII, telecom domain.
- Glossary terms: throughput, IMSI, MSISDN, cell ID, CDR.
- Search/semantic search cho retrieval.

## Metadata Từ Excel OM

Các cột cần dùng từ Excel:

```text
name*
description
owner
tags
glossaryTerms
tiers
certification
retentionPeriod
sourceUrl
domains
entityType*
fullyQualifiedName
column.dataTypeDisplay
column.dataType
column.arrayDataType
column.dataLength
```

Entity types cần map:

```text
database
databaseSchema
table
column
```

## Metadata Package Local

Nên xuất ra các file:

```text
sample data/synthetic/vtnet-mini/om_ingest/
  README.md
  service.json
  databases.jsonl
  schemas.jsonl
  tables.jsonl
  columns.jsonl
  tags.jsonl
  glossary_terms.jsonl
  domains.jsonl
  owners.jsonl
  ingestion_manifest.json
  ingest_config_template.yaml
```

## Mapping Cơ Bản

| Excel OM | OpenMetadata concept |
| --- | --- |
| `fullyQualifiedName` | entity FQN |
| `entityType* = database` | Database |
| `entityType* = databaseSchema` | DatabaseSchema |
| `entityType* = table` | Table |
| `entityType* = column` | Column |
| `description` | description |
| `tags` | tag labels |
| `glossaryTerms` | glossary term labels |
| `column.dataType` | column data type |
| `owner` | owner reference nếu có |
| `domains` | domain reference nếu có |

## Tag Và Glossary Ưu Tiên

Từ Excel OM, nên giữ các tag/glossary phổ biến:

```text
Sensitivity-Level.L1-Public
Sensitivity-Level.L2-Internal
Sensitivity-Level.L3-Confidential
Sensitivity-Level.L4-Restricted
PII.NonSensitive
PII.Sensitive
Data-Category.CPNI
Data-Category.Location.Loc-Precise
Network Performance.Throughput
Network Performance.Handover
Network Performance.Drop Call Rate
Network Architecture.Cell ID
Subscriber & Customer.IMSI
Subscriber & Customer.MSISDN
Billing & Revenue.CDR
```

## Ingest Strategy Trên VM

Phase 1: Import metadata tối thiểu.

```text
database service
database/catalog
schema
table
column
description
```

Phase 2: Import governance metadata.

```text
tags
glossary terms
owners
domains
tiers
```

Phase 3: Validate search.

Test các query search:

```text
bad cell throughput 5g
dl_user_throughput_mbps
occean_cell
f_location_new
alarm SLA
FBB PPPoE session
data freshness
```

## Search Evaluation

Trước khi đưa NL2SQL vào, cần test retrieval:

| Query search | Kết quả mong muốn |
| --- | --- |
| `bad cell throughput 5g` | `hive.npms.kpi_access5g_5g_cell_peak_view` |
| `cell exclusion occean` | `hive.npms.occean_cell` |
| `province name location` | `hive.netbi.f_location_new` |
| `unresolved alarm SLA` | alarm/ticket/SLA tables |
| `FBB PPPoE session` | `hive.fbb.pppoe_session_daily/hourly` |
| `table freshness SLA` | `mysql_datamon.data_monitoring.table_freshness_daily` |

## Rủi Ro

| Rủi ro | Cách giảm |
| --- | --- |
| Description trong Excel có `[AI Gen]` và có thể noise | giữ nhưng thêm metadata curated cho bảng core |
| CSV import Excel từng bị lệch quote | parse bằng XML/structured parser, không dùng copy thủ công |
| OM search trả schema noisy | benchmark có required tables để debug retrieval |
| Tag/glossary format không khớp OM | normalize tag name trước khi ingest |
| Tên FQN có khoảng trắng `VTNet Datalake Presto` | thống nhất service name và database FQN mapping |

## Done Criteria

- OM có service `VTNet Datalake Presto` hoặc tên tương ứng.
- Search thấy đủ bảng core.
- Bảng/cột core có description.
- Tags/glossary hiển thị được.
- NL2SQL pipeline có thể retrieve metadata từ OM và chạy SQL local/VM.
