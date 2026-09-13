import pytest
from pydantic import ValidationError

from t2s.configuration import Settings


def test_production_settings_require_trusted_auth_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="prod")


def test_development_settings_can_load_without_trusted_auth_configuration() -> None:
    settings = Settings(environment="dev")

    assert settings.environment == "dev"


def test_dependency_url_settings_are_clearly_named() -> None:
    settings = Settings(
        environment="dev",
        state_postgres_url="postgresql://t2s:secret@localhost:5432/t2s",
        opensearch_url="http://localhost:9200",
        openmetadata_url="https://openmetadata.example.internal/api",
        vllm_base_url="http://vllm.example.internal/v1",
    )

    assert settings.state_postgres_url is not None
    assert settings.opensearch_url == "http://localhost:9200"
    assert settings.openmetadata_url is not None
    assert settings.vllm_base_url == "http://vllm.example.internal/v1"


def test_dependency_url_settings_support_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STATE_POSTGRES_URL", "postgresql://localhost/t2s")
    monkeypatch.setenv("OPENSEARCH_URL", "http://localhost:9200")
    monkeypatch.setenv("OPENMETADATA_URL", "https://openmetadata.example/api")
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.example/v1")

    settings = Settings(environment="dev")

    assert settings.state_postgres_url == "postgresql://localhost/t2s"
    assert settings.opensearch_url == "http://localhost:9200"
    assert settings.openmetadata_url == "https://openmetadata.example/api"
    assert settings.vllm_base_url == "http://vllm.example/v1"
