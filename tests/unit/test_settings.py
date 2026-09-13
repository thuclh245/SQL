import pytest
from pydantic import ValidationError

from t2s.configuration import Settings


def test_production_settings_require_trusted_auth_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="prod")


def test_development_settings_can_load_without_trusted_auth_configuration() -> None:
    settings = Settings(environment="dev")

    assert settings.environment == "dev"
