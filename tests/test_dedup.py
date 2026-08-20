import sqlite3

from moolias.dedup import (
    DEDUP_CLEANUP_INTERVAL_SECONDS,
    DedupStore,
    dedup_cleanup_due,
    dedup_prune_cutoff,
    dedup_safety_seconds,
)
from moolias.stats import SenderEvent, StatsStore, UsageEvent

MAILBOX = "user@example.org"
ALIAS = "shop@example.org"


def test_prune_cutoff_requires_healthy_overlap_and_keeps_safety_margin():
    assert dedup_safety_seconds(poll_interval_seconds=60, stale_polls=3) == 3600
    assert dedup_prune_cutoff(
        previous_watermark=10_000,
        coverage_state="healthy",
        poll_interval_seconds=60,
        stale_polls=3,
    ) == 6400

    assert dedup_prune_cutoff(
        previous_watermark=50_000,
        coverage_state="healthy",
        poll_interval_seconds=3600,
        stale_polls=3,
    ) == 28_400

    for state in (None, "initial", "low", "gap", "unknown"):
        assert (
            dedup_prune_cutoff(
                previous_watermark=10_000,
                coverage_state=state,
                poll_interval_seconds=60,
                stale_polls=3,
            )
            is None
        )

    assert (
        dedup_prune_cutoff(
            previous_watermark=None,
            coverage_state="healthy",
            poll_interval_seconds=60,
            stale_polls=3,
        )
        is None
    )


def test_cleanup_is_periodic_not_per_poll():
    now = 100_000
    assert dedup_cleanup_due(last_pruned_at=None, now=now)
    assert not dedup_cleanup_due(last_pruned_at=now - 60, now=now)
    assert not dedup_cleanup_due(
        last_pruned_at=now - DEDUP_CLEANUP_INTERVAL_SECONDS + 1,
        now=now,
    )
    assert dedup_cleanup_due(
        last_pruned_at=now - DEDUP_CLEANUP_INTERVAL_SECONDS,
        now=now,
    )


async def test_pruning_removes_only_old_dedup_state_and_blocks_replay_after_restart(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    store = StatsStore(str(db_path))
    await store.initialize()
    started_at = await store.tracking_started_at()
    await store.sync_sender_modes({MAILBOX: "full"}, now=started_at)

    old_at = started_at + 10
    recent_at = started_at + 7200
    old_usage = UsageEvent("usage-old", MAILBOX, ALIAS, old_at)
    recent_usage = UsageEvent("usage-recent", MAILBOX, ALIAS, recent_at)
    old_sender = SenderEvent(
        "sender-old",
        MAILBOX,
        ALIAS,
        "vendor.example",
        "one@vendor.example",
        "full",
        old_at,
    )
    recent_sender = SenderEvent(
        "sender-recent",
        MAILBOX,
        ALIAS,
        "vendor.example",
        "one@vendor.example",
        "full",
        recent_at,
    )

    assert await store.record_received([old_usage, recent_usage]) == 2
    assert await store.record_senders([old_sender, recent_sender]) == 2

    pruner = DedupStore(db_path)
    result = await pruner.prune(old_at, pruned_at=recent_at + 1)

    assert result.floor_at == old_at
    assert result.processed_events == 1
    assert result.sender_processed_events == 1
    assert result.total == 2
    assert await pruner.floor_at() == old_at
    assert await pruner.last_pruned_at() == recent_at + 1

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM processed_events").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM sender_processed_events").fetchone()[0]
            == 1
        )

    usage = await store.alias_usage(MAILBOX, [ALIAS])
    assert usage[ALIAS].received_count == 2
    senders = await store.sender_usage(MAILBOX, [ALIAS])
    assert senders[ALIAS][0].received_count == 2

    # The old hashes are gone, but the persistent floor makes replaying those
    # Rspamd events a no-op instead of counting them a second time.
    assert await store.record_received([old_usage]) == 0
    assert await store.record_senders([old_sender]) == 0

    # Recent hashes are deliberately retained and continue to deduplicate normally.
    assert await store.record_received([recent_usage]) == 0
    assert await store.record_senders([recent_sender]) == 0

    restarted_store = StatsStore(str(db_path))
    await restarted_store.initialize()
    assert await restarted_store.record_received([old_usage]) == 0
    assert await restarted_store.record_senders([old_sender]) == 0

    newer_usage = UsageEvent("usage-new", MAILBOX, ALIAS, recent_at + 10)
    assert await restarted_store.record_received([newer_usage]) == 1

    # The floor is monotonic even if a later cleanup is given an older cutoff.
    second = await pruner.prune(old_at - 5, pruned_at=recent_at + 2)
    assert second.floor_at == old_at
    assert await pruner.floor_at() == old_at


async def test_pruning_deletes_only_one_bounded_batch_per_table(tmp_path):
    db_path = tmp_path / "bounded.sqlite3"
    store = StatsStore(str(db_path))
    await store.initialize()
    started_at = await store.tracking_started_at()
    await store.sync_sender_modes({MAILBOX: "full"}, now=started_at)

    usage_events = [
        UsageEvent(f"usage-{index}", MAILBOX, ALIAS, started_at + index)
        for index in range(1, 4)
    ]
    sender_events = [
        SenderEvent(
            f"sender-{index}",
            MAILBOX,
            ALIAS,
            "vendor.example",
            "one@vendor.example",
            "full",
            started_at + index,
        )
        for index in range(1, 4)
    ]
    assert await store.record_received(usage_events) == 3
    assert await store.record_senders(sender_events) == 3

    pruner = DedupStore(db_path, batch_size=1)
    result = await pruner.prune(started_at + 3, pruned_at=started_at + 100)
    assert result.processed_events == 1
    assert result.sender_processed_events == 1

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM processed_events").fetchone()[0] == 2
        assert (
            connection.execute("SELECT COUNT(*) FROM sender_processed_events").fetchone()[0]
            == 2
        )

    usage = await store.alias_usage(MAILBOX, [ALIAS])
    assert usage[ALIAS].received_count == 3
    senders = await store.sender_usage(MAILBOX, [ALIAS])
    assert senders[ALIAS][0].received_count == 3
