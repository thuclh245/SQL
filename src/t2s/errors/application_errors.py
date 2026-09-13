class T2SError(Exception):
    error_code = "t2s_error"


class ApplicationError(T2SError):
    error_code = "application_error"


class ConfigurationError(ApplicationError):
    error_code = "configuration_error"


class QueryValidationError(ApplicationError):
    error_code = "query_validation_error"


class UnauthorizedDataAccessError(ApplicationError):
    error_code = "unauthorized_data_access"


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
