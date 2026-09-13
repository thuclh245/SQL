from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "t2s-api"
    environment: Literal["dev", "test", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    auth_issuer: str | None = None
    auth_audience: str | None = None
    state_postgres_url: str | None = None
    opensearch_url: str | None = None
    openmetadata_url: str | None = None
    vllm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model_name: str = "gpt-oss-120b"
    llm_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    llm_request_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_output_tokens: int = Field(default=2048, gt=0)
    database_statement_timeout_seconds: int = Field(default=30, gt=0)
    database_max_result_rows: int = Field(default=1000, gt=0)

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
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
