from pathlib import Path
from types import SimpleNamespace

from cowcloak.config import Settings
from cowcloak.review_settings import get_collector_health

ROOT = Path(__file__).resolve().parents[1]


def settings(*, enabled: bool) -> Settings:
    return Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        COWCLOAK_USAGE_STATS=enabled,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


async def test_statistics_off_returns_disabled_collector_health():
    request = SimpleNamespace(
        session={"user_email": "user@example.org"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings(enabled=False),
                stats_store=None,
            )
        ),
    )

    payload = await get_collector_health(request)

    assert payload == {"enabled": False, "state": "off"}


def test_stale_poll_default_is_three_and_configurable():
    assert settings(enabled=True).usage_stale_polls == 3

    custom = Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        COWCLOAK_USAGE_STATS=True,
        COWCLOAK_USAGE_STALE_POLLS=5,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )
    assert custom.usage_stale_polls == 5


def test_collector_health_assets_cover_german_and_english_ui():
    script = (ROOT / "cowcloak/static/collector-health.js").read_text()
    base = (ROOT / "cowcloak/templates/base.html").read_text()

    assert "Puffer niedrig" in script
    assert "mögliche Lücke" in script
    assert "low headroom" in script
    assert "possible gap" in script
    assert "not CPU or server utilization" in script
    assert "/static/collector-health.js" in base
    assert "/static/collector-health.css" in base
