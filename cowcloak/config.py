from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = Field(alias="COWCLOAK_BASE_URL")
    session_secret: str = Field(alias="COWCLOAK_SESSION_SECRET", min_length=32)
    cookie_secure: bool = Field(default=True, alias="COWCLOAK_COOKIE_SECURE")
    trusted_hosts: str = Field(default="*", alias="COWCLOAK_TRUSTED_HOSTS")
    allowed_users: str = Field(default="", alias="COWCLOAK_ALLOWED_USERS")
    allowed_domains: str = Field(default="", alias="COWCLOAK_ALLOWED_DOMAINS")

    mailcow_url: str = Field(alias="MAILCOW_URL")
    mailcow_api_key: str = Field(alias="MAILCOW_API_KEY", min_length=1)
    mailcow_oauth_client_id: str = Field(alias="MAILCOW_OAUTH_CLIENT_ID", min_length=1)
    mailcow_oauth_client_secret: str = Field(alias="MAILCOW_OAUTH_CLIENT_SECRET", min_length=1)
    mailcow_verify_tls: bool = Field(default=True, alias="MAILCOW_VERIFY_TLS")

    @field_validator("base_url", "mailcow_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def oauth_callback_url(self) -> str:
        return f"{self.base_url}/oauth/callback"

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def allowed_user_list(self) -> list[str]:
        return [item.strip().lower() for item in self.allowed_users.split(",") if item.strip()]

    @property
    def allowed_domain_list(self) -> list[str]:
        return [
            item.strip().lower().lstrip("@")
            for item in self.allowed_domains.split(",")
            if item.strip().lstrip("@")
        ]

    def is_mailbox_allowed(self, email: str) -> bool:
        allowed_users = self.allowed_user_list
        allowed_domains = self.allowed_domain_list
        if not allowed_users and not allowed_domains:
            return True

        mailbox = email.strip().lower()
        if mailbox in allowed_users:
            return True
        if "@" not in mailbox:
            return False
        return mailbox.rsplit("@", 1)[1] in allowed_domains


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
