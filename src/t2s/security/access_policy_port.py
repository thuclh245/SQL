from typing import Protocol

from pydantic import BaseModel, field_validator

from t2s.security.user_identity import UserIdentity


class AuthorizedSqlResource(BaseModel):
    catalog_fqn: str
    sql_identifier: str

    @field_validator("catalog_fqn", "sql_identifier")
    @classmethod
    def validate_resource_identifier_is_not_empty(cls, resource_identifier: str) -> str:
        stripped_identifier = resource_identifier.strip()
        if not stripped_identifier:
            raise ValueError("Authorized SQL resource identifiers must not be empty.")
        return stripped_identifier


class AccessPolicyPort(Protocol):
    def get_authorized_resources(
        self, user_identity: UserIdentity
    ) -> list[AuthorizedSqlResource]: ...
