import os

os.environ.setdefault("COWCLOAK_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("COWCLOAK_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

from fastapi.testclient import TestClient

import cowcloak.main as main_module
from cowcloak.config import Settings
from cowcloak.mailcow import MailcowAccessDenied
from cowcloak.main import create_app


def settings() -> Settings:
    return Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        COWCLOAK_ACCESS_TAG="cowcloak",
        COWCLOAK_COOKIE_SECURE=False,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class DeniedMailcowClient:
    async def get_mailbox(self, email: str):
        raise MailcowAccessDenied("cowcloak")

    async def close(self) -> None:
        pass


class ToggleMailcowClient:
    def __init__(self) -> None:
        self.allowed = True
        self.mailbox_checks = 0

    async def get_mailbox(self, email: str):
        self.mailbox_checks += 1
        if not self.allowed:
            raise MailcowAccessDenied("cowcloak")
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": ["cowcloak"],
        }

    async def list_aliases(self):
        return []

    async def close(self) -> None:
        pass


def configure_oauth(monkeypatch) -> None:
    async def fake_exchange_code(_settings, _code):
        return {"email": "hidden@example.org"}

    monkeypatch.setattr(main_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(main_module, "validate_oauth_state", lambda _request, _state: None)


def test_oauth_access_denied_renders_cowcloak_html(monkeypatch):
    configure_oauth(monkeypatch)

    app = create_app(settings())
    with TestClient(app) as client:
        app.state.mailcow = DeniedMailcowClient()
        response = client.get(
            "/oauth/callback?code=test&state=test",
            headers={"Accept-Language": "de"},
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Kein Zugriff auf Cowcloak" in response.text
    assert "nicht für Cowcloak freigeschaltet" in response.text
    assert '"detail"' not in response.text


def test_existing_session_is_revoked_when_access_tag_is_removed(monkeypatch):
    configure_oauth(monkeypatch)
    mailcow = ToggleMailcowClient()
    app = create_app(settings())

    with TestClient(app) as client:
        app.state.mailcow = mailcow

        login_response = client.get(
            "/oauth/callback?code=test&state=test",
            follow_redirects=False,
        )
        assert login_response.status_code == 303
        assert login_response.headers["location"] == "/aliases"

        mailcow.allowed = False
        response = client.get(
            "/aliases",
            headers={"Accept-Language": "de"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Kein Zugriff auf Cowcloak" in response.text
        assert '"detail"' not in response.text

        start_response = client.get("/", follow_redirects=False)
        assert start_response.status_code == 200

    assert mailcow.mailbox_checks == 2
