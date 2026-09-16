"""Unit tests for MetadataProviderFactory."""

from pathlib import Path

import pytest

from t2s.catalog.metadata_provider_factory import MetadataProviderFactory
from t2s.catalog.postgres_metadata_provider import PostgresMetadataProvider
from t2s.catalog.static_metadata_provider import StaticMetadataProvider
from t2s.configuration.settings import Settings
from t2s.errors.application_errors import ConfigurationError


def test_factory_creates_static_provider_explicit(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text("[]", encoding="utf-8")
    settings = Settings(
        metadata_provider="static",
        runtime_catalog_tables_path=catalog_path,
    )
    provider = MetadataProviderFactory.create_provider(settings)
    assert isinstance(provider, StaticMetadataProvider)
    assert provider.source_system == "static"


def test_factory_creates_postgres_provider_explicit() -> None:
    settings = Settings(
        metadata_provider="postgres",
        runtime_database_url="postgresql://user:pass@localhost:5432/testdb",
        metadata_service_name="custom_svc",
    )
    provider = MetadataProviderFactory.create_provider(settings)
    assert isinstance(provider, PostgresMetadataProvider)
    assert provider.source_system == "postgresql"
    assert provider.service_name == "custom_svc"


def test_factory_backward_compatibility_defaults_to_static_when_path_set(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text("[]", encoding="utf-8")
    settings = Settings(
        runtime_catalog_tables_path=catalog_path,
    )
    provider = MetadataProviderFactory.create_provider(settings)
    assert isinstance(provider, StaticMetadataProvider)


def test_factory_missing_static_path_raises_configuration_error() -> None:
    settings = Settings(metadata_provider="static")
    with pytest.raises(ConfigurationError, match="runtime_catalog_tables_path is required"):
        MetadataProviderFactory.create_provider(settings)


def test_factory_missing_postgres_url_raises_configuration_error() -> None:
    settings = Settings(metadata_provider="postgres")
    with pytest.raises(ConfigurationError, match="runtime_database_url is required"):
        MetadataProviderFactory.create_provider(settings)


def test_factory_unsupported_provider_raises_configuration_error() -> None:
    settings = Settings(metadata_provider="openmetadata")
    with pytest.raises(ConfigurationError, match="Unsupported metadata provider 'openmetadata'"):
        MetadataProviderFactory.create_provider(settings)


def test_factory_unconfigured_raises_configuration_error() -> None:
    settings = Settings()
    with pytest.raises(ConfigurationError, match="No metadata provider configured"):
        MetadataProviderFactory.create_provider(settings)
