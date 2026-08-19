import os

os.environ.setdefault("COWCLOAK_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("COWCLOAK_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

from fastapi.testclient import TestClient

from cowcloak.config import Settings
from cowcloak.main import create_app
from cowcloak.stats import StatsStore, UsageEvent


def settings(db_path: str, *, enabled: bool = False) -> Settings:
    return Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        COWCLOAK_USAGE_STATS=enabled,
        COWCLOAK_USAGE_DB_PATH=db_path,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def test_disabled_stats_do_not_create_database(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    app = create_app(settings(str(db_path)))

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert not db_path.exists()


async def test_stats_store_deduplicates_received_events(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    store = StatsStore(str(db_path))
    await store.initialize()
    started_at = await store.tracking_started_at()

    event = UsageEvent(
        event_key="received-1",
        mailbox="user@example.org",
        alias="shop@example.org",
        event_at=started_at + 1,
    )
    newer = UsageEvent(
        event_key="received-2",
        mailbox="user@example.org",
        alias="shop@example.org",
        event_at=started_at + 2,
    )

    assert await store.record_received([event, event]) == 1
    assert await store.record_received([event, newer]) == 1

    usage = await store.alias_usage("user@example.org", ["shop@example.org"])
    assert usage["shop@example.org"].received_count == 2
    assert usage["shop@example.org"].sent_count == 0
    assert usage["shop@example.org"].last_received_at == started_at + 2
    assert usage["shop@example.org"].last_sent_at is None


async def test_stats_store_deduplicates_sent_events_on_existing_alias_row(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    store = StatsStore(str(db_path))
    await store.initialize()
    started_at = await store.tracking_started_at()

    received = UsageEvent(
        event_key="received-1",
        mailbox="user@example.org",
        alias="shop@example.org",
        event_at=started_at + 1,
    )
    sent = UsageEvent(
        event_key="sent-1",
        mailbox="user@example.org",
        alias="shop@example.org",
        event_at=started_at + 2,
    )
    newer = UsageEvent(
        event_key="sent-2",
        mailbox="user@example.org",
        alias="shop@example.org",
        event_at=started_at + 3,
    )

    assert await store.record_received([received]) == 1
    assert await store.record_sent([sent, sent]) == 1
    assert await store.record_sent([sent, newer]) == 1

    usage = await store.alias_usage("user@example.org", ["shop@example.org"])
    assert usage["shop@example.org"].received_count == 1
    assert usage["shop@example.org"].sent_count == 2
    assert usage["shop@example.org"].last_received_at == started_at + 1
    assert usage["shop@example.org"].last_sent_at == started_at + 3
