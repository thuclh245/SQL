from pydantic import BaseModel, Field, field_validator


class UserIdentity(BaseModel):
    user_id: str
    tenant_id: str | None = None
    roles: frozenset[str] = Field(default_factory=frozenset)
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("user_id")
    @classmethod
    def validate_user_id_is_not_empty(cls, user_id: str) -> str:
        stripped_user_id = user_id.strip()
        if not stripped_user_id:
            raise ValueError("User identity user_id must not be empty.")
        return stripped_user_id
