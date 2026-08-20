import os

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

from fastapi.testclient import TestClient

from moolias.config import Settings
from moolias.main import create_app


def settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def test_expired_html_session_redirects_to_login_page():
    app = create_app(settings())

    with TestClient(app) as client:
        response = client.get(
            "/aliases",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert '"detail"' not in response.text


def test_expired_api_session_keeps_json_401():
    app = create_app(settings())

    with TestClient(app) as client:
        response = client.get(
            "/aliases/review-settings",
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
