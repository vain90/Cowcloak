from cowcloak.collector_health import CollectorHealthStore, assess_collector_health
from cowcloak.stats import StatsStore


def history(*timestamps: int) -> list[dict[str, int]]:
    return [{"unix_time": timestamp} for timestamp in timestamps]


async def initialized_store(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    stats_store = StatsStore(str(db_path))
    await stats_store.initialize()
    return CollectorHealthStore(db_path)


async def successful_poll(
    store: CollectorHealthStore,
    *,
    attempted_at: int,
    finished_at: int,
    values: list[dict[str, int]] | None,
    history_limit: int = 100,
):
    await store.record_attempt(
        attempted_at=attempted_at,
        poll_interval_seconds=60,
        history_limit=history_limit,
    )
    return await store.record_success(
        finished_at=finished_at,
        duration_ms=125,
        history=values,
    )


async def test_healthy_overlap_uses_entries_older_than_previous_watermark(tmp_path):
    store = await initialized_store(tmp_path)
    await successful_poll(
        store,
        attempted_at=100,
        finished_at=101,
        values=history(10, 20, 30, 40, 50),
    )

    health = await successful_poll(
        store,
        attempted_at=160,
        finished_at=161,
        values=history(20, 30, 40, 50, 60, 70, 80, 90),
    )

    assert health.previous_watermark == 50
    assert health.watermark == 90
    assert health.overlap_count == 3
    assert health.headroom_percent == 37.5
    assert health.coverage_state == "healthy"
    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
        now=162,
    ).state == "healthy"


async def test_exactly_ten_percent_headroom_is_healthy(tmp_path):
    store = await initialized_store(tmp_path)
    await successful_poll(
        store,
        attempted_at=100,
        finished_at=101,
        values=history(10, 20, 30, 40, 50),
    )

    health = await successful_poll(
        store,
        attempted_at=160,
        finished_at=161,
        values=history(40, 50, 60, 70, 80, 90, 100, 110, 120, 130),
    )

    assert health.overlap_count == 1
    assert health.headroom_percent == 10.0
    assert health.coverage_state == "healthy"
    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
        now=162,
    ).state == "healthy"


async def test_low_headroom_below_ten_percent(tmp_path):
    store = await initialized_store(tmp_path)
    await successful_poll(
        store,
        attempted_at=100,
        finished_at=101,
        values=history(10, 20, 30, 40, 50),
    )

    values = history(40, 50, *range(60, 240, 10))
    health = await successful_poll(
        store,
        attempted_at=160,
        finished_at=161,
        values=values,
    )

    assert health.overlap_count == 1
    assert health.headroom_percent == 5.0
    assert health.coverage_state == "low"
    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
        now=162,
    ).state == "low"


async def test_initial_success_stays_starting_until_a_watermark_can_be_compared(tmp_path):
    store = await initialized_store(tmp_path)
    health = await successful_poll(
        store,
        attempted_at=100,
        finished_at=101,
        values=history(10, 20, 30),
    )

    assert health.previous_watermark is None
    assert health.headroom_percent is None
    assert health.coverage_state == "initial"
    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
        now=102,
    ).state == "starting"


async def test_missing_previous_watermark_is_possible_gap(tmp_path):
    store = await initialized_store(tmp_path)
    await successful_poll(
        store,
        attempted_at=100,
        finished_at=101,
        values=history(10, 20, 30, 40, 50),
    )

    health = await successful_poll(
        store,
        attempted_at=160,
        finished_at=161,
        values=history(60, 70, 80, 90, 100),
    )

    assert health.previous_watermark == 50
    assert health.oldest_event_at == 60
    assert health.coverage_state == "gap"
    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
        now=162,
    ).state == "gap"


async def test_collector_becomes_stale_after_configured_poll_multiple(tmp_path):
    store = await initialized_store(tmp_path)
    health = await successful_poll(
        store,
        attempted_at=100,
        finished_at=101,
        values=None,
    )

    assert assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
        now=280,
    ).state == "healthy"
    stale = assess_collector_health(
        health,
        poll_interval_seconds=60,
        stale_polls=3,
        now=281,
    )
    assert stale.state == "stale"
    assert stale.stale_after_seconds == 180


async def test_failed_poll_keeps_last_success_and_successful_window(tmp_path):
    store = await initialized_store(tmp_path)
    successful = await successful_poll(
        store,
        attempted_at=100,
        finished_at=101,
        values=history(10, 20, 30),
        history_limit=3,
    )
    assert successful.history_full

    await store.record_attempt(
        attempted_at=160,
        poll_interval_seconds=60,
        history_limit=3,
    )
    failed = await store.record_failure(
        duration_ms=42,
        error=RuntimeError("sensitive details are not persisted"),
    )

    assert failed.last_attempt_at == 160
    assert failed.last_success_at == 101
    assert failed.newest_event_at == 30
    assert failed.watermark == 30
    assert failed.last_error == "RuntimeError"
    assert "sensitive" not in failed.last_error
    assert assess_collector_health(
        failed,
        poll_interval_seconds=60,
        stale_polls=3,
        now=161,
    ).state == "failed"
