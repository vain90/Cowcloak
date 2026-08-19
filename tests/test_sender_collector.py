import pytest

from cowcloak.aliases import AliasRecord
from cowcloak.config import Settings
from cowcloak.stats import StatsStore
from cowcloak.usage import UsageCollector


def settings(db_path: str) -> Settings:
    return Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        COWCLOAK_USAGE_STATS=True,
        COWCLOAK_USAGE_TAG="cowcloak-stats",
        COWCLOAK_USAGE_DB_PATH=db_path,
        COWCLOAK_USAGE_HISTORY_COUNT=100,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, mode_tag: str, event_at: int) -> None:
        self.mode_tag = mode_tag
        self.event_at = event_at

    async def list_domains(self):
        return [{"domain": "example.org", "tags": [self.mode_tag]}]

    async def list_mailboxes(self):
        return [
            {
                "username": "user@example.org",
                "domain": "example.org",
                "tags": [],
            }
        ]

    async def list_aliases(self):
        return [
            AliasRecord(
                id=1,
                address="amazon-k7@example.org",
                goto="user@example.org",
                domain="example.org",
                active=True,
                private_comment="",
                public_comment="Amazon",
            )
        ]

    async def get_rspamd_history(self, count: int):
        assert count == 100
        return [
            {
                "unix_time": self.event_at,
                "action": "no action",
                "sender_smtp": "news@amazon.de",
                "sender_mime": "news@amazon.de",
                "rcpt_smtp": ["amazon-k7@example.org"],
                "message-id": f"incoming-{self.mode_tag}@amazon.de",
                "user": "unknown",
            }
        ]


@pytest.mark.parametrize(
    ("mode_tag", "expected_key", "expected_address"),
    [
        ("cowcloak-stats-domain", "amazon.de", None),
        ("cowcloak-stats-full", "news@amazon.de", "news@amazon.de"),
    ],
)
async def test_collector_stores_sender_at_selected_detail_level(
    tmp_path,
    mode_tag,
    expected_key,
    expected_address,
):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(mode_tag, started_at + 1000)
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.collect_once() == 2
    assert await collector.collect_once() == 0

    usage = await store.sender_usage("user@example.org", ["amazon-k7@example.org"])
    sender = usage["amazon-k7@example.org"][0]
    assert sender.sender_key == expected_key
    assert sender.sender_domain == "amazon.de"
    assert sender.sender_address == expected_address
