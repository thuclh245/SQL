from t2s.security.authorization_service import AuthorizationService
from t2s.security.user_identity import UserIdentity
from t2s.verification.sql_ast_parser import ParsedSql


class SqlAccessValidator:
    def __init__(self, authorization_service: AuthorizationService) -> None:
        self.authorization_service = authorization_service

    def validate_table_access(
        self,
        user_identity: UserIdentity,
        parsed_sql: ParsedSql,
    ) -> None:
        self.authorization_service.validate_sql_resource_access(
            user_identity=user_identity,
            referenced_sql_identifiers=parsed_sql.referenced_table_identifiers(),
        )
