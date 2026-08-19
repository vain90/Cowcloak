from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = Field(alias="COWCLOAK_BASE_URL")
    session_secret: str = Field(alias="COWCLOAK_SESSION_SECRET", min_length=32)
    cookie_secure: bool = Field(default=True, alias="COWCLOAK_COOKIE_SECURE")
    trusted_hosts: str = Field(default="*", alias="COWCLOAK_TRUSTED_HOSTS")
    access_tag: str = Field(default="", alias="COWCLOAK_ACCESS_TAG")

    usage_stats: bool = Field(default=False, alias="COWCLOAK_USAGE_STATS")
    usage_tag: str = Field(default="cowcloak-stats", alias="COWCLOAK_USAGE_TAG")
    usage_db_path: str = Field(
        default="/data/cowcloak-stats.sqlite3",
        alias="COWCLOAK_USAGE_DB_PATH",
    )
    usage_poll_seconds: int = Field(
        default=60,
        ge=15,
        le=3600,
        alias="COWCLOAK_USAGE_POLL_SECONDS",
    )
    usage_history_count: int = Field(
        default=1000,
        ge=100,
        le=10000,
        alias="COWCLOAK_USAGE_HISTORY_COUNT",
    )

    mailcow_url: str = Field(alias="MAILCOW_URL")
    mailcow_api_key: str = Field(alias="MAILCOW_API_KEY", min_length=1)
    mailcow_oauth_client_id: str = Field(alias="MAILCOW_OAUTH_CLIENT_ID", min_length=1)
    mailcow_oauth_client_secret: str = Field(alias="MAILCOW_OAUTH_CLIENT_SECRET", min_length=1)
    mailcow_verify_tls: bool = Field(default=True, alias="MAILCOW_VERIFY_TLS")

    @field_validator("base_url", "mailcow_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("access_tag", "usage_tag", "usage_db_path")
    @classmethod
    def strip_optional_value(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_usage_settings(self) -> "Settings":
        if self.usage_stats and not self.usage_tag:
            raise ValueError("COWCLOAK_USAGE_TAG must be set when usage statistics are enabled")
        if self.usage_stats and not self.usage_db_path:
            raise ValueError("COWCLOAK_USAGE_DB_PATH must be set when usage statistics are enabled")
        return self

    @property
    def oauth_callback_url(self) -> str:
        return f"{self.base_url}/oauth/callback"

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
