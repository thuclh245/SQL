from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "t2s"
    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None
    state_postgres_url: str | None = None
    opensearch_url: str | None = None
    openmetadata_url: str | None = None
    openmetadata_auth_token: str | None = None
    openmetadata_service_name: str = "openmetadata"
    openmetadata_request_timeout_seconds: float = Field(default=30.0, gt=0)
    openmetadata_max_assets: int = Field(default=25, gt=0)
    openmetadata_max_retries: int = Field(default=3, ge=0)
    openmetadata_pilot_fqns: list[str] | None = None
    # Derive sql_identifier as <database>.<schema>.<table> from the OpenMetadata FQN.
    # Required for engines addressed that way (Trino, Presto) unless every table
    # carries an explicit sqlIdentifier custom property.
    openmetadata_derive_sql_identifier_from_fqn: bool = False
    vllm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_provider: str = "openai_compatible"
    llm_model_name: str = "gpt-oss-120b"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    llm_request_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_output_tokens: int = Field(default=2048, gt=0)
    database_statement_timeout_seconds: int = Field(default=30, gt=0)
    database_max_result_rows: int = Field(default=1000, gt=0)
    runtime_sqlite_database_path: Path | None = None
    runtime_database_url: str | None = None
    runtime_database_connect_timeout_seconds: int = Field(default=10, gt=0)
    runtime_catalog_tables_path: Path | None = None
    # --- Trino lakehouse runtime ---
    # Base URL of the Trino coordinator, e.g. http://localhost:8090.
    trino_base_url: str | None = None
    # Trino user the application queries as. Trino's file-based access control is
    # the outermost read-only guard, so this user must hold SELECT only.
    trino_user: str = "t2s_app"
    trino_password: str | None = None
    trino_catalog: str = "hive"
    trino_schema: str | None = None
    trino_source: str = "t2s"
    trino_time_zone: str = "Asia/Ho_Chi_Minh"
    trino_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    runtime_catalog_database_id: str | None = None
    metadata_provider: str | None = None
    metadata_service_name: str = "t2s"
    runtime_prompt_directory: Path = Path("prompts/direct_sql")
    runtime_prompt_version: str = "v001"
    runtime_evidence_mode: Literal["none", "inline", "structured"] = "none"
    semantic_planner_mode: Literal["off", "deterministic", "llm"] = "off"
    result_verifier_enabled: bool = True
    # Startup guard against pointing the runtime at a schema-only database, where
    # every query succeeds and returns nothing.
    runtime_require_populated_execution_database: bool = True
    runtime_readiness_relation_sample_size: int = Field(default=25, gt=0)
    # Abstention posture. True lets a structurally sound candidate proceed with its
    # caveats attached; False blocks on any uncertainty the solver reports.
    release_candidates_with_caveats: bool = True
    # Value grounding: read candidate literals from the execution database so the
    # solver filters on observed values instead of guessing them.
    value_grounding_enabled: bool = False
    max_value_columns: int = Field(default=6, gt=0)
    max_value_candidates_per_column: int = Field(default=5, gt=0)
    value_lookup_timeout_ms: int = Field(default=1500, gt=0)
    enumerate_low_cardinality_domains: bool = True
    max_enumerated_domain_values: int = Field(default=12, gt=0)
    runtime_max_candidate_tables: int = Field(default=50, gt=0)
    runtime_max_hydrated_tables: int = Field(default=8, gt=0)
    runtime_max_columns_per_table: int = Field(default=12, gt=0)
    runtime_max_total_columns: int = Field(default=60, gt=0)
    runtime_max_relationships: int = Field(default=16, ge=0)
    runtime_relationship_expansion_mode: Literal[
        "conditional", "unconditional", "relationship_priority"
    ] = "conditional"
    runtime_fill_column_budget: bool = False
    runtime_small_db_threshold: int = Field(default=0, ge=0)
    runtime_max_escalations: int = Field(default=1, ge=0, le=3)
    runtime_default_dialect: Literal["postgres", "clickhouse", "starrocks", "sqlite", "trino"] = (
        "sqlite"
    )
    runtime_api_user_id: str = "api-user"
    validator_mode: Literal["disabled", "shadow", "enforce"] = Field(
        default="shadow",
        validation_alias=AliasChoices(
            "validator_mode",
            "sql_risk_validator_mode",
        ),
    )
    production_enforcement_authorized: bool = Field(
        default=False,
        description=(
            "Whether production enforcement of the semantic risk validator is authorized. "
            "Strictly False until certified on independent validation data."
        ),
        validation_alias=AliasChoices(
            "production_enforcement_authorized",
            "t2s_production_enforcement_authorized",
        ),
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.validator_mode == "enforce" and not self.production_enforcement_authorized:
            raise ValueError(
                "Production enforcement of semantic risk validator is not authorized "
                "(PRODUCTION_ENFORCEMENT_AUTHORIZED=False). Set validator_mode='shadow' "
                "or explicitly certify and set production_enforcement_authorized=True."
            )
        if self.environment in {"staging", "prod"}:
            missing_settings = [
                setting_name
                for setting_name, setting_value in {
                    "auth_issuer": self.auth_issuer,
                    "auth_audience": self.auth_audience,
                }.items()
                if not setting_value
            ]
            if missing_settings:
                joined_settings = ", ".join(missing_settings)
                raise ValueError(f"Missing security-critical settings: {joined_settings}")
        return self


@lru_cache
def load_application_settings() -> Settings:
    return Settings()
