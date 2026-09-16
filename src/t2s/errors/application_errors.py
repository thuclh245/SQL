class T2SError(Exception):
    error_code = "t2s_error"


class ApplicationError(T2SError):
    error_code = "application_error"


class ConfigurationError(ApplicationError):
    error_code = "configuration_error"


class QueryValidationError(ApplicationError):
    error_code = "query_validation_error"


class MetadataCatalogError(ApplicationError):
    error_code = "metadata_catalog_error"


class MetadataNotFoundError(MetadataCatalogError):
    error_code = "metadata_not_found"


class MetadataSyncError(MetadataCatalogError):
    error_code = "metadata_sync_error"


class MetadataMappingError(MetadataCatalogError):
    error_code = "metadata_mapping_error"


class MetadataAuthenticationError(MetadataCatalogError):
    error_code = "metadata_authentication_error"


class MetadataPermissionError(MetadataCatalogError):
    error_code = "metadata_permission_error"


class MetadataEntityNotFoundError(MetadataCatalogError):
    error_code = "metadata_entity_not_found"


class MetadataCardinalityLimitExceededError(MetadataCatalogError):
    error_code = "metadata_cardinality_limit_exceeded"


class UnauthorizedDataAccessError(ApplicationError):
    error_code = "unauthorized_data_access"


class UnsafeSqlError(ApplicationError):
    error_code = "unsafe_sql"


class SqlExplainError(ApplicationError):
    error_code = "sql_explain_error"


class QueryExecutionError(ApplicationError):
    error_code = "query_execution_error"


class QueryExecutionTimeoutError(QueryExecutionError):
    error_code = "query_execution_timeout"


class BenchmarkDatabaseIntegrityError(ApplicationError):
    error_code = "benchmark_database_integrity_error"


class SolverError(ApplicationError):
    error_code = "solver_error"


class UnsupportedSqlDialectError(SolverError):
    error_code = "unsupported_sql_dialect"


class EmptySqlCandidateError(SolverError):
    error_code = "empty_sql_candidate"


class MalformedSolverOutputError(SolverError):
    error_code = "malformed_solver_output"


class SolverDependencyError(SolverError):
    error_code = "solver_dependency_error"
