from __future__ import annotations

import sqlite3
import time
from typing import Any

import pytest

from moolias.collector_health import CollectorHealth, assess_collector_health
from moolias.config import Settings
from moolias.history_probe import (
    HISTORY_PROBE_COVERAGE_STATE,
    HISTORY_PROBE_META_KEY,
    UnchangedHistory,
    history_probe_fingerprints,
)
from moolias.stats import StatsStore
from moolias.usage import UsageCollector


def settings(db_path: str, *, maximum: int = 1000) -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_USAGE_STATS=True,
        MOOLIAS_USAGE_DB_PATH=db_path,
        MOOLIAS_USAGE_HISTORY_COUNT=maximum,
        MOOLIAS_USAGE_POLL_SECONDS=60,
        MOOLIAS_USAGE_STALE_POLLS=3,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def entry(timestamp: int, qid: str) -> dict[str, Any]:
    return {
        "unix_time": timestamp,
        "qid": qid,
        "action": "clean",
    }


def normal_entries() -> list[dict[str, Any]]:
    return [entry(timestamp, f"qid-{timestamp}") for timestamp in range(188, 178, -1)]


class AdaptiveMailcow:
    def __init__(self, entries: list[dict[str, Any]], *, fail_probe: bool = False) -> None:
        self.entries = entries
        self.fail_probe = fail_probe
        self.range_calls: list[tuple[int, int]] = []
        self.history_calls: list[int] = []

    async def get_rspamd_history_range(self, start: int, end: int):
        self.range_calls.append((start, end))
        if start >= len(self.entries):
            return []
        return self.entries[start : min(end + 1, len(self.entries))]

    async def get_rspamd_history(self, count: int):
        self.history_calls.append(count)
        if self.fail_probe and count == 3:
            raise RuntimeError("probe failed")
        return self.entries[:count]


class StaticHealthStore:
    def __init__(self, health: CollectorHealth) -> None:
        self.health = health

    async def read(self) -> CollectorHealth:
        return self.health


async def initialized_collector(
    tmp_path,
    entries: list[dict[str, Any]] | None = None,
    *,
    maximum: int = 1000,
    fail_probe: bool = False,
    collector_type=UsageCollector,
):
    db_path = tmp_path / "usage.sqlite3"
    store = StatsStore(str(db_path))
    await store.initialize()
    mailcow = AdaptiveMailcow(entries or normal_entries(), fail_probe=fail_probe)
    collector = collector_type(settings(str(db_path), maximum=maximum), mailcow, store)
    return collector, mailcow


def health_for_state(state: str, *, now: int | None = None) -> CollectorHealth:
    timestamp = int(time.time()) if now is None else now
    values = {
        "last_attempt_at": timestamp - 1,
        "last_success_at": timestamp - 1,
        "last_error": None,
        "last_duration_ms": 10,
        "poll_interval_seconds": 60,
        "history_limit": 1000,
        "history_count": 10,
        "oldest_event_at": 170,
        "newest_event_at": 180,
        "previous_watermark": 170,
        "watermark": 180,
        "overlap_count": 1,
        "headroom_percent": 10.0,
        "coverage_state": "healthy",
    }
    if state == "starting":
        values["coverage_state"] = "initial"
    elif state == "low":
        values["coverage_state"] = "low"
        values["headroom_percent"] = 5.0
    elif state == "gap":
        values["coverage_state"] = "gap"
        values["overlap_count"] = 0
        values["headroom_percent"] = 0.0
    elif state == "stale":
        values["last_success_at"] = timestamp - 181
    elif state == "failed":
        values["last_error"] = "RuntimeError"
    elif state in {"unknown", "unavailable"}:
        values["coverage_state"] = state
    elif state != "healthy":
        raise ValueError(state)
    return CollectorHealth(**values)


async def seed_healthy_health(collector: UsageCollector) -> CollectorHealth:
    now = int(time.time())
    await collector.health_store.record_attempt(
        attempted_at=now - 120,
        poll_interval_seconds=60,
        history_limit=1000,
    )
    await collector.health_store.record_success(
        finished_at=now - 119,
        duration_ms=10,
        history=[entry(value, f"seed-a-{value}") for value in (100, 110, 120)],
    )
    await collector.health_store.record_attempt(
        attempted_at=now - 60,
        poll_interval_seconds=60,
        history_limit=1000,
    )
    health = await collector.health_store.record_success(
        finished_at=now - 59,
        duration_ms=10,
        history=[entry(value, f"seed-b-{value}") for value in range(110, 201, 10)],
    )
    assert health.coverage_state == "healthy"
    return health


async def test_healthy_identical_probe_skips_normal_history_fetch(tmp_path):
    collector, mailcow = await initialized_collector(tmp_path)
    collector.health_store = StaticHealthStore(health_for_state("healthy"))
    await collector.history_probe_store.record_full_history(mailcow.entries)

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert isinstance(result, UnchangedHistory)
    assert mailcow.history_calls == [3]
    assert mailcow.range_calls == []


async def test_healthy_changed_probe_falls_back_to_normal_ten_entry_fetch(tmp_path):
    collector, mailcow = await initialized_collector(tmp_path)
    collector.health_store = StaticHealthStore(health_for_state("healthy"))
    previous = [entry(188, "old-a"), entry(187, "old-b"), entry(186, "old-c")]
    await collector.history_probe_store.record_full_history(previous)

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert result == mailcow.entries
    assert mailcow.history_calls == [3, 10]
    assert mailcow.range_calls == [(9, 9)]
    assert await collector.history_probe_store.read() is None


async def test_changed_probe_keeps_existing_adaptive_escalation(tmp_path):
    entries = [entry(timestamp, f"qid-{timestamp}") for timestamp in range(230, 190, -1)]
    collector, mailcow = await initialized_collector(tmp_path, entries, maximum=100)
    collector.health_store = StaticHealthStore(health_for_state("healthy"))
    previous = [entry(230, "old-a"), entry(229, "old-b"), entry(228, "old-c")]
    await collector.history_probe_store.record_full_history(previous)

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert result == entries
    assert mailcow.history_calls == [3, 50]
    assert mailcow.range_calls == [(9, 9), (22, 22), (45, 45)]


async def test_same_timestamps_with_different_identity_trigger_slow_path(tmp_path):
    current_head = [
        entry(188, "new-a"),
        entry(188, "new-b"),
        entry(188, "new-c"),
    ]
    entries = [
        *current_head,
        entry(185, "tail-185"),
        entry(184, "tail-184"),
        entry(183, "tail-183"),
        entry(182, "tail-182"),
        entry(181, "tail-181"),
        entry(180, "tail-180"),
        entry(179, "tail-179"),
    ]
    collector, mailcow = await initialized_collector(tmp_path, entries)
    collector.health_store = StaticHealthStore(health_for_state("healthy"))
    previous_head = [
        entry(188, "old-a"),
        entry(188, "old-b"),
        entry(188, "old-c"),
    ]
    assert history_probe_fingerprints(previous_head) != history_probe_fingerprints(current_head)
    await collector.history_probe_store.record_full_history(previous_head)

    await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert mailcow.history_calls == [3, 10]


@pytest.mark.parametrize(
    "state",
    ["starting", "low", "gap", "stale", "failed", "unknown", "unavailable"],
)
async def test_unsafe_collector_states_bypass_head_probe(tmp_path, state):
    collector, mailcow = await initialized_collector(tmp_path)
    collector.health_store = StaticHealthStore(health_for_state(state))
    await collector.history_probe_store.record_full_history(mailcow.entries)

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert result == mailcow.entries
    assert mailcow.history_calls == [10]
    assert mailcow.range_calls == [(9, 9)]


@pytest.mark.parametrize("invalid", [False, True])
async def test_missing_or_invalid_probe_state_bypasses_head_probe(tmp_path, invalid):
    collector, mailcow = await initialized_collector(tmp_path)
    collector.health_store = StaticHealthStore(health_for_state("healthy"))
    if invalid:
        with sqlite3.connect(collector.store.path) as connection:
            connection.execute(
                "INSERT INTO usage_meta (key, value) VALUES (?, ?)",
                (HISTORY_PROBE_META_KEY, "not-json"),
            )

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert result == mailcow.entries
    assert mailcow.history_calls == [10]
    assert mailcow.range_calls == [(9, 9)]


class ProbeOnlyCollector(UsageCollector):
    async def collect_once(self) -> int:
        self._last_history = await self._adaptive_rspamd_history(tracking_started_at=1)
        return 0


async def test_probe_request_failure_marks_collector_failed(tmp_path):
    collector, mailcow = await initialized_collector(
        tmp_path,
        fail_probe=True,
        collector_type=ProbeOnlyCollector,
    )
    await seed_healthy_health(collector)
    await collector.history_probe_store.record_full_history(mailcow.entries)

    with pytest.raises(RuntimeError, match="probe failed"):
        await collector.collect_with_health()

    health = await collector.health_store.read()
    assert health.last_error == "RuntimeError"
    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
    ).state == "failed"


class UnchangedOnlyCollector(UsageCollector):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.prune_coverage_state: str | None = None

    async def collect_once(self) -> int:
        self._last_history = UnchangedHistory()
        return 0

    async def _prune_deduplication(self, health: CollectorHealth, *, now: int) -> None:
        self.prune_coverage_state = health.coverage_state


async def test_unchanged_probe_preserves_full_window_and_pruning_safety_state(tmp_path):
    collector, _ = await initialized_collector(tmp_path, collector_type=UnchangedOnlyCollector)
    previous = await seed_healthy_health(collector)

    await collector.collect_with_health()

    health = await collector.health_store.read()
    assert health.coverage_state == HISTORY_PROBE_COVERAGE_STATE
    assert health.watermark == previous.watermark
    assert health.previous_watermark == previous.previous_watermark
    assert health.history_count == previous.history_count
    assert health.overlap_count == previous.overlap_count
    assert health.headroom_percent == previous.headroom_percent
    assert collector.prune_coverage_state == "healthy"
    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
    ).state == "healthy"
