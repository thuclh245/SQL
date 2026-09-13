from t2s.errors import UnauthorizedDataAccessError
from t2s.security.access_policy_port import AccessPolicyPort, AuthorizedSqlResource
from t2s.security.user_identity import UserIdentity


class AuthorizationService:
    def __init__(self, access_policy: AccessPolicyPort) -> None:
        self.access_policy = access_policy

    def get_authorized_resources(
        self,
        user_identity: UserIdentity,
    ) -> list[AuthorizedSqlResource]:
        return self.access_policy.get_authorized_resources(user_identity)

    def validate_sql_resource_access(
        self,
        user_identity: UserIdentity,
        referenced_sql_identifiers: set[str],
    ) -> None:
        authorized_resources = self.get_authorized_resources(user_identity)
        authorized_sql_identifiers = {
            self._normalize_sql_identifier(resource.sql_identifier)
            for resource in authorized_resources
        }
        unauthorized_identifiers = sorted(
            referenced_sql_identifier
            for referenced_sql_identifier in referenced_sql_identifiers
            if self._normalize_sql_identifier(referenced_sql_identifier)
            not in authorized_sql_identifiers
        )
        if unauthorized_identifiers:
            joined_identifiers = ", ".join(unauthorized_identifiers)
            raise UnauthorizedDataAccessError(
                f"SQL references unauthorized resources: {joined_identifiers}"
            )

    def _normalize_sql_identifier(self, sql_identifier: str) -> str:
        return sql_identifier.replace('"', "").replace("`", "").strip().lower()
