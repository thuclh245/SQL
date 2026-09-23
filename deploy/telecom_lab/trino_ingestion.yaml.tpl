# Nạp metadata từ Trino vào OpenMetadata — cổng G2.
# Chạy: /home/ubuntu/om-ingest/bin/metadata ingest -c <file này>
#
# Đọc bằng t2s_app (chỉ có quyền SELECT trong rules.json): ingestion chỉ cần
# đọc information_schema, không cần quyền ghi nào.
source:
  type: trino
  serviceName: telecom_lakehouse
  serviceConnection:
    config:
      type: Trino
      hostPort: localhost:8090
      username: t2s_app
      catalog: hive
  sourceConfig:
    config:
      type: DatabaseMetadata
      includeTables: true
      includeViews: false
      markDeletedTables: true
      schemaFilterPattern:
        excludes:
          # stg giữ bảng CSV thô trước khi CTAS; không phải tài sản dữ liệu.
          - ^stg$
          - ^information_schema$
          - ^default$
sink:
  type: metadata-rest
  config: {}
workflowConfig:
  loggerLevel: INFO
  openMetadataServerConfig:
    hostPort: http://localhost:8585/api
    authProvider: openmetadata
    securityConfig:
      jwtToken: __TOKEN__
