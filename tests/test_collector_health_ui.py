from pathlib import Path
from types import SimpleNamespace

from moolias.config import Settings
from moolias.review_settings import get_collector_health

ROOT = Path(__file__).resolve().parents[1]


def settings(*, enabled: bool) -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_USAGE_STATS=enabled,
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
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_USAGE_STATS=True,
        MOOLIAS_USAGE_STALE_POLLS=5,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )
    assert custom.usage_stale_polls == 5


def test_collector_health_assets_keep_the_dashboard_compact():
    script = (ROOT / "moolias/static/collector-health.js").read_text()
    base = (ROOT / "moolias/templates/base.html").read_text()

    assert "Puffer niedrig" in script
    assert "mögliche Lücke" in script
    assert "low buffer" in script
    assert "possible gap" in script
    assert "History-Puffer" in script
    assert "History buffer" in script
    assert "History-Abruf" in script
    assert "History fetch" in script
    assert "3 Einträge geprüft · unverändert" in script
    assert "3 entries checked · unchanged" in script
    assert "history_buffer_percent" in script

    assert "Vorheriger Watermark" not in script
    assert "Previous watermark" not in script
    assert "Aktueller Watermark" not in script
    assert "Current watermark" not in script
    assert "Ältester Eintrag" not in script
    assert "Oldest entry" not in script
    assert "Neuester Eintrag" not in script
    assert "Newest entry" not in script
    assert "Dauer des letzten Laufs" not in script
    assert "Last collection duration" not in script
    assert "Veraltet nach" not in script
    assert "Stale after" not in script

    assert "/static/collector-health.js" in base
    assert "/static/collector-health.css" in base
