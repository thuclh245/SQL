"""Metadata Provider Factory.

Wires configured metadata sources into the appropriate `MetadataProviderPort`
implementation, guaranteeing strict fail-closed validation and zero implicit fallbacks.
"""

from t2s.catalog.metadata_provider import MetadataProviderPort
from t2s.catalog.openmetadata_provider import OpenMetadataProvider
from t2s.catalog.postgres_metadata_provider import PostgresMetadataProvider
from t2s.catalog.static_metadata_provider import StaticMetadataProvider
from t2s.configuration.settings import Settings
from t2s.errors.application_errors import ConfigurationError


class MetadataProviderFactory:
    """Instantiates metadata providers based on runtime settings."""

    @classmethod
    def create_provider(cls, settings: Settings) -> MetadataProviderPort:
        provider_name = settings.metadata_provider

        # Backward compatibility: if metadata_provider not set but static path is provided
        if provider_name is None:
            if settings.runtime_catalog_tables_path is not None:
                provider_name = "static"
            elif (
                settings.runtime_database_url is not None
                and settings.runtime_default_dialect == "postgres"
            ):
                provider_name = "postgres"
            else:
                raise ConfigurationError(
                    "No metadata provider configured. Set 'metadata_provider' or configure "
                    "'runtime_catalog_tables_path'."
                )

        clean_provider = provider_name.strip().lower()

        if clean_provider == "static":
            if settings.runtime_catalog_tables_path is None:
                raise ConfigurationError(
                    "runtime_catalog_tables_path is required when metadata_provider='static'."
                )
            return StaticMetadataProvider(
                catalog_tables_path=settings.runtime_catalog_tables_path,
                database_id=settings.runtime_catalog_database_id,
            )

        if clean_provider == "postgres":
            if settings.runtime_database_url is None:
                raise ConfigurationError(
                    "runtime_database_url is required when metadata_provider='postgres'."
                )
            return PostgresMetadataProvider(
                database_url=settings.runtime_database_url,
                service_name=getattr(settings, "metadata_service_name", "t2s"),
                connect_timeout_seconds=settings.runtime_database_connect_timeout_seconds,
                statement_timeout_seconds=settings.database_statement_timeout_seconds,
            )

        if clean_provider == "openmetadata":
            if not settings.openmetadata_url:
                raise ConfigurationError(
                    "openmetadata_url is required when metadata_provider='openmetadata'."
                )
            from t2s.integrations.openmetadata.openmetadata_client import OpenMetadataClient

            client = OpenMetadataClient(
                base_url=settings.openmetadata_url,
                auth_token=settings.openmetadata_auth_token,
                request_timeout_seconds=settings.openmetadata_request_timeout_seconds,
                max_retries=settings.openmetadata_max_retries,
                max_assets=settings.openmetadata_max_assets,
            )
            return OpenMetadataProvider(
                client=client,
                service_name=settings.openmetadata_service_name,
                pilot_fqns=settings.openmetadata_pilot_fqns,
            )

        raise ConfigurationError(
            f"Unsupported metadata provider '{provider_name}'. "
            "Supported providers: 'static', 'postgres', 'openmetadata'."
        )
