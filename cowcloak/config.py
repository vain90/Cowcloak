from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = Field(alias="COWCLOAK_BASE_URL")
    session_secret: str = Field(alias="COWCLOAK_SESSION_SECRET", min_length=32)
    wordlist: str = Field(default="en", alias="COWCLOAK_WORDLIST")
    cookie_secure: bool = Field(default=True, alias="COWCLOAK_COOKIE_SECURE")
    trusted_hosts: str = Field(default="*", alias="COWCLOAK_TRUSTED_HOSTS")

    mailcow_url: str = Field(alias="MAILCOW_URL")
    mailcow_api_key: str = Field(alias="MAILCOW_API_KEY", min_length=1)
    mailcow_oauth_client_id: str = Field(alias="MAILCOW_OAUTH_CLIENT_ID", min_length=1)
    mailcow_oauth_client_secret: str = Field(alias="MAILCOW_OAUTH_CLIENT_SECRET", min_length=1)
    mailcow_verify_tls: bool = Field(default=True, alias="MAILCOW_VERIFY_TLS")

    @field_validator("base_url", "mailcow_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("wordlist")
    @classmethod
    def validate_wordlist(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"de", "en"}:
            raise ValueError("COWCLOAK_WORDLIST must be 'de' or 'en'")
        return value

    @property
    def oauth_callback_url(self) -> str:
        return f"{self.base_url}/oauth/callback"

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
