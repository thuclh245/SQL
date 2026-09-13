import pytest

from t2s.errors import UnauthorizedDataAccessError
from t2s.security import AuthorizationService, AuthorizedSqlResource, UserIdentity


class StaticAccessPolicy:
    def get_authorized_resources(self, user_identity: UserIdentity) -> list[AuthorizedSqlResource]:
        return [
            AuthorizedSqlResource(
                catalog_fqn="warehouse.analytics.customers",
                sql_identifier="analytics.customers",
            )
        ]


def test_authorization_uses_executable_identifier_not_catalog_fqn() -> None:
    authorization_service = AuthorizationService(StaticAccessPolicy())

    authorization_service.validate_sql_resource_access(
        user_identity=UserIdentity(user_id="analyst"),
        referenced_sql_identifiers={"analytics.customers"},
    )


def test_authorization_blocks_catalog_fqn_substitution() -> None:
    authorization_service = AuthorizationService(StaticAccessPolicy())

    with pytest.raises(UnauthorizedDataAccessError):
        authorization_service.validate_sql_resource_access(
            user_identity=UserIdentity(user_id="analyst"),
            referenced_sql_identifiers={"warehouse.analytics.customers"},
        )
