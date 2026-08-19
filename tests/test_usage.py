from cowcloak.aliases import RESERVED_COMMENT, AliasRecord
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
    def __init__(self, event_at: int) -> None:
        self.event_at = event_at

    async def list_domains(self):
        return [
            {"domain": "example.org", "tags": ["Cowcloak-Stats"]},
            {"domain": "other.org", "tags": []},
        ]

    async def list_mailboxes(self):
        return [
            {"username": "user@example.org", "domain": "example.org", "tags": []},
            {"username": "other@other.org", "domain": "other.org", "tags": []},
        ]

    async def list_aliases(self):
        return [
            AliasRecord(
                id=1,
                address="shop@example.org",
                goto="user@example.org",
                domain="example.org",
                active=True,
                private_comment="",
                public_comment="Shop",
            ),
            AliasRecord(
                id=2,
                address="user@example.org",
                goto="user@example.org",
                domain="example.org",
                active=True,
                private_comment="",
                public_comment="",
            ),
            AliasRecord(
                id=3,
                address="offline@example.org",
                goto="user@example.org",
                domain="example.org",
                active=True,
                private_comment=RESERVED_COMMENT,
                public_comment="",
            ),
            AliasRecord(
                id=4,
                address="shared@example.org",
                goto="user@example.org,someone@example.org",
                domain="example.org",
                active=True,
                private_comment="",
                public_comment="Shared",
            ),
            AliasRecord(
                id=5,
                address="other@other.org",
                goto="other@other.org",
                domain="other.org",
                active=True,
                private_comment="",
                public_comment="Other",
            ),
        ]

    async def get_rspamd_history(self, count: int):
        assert count == 100
        return [
            {
                "unix_time": self.event_at,
                "action": "no action",
                "sender_smtp": "sender@example.net",
                "rcpt_smtp": ["shop@example.org"],
                "message-id": "message-1@example.net",
                "subject": "Test",
                "user": "unknown",
            },
            {
                "unix_time": self.event_at,
                "action": "soft reject",
                "sender_smtp": "sender@example.net",
                "rcpt_smtp": ["shop@example.org"],
                "message-id": "message-2@example.net",
                "subject": "Rejected",
                "user": "unknown",
            },
            {
                "unix_time": self.event_at,
                "action": "no action",
                "sender_smtp": "sender@example.net",
                "rcpt_smtp": ["offline@example.org"],
                "message-id": "message-3@example.net",
                "subject": "Offline",
                "user": "unknown",
            },
            {
                "unix_time": self.event_at,
                "action": "no action",
                "sender_smtp": "sender@example.net",
                "rcpt_smtp": ["other@other.org"],
                "message-id": "message-4@example.net",
                "subject": "Other",
                "user": "unknown",
            },
        ]


async def test_collector_counts_only_accepted_opted_in_owned_aliases(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(started_at + 1)
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.collect_once() == 1
    assert await collector.collect_once() == 0

    usage = await store.alias_usage(
        "user@example.org",
        ["shop@example.org", "offline@example.org", "shared@example.org"],
    )
    assert usage["shop@example.org"].received_count == 1
    assert "offline@example.org" not in usage
    assert "shared@example.org" not in usage


async def test_mailbox_tag_enables_stats_without_domain_tag(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(started_at + 1)

    async def list_domains():
        return [{"domain": "example.org", "tags": []}]

    async def list_mailboxes():
        return [
            {
                "username": "user@example.org",
                "domain": "example.org",
                "tags": ["cowcloak-stats"],
            }
        ]

    mailcow.list_domains = list_domains
    mailcow.list_mailboxes = list_mailboxes
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.eligible_mailboxes() == {"user@example.org"}
