# Hive Standalone Metastore 4.1.0 + JDBC PostgreSQL + hadoop-aws.
#
# Image gốc apache/hive không kèm driver PostgreSQL, và cũng không kèm hadoop-aws,
# nên metastore không phân giải được đường dẫn s3a:// khi Trino đăng ký bảng.
# Phiên bản jar khớp Hadoop 3.4.1 có sẵn trong image (hadoop-aws 3.4.1 phụ thuộc
# software.amazon.awssdk:bundle:2.24.6 theo hadoop-project-3.4.1.pom).
FROM apache/hive:standalone-metastore-4.1.0

USER root

ARG POSTGRES_JDBC_VERSION=42.7.7
ARG HADOOP_AWS_VERSION=3.4.1
ARG AWS_SDK_BUNDLE_VERSION=2.24.6
ARG MAVEN_BASE=https://repo1.maven.org/maven2

RUN set -eux; \
    curl -fsSL -o /opt/hive/lib/postgresql-${POSTGRES_JDBC_VERSION}.jar \
      ${MAVEN_BASE}/org/postgresql/postgresql/${POSTGRES_JDBC_VERSION}/postgresql-${POSTGRES_JDBC_VERSION}.jar; \
    curl -fsSL -o /opt/hive/lib/hadoop-aws-${HADOOP_AWS_VERSION}.jar \
      ${MAVEN_BASE}/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar; \
    curl -fsSL -o /opt/hive/lib/aws-sdk-bundle-${AWS_SDK_BUNDLE_VERSION}.jar \
      ${MAVEN_BASE}/software/amazon/awssdk/bundle/${AWS_SDK_BUNDLE_VERSION}/bundle-${AWS_SDK_BUNDLE_VERSION}.jar

USER hive
