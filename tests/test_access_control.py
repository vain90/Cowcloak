from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from cowcloak.config import Settings
from cowcloak.security import require_user


def settings(**overrides) -> Settings:
    values = {
        "COWCLOAK_BASE_URL": "https://aliases.example.org",
        "COWCLOAK_SESSION_SECRET": "x" * 64,
        "COWCLOAK_COOKIE_SECURE": False,
        "MAILCOW_URL": "https://mail.example.org",
        "MAILCOW_API_KEY": "secret",
        "MAILCOW_OAUTH_CLIENT_ID": "client",
        "MAILCOW_OAUTH_CLIENT_SECRET": "oauth-secret",
    }
    values.update(overrides)
    return Settings(**values)


def request_with_user(config: Settings, email: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/aliases",
        "headers": [],
        "app": SimpleNamespace(state=SimpleNamespace(settings=config)),
        "session": {"user_email": email, "csrf_token": "token"},
    }
    return Request(scope)


def test_empty_access_lists_allow_all_mailboxes() -> None:
    config = settings()

    assert config.is_mailbox_allowed("alice@example.org")
    assert config.is_mailbox_allowed("bob@another.example")


def test_exact_mailbox_allowlist_is_case_insensitive() -> None:
    config = settings(COWCLOAK_ALLOWED_USERS=" Alice@Example.org , bob@example.net ")

    assert config.is_mailbox_allowed("alice@example.org")
    assert config.is_mailbox_allowed("BOB@EXAMPLE.NET")
    assert not config.is_mailbox_allowed("carol@example.org")


def test_domain_allowlist_accepts_optional_at_prefix() -> None:
    config = settings(COWCLOAK_ALLOWED_DOMAINS="example.org,@example.net")

    assert config.is_mailbox_allowed("alice@example.org")
    assert config.is_mailbox_allowed("bob@example.net")
    assert not config.is_mailbox_allowed("carol@example.com")


def test_user_or_domain_match_grants_access() -> None:
    config = settings(
        COWCLOAK_ALLOWED_USERS="special@other.example",
        COWCLOAK_ALLOWED_DOMAINS="example.org",
    )

    assert config.is_mailbox_allowed("alice@example.org")
    assert config.is_mailbox_allowed("special@other.example")
    assert not config.is_mailbox_allowed("blocked@other.example")


def test_require_user_clears_disallowed_existing_session() -> None:
    request = request_with_user(
        settings(COWCLOAK_ALLOWED_USERS="allowed@example.org"),
        "blocked@example.org",
    )

    with pytest.raises(HTTPException) as exc_info:
        require_user(request)

    assert exc_info.value.status_code == 403
    assert request.session == {}
