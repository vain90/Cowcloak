from moolias.aliases import RESERVED_COMMENT, USED_RESERVED_COMMENT, AliasRecord
from moolias.config import Settings
from moolias.stats import StatsStore, UsageEvent
from moolias.usage import UsageCollector


def settings(db_path: str, *, access_tag: str = "") -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_ACCESS_TAG=access_tag,
        MOOLIAS_USAGE_STATS=True,
        MOOLIAS_USAGE_TAG="moolias-stats",
        MOOLIAS_USAGE_DB_PATH=db_path,
        MOOLIAS_USAGE_HISTORY_COUNT=100,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, event_at: int) -> None:
        self.event_at = event_at
        self.marked_used: set[int] = set()

    async def list_domains(self):
        return [
            {"domain": "example.org", "tags": ["Moolias-Stats"]},
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
                private_comment=(
                    USED_RESERVED_COMMENT if 3 in self.marked_used else RESERVED_COMMENT
                ),
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

    async def get_alias(self, alias_id: int):
        return next(alias for alias in await self.list_aliases() if alias.id == alias_id)

    async def mark_reserved_alias_used(self, alias_id: int):
        self.marked_used.add(alias_id)

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
                "unix_time": self.event_at + 10,
                "action": "add header",
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


async def test_collector_counts_accepted_opted_in_owned_and_reserved_aliases(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(started_at + 1)
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.collect_once() == 2
    assert await collector.collect_once() == 0

    usage = await store.alias_usage(
        "user@example.org",
        ["shop@example.org", "offline@example.org", "shared@example.org"],
    )
    assert usage["shop@example.org"].received_count == 1
    assert usage["shop@example.org"].sent_count == 0
    assert usage["offline@example.org"].received_count == 1
    assert "shared@example.org" not in usage
    assert mailcow.marked_used == {3}


async def test_reserved_offline_alias_collects_sender_detail_in_full_mode(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(started_at + 1)

    async def list_domains():
        return [
            {"domain": "example.org", "tags": ["moolias-stats-full"]},
            {"domain": "other.org", "tags": []},
        ]

    mailcow.list_domains = list_domains
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.collect_once() == 4
    senders = await store.sender_usage("user@example.org", ["offline@example.org"])
    assert len(senders["offline@example.org"]) == 1
    assert senders["offline@example.org"][0].sender_address == "sender@example.net"
    assert senders["offline@example.org"][0].sender_domain == "example.net"
    assert mailcow.marked_used == {3}


async def test_collector_counts_authenticated_alias_sends_once(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(started_at + 1)

    async def get_rspamd_history(count: int):
        assert count == 100
        return [
            {
                "unix_time": started_at + 1,
                "action": "no action",
                "sender_smtp": "shop@example.org",
                "sender_mime": "shop@example.org",
                "rcpt_smtp": ["outside@example.net"],
                "message-id": "outbound-1@example.org",
                "user": "user@example.org",
            },
            {
                "unix_time": started_at + 2,
                "action": "add header",
                "sender_smtp": "shop@example.org",
                "sender_mime": "shop@example.org",
                "rcpt_smtp": ["outside@example.net"],
                "message-id": "outbound-1@example.org",
                "user": "user@example.org",
            },
            {
                "unix_time": started_at + 3,
                "action": "no action",
                "sender_smtp": "user@example.org",
                "sender_mime": "shop@example.org",
                "rcpt_smtp": ["outside@example.net"],
                "message-id": "outbound-2@example.org",
                "user": "user@example.org",
            },
            {
                "unix_time": started_at + 4,
                "action": "no action",
                "sender_smtp": "shop@example.org",
                "sender_mime": "shop@example.org",
                "rcpt_smtp": ["outside@example.net"],
                "message-id": "wrong-user@example.org",
                "user": "other@other.org",
            },
            {
                "unix_time": started_at + 5,
                "action": "soft reject",
                "sender_smtp": "shop@example.org",
                "sender_mime": "shop@example.org",
                "rcpt_smtp": ["outside@example.net"],
                "message-id": "rejected@example.org",
                "user": "user@example.org",
            },
        ]

    mailcow.get_rspamd_history = get_rspamd_history
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.collect_once() == 2
    assert await collector.collect_once() == 0

    usage = await store.alias_usage("user@example.org", ["shop@example.org"])
    assert usage["shop@example.org"].received_count == 0
    assert usage["shop@example.org"].sent_count == 2
    assert usage["shop@example.org"].last_sent_at == started_at + 3


async def test_reserved_offline_alias_is_marked_used_after_authenticated_send(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(started_at + 1)

    async def get_rspamd_history(count: int):
        assert count == 100
        return [
            {
                "unix_time": started_at + 1,
                "action": "no action",
                "sender_smtp": "offline@example.org",
                "sender_mime": "offline@example.org",
                "rcpt_smtp": ["outside@example.net"],
                "message-id": "offline-outbound@example.org",
                "user": "user@example.org",
            }
        ]

    mailcow.get_rspamd_history = get_rspamd_history
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.collect_once() == 1
    assert mailcow.marked_used == {3}

    usage = await store.alias_usage("user@example.org", ["offline@example.org"])
    assert usage["offline@example.org"].sent_count == 1


async def test_existing_reserved_usage_is_migrated_to_persistent_marker(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    await store.record_received(
        [
            UsageEvent(
                event_key="existing-offline-event",
                mailbox="user@example.org",
                alias="offline@example.org",
                event_at=started_at + 1,
            )
        ]
    )
    mailcow = FakeMailcow(started_at + 2)

    async def get_rspamd_history(count: int):
        assert count == 100
        return []

    mailcow.get_rspamd_history = get_rspamd_history
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.collect_once() == 0
    assert mailcow.marked_used == {3}


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
                "tags": ["moolias-stats"],
            }
        ]

    mailcow.list_domains = list_domains
    mailcow.list_mailboxes = list_mailboxes
    collector = UsageCollector(settings(str(tmp_path / "usage.sqlite3")), mailcow, store)

    assert await collector.eligible_mailboxes() == {"user@example.org"}


async def test_usage_tag_does_not_bypass_configured_access_tag(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    started_at = await store.tracking_started_at()
    mailcow = FakeMailcow(started_at + 1)

    collector = UsageCollector(
        settings(str(tmp_path / "usage.sqlite3"), access_tag="moolias"),
        mailcow,
        store,
    )
    assert await collector.eligible_mailboxes() == set()

    async def list_mailboxes():
        return [
            {
                "username": "user@example.org",
                "domain": "example.org",
                "tags": ["moolias"],
            }
        ]

    mailcow.list_mailboxes = list_mailboxes
    assert await collector.eligible_mailboxes() == {"user@example.org"}
