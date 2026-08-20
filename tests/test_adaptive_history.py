import httpx

from moolias.config import Settings
from moolias.mailcow import MailcowClient
from moolias.stats import StatsStore
from moolias.usage import UsageCollector


def settings(db_path: str, *, maximum: int = 1000) -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_USAGE_STATS=True,
        MOOLIAS_USAGE_DB_PATH=db_path,
        MOOLIAS_USAGE_HISTORY_COUNT=maximum,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def history(*timestamps: int) -> list[dict[str, int]]:
    return [{"unix_time": timestamp} for timestamp in timestamps]


class AdaptiveMailcow:
    def __init__(self, entries: list[dict[str, int]]) -> None:
        self.entries = entries
        self.range_calls: list[tuple[int, int]] = []
        self.history_calls: list[int] = []

    async def get_rspamd_history_range(self, start: int, end: int):
        self.range_calls.append((start, end))
        if start >= len(self.entries):
            return []
        return self.entries[start : min(end + 1, len(self.entries))]

    async def get_rspamd_history(self, count: int):
        self.history_calls.append(count)
        return self.entries[:count]


async def collector_with_watermark(tmp_path, entries, *, maximum=1000, watermark=100):
    db_path = tmp_path / "usage.sqlite3"
    store = StatsStore(str(db_path))
    await store.initialize()
    mailcow = AdaptiveMailcow(entries)
    collector = UsageCollector(settings(str(db_path), maximum=maximum), mailcow, store)

    await collector.health_store.record_attempt(
        attempted_at=90,
        poll_interval_seconds=60,
        history_limit=maximum,
    )
    await collector.health_store.record_success(
        finished_at=91,
        duration_ms=1,
        history=history(80, 90, watermark),
    )
    return collector, mailcow


async def test_adaptive_history_stops_at_ten_when_ten_percent_overlap_is_available(tmp_path):
    entries = history(108, 107, 106, 105, 104, 103, 102, 101, 100, 99)
    collector, mailcow = await collector_with_watermark(tmp_path, entries)

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert result == entries
    assert mailcow.range_calls == [(9, 9)]
    assert mailcow.history_calls == [10]


async def test_adaptive_history_probes_ten_then_uses_twenty_five(tmp_path):
    entries = history(*(130 - 2 * index for index in range(40)))
    collector, mailcow = await collector_with_watermark(tmp_path, entries)

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert result == entries[:25]
    assert mailcow.range_calls == [(9, 9), (22, 22)]
    assert mailcow.history_calls == [25]


async def test_adaptive_history_loads_maximum_when_smaller_probes_do_not_reach_watermark(
    tmp_path,
):
    entries = history(*(300 - index for index in range(100)))
    collector, mailcow = await collector_with_watermark(
        tmp_path,
        entries,
        maximum=100,
        watermark=100,
    )

    result = await collector._adaptive_rspamd_history(tracking_started_at=1)

    assert result == entries
    assert mailcow.range_calls == [(9, 9), (22, 22), (45, 45)]
    assert mailcow.history_calls == [100]


def test_adaptive_probe_sizes_and_indexes_match_ten_percent_target(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    store = StatsStore(str(db_path))
    collector = UsageCollector(settings(str(db_path)), AdaptiveMailcow([]), store)

    assert collector._history_request_sizes() == [10, 25, 50, 100, 250, 500, 1000]
    assert [collector._history_probe_index(count) for count in (10, 25, 50, 100, 250, 500)] == [
        9,
        22,
        45,
        90,
        225,
        450,
    ]


async def test_mailcow_rspamd_history_range_uses_zero_based_range_path():
    paths = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=[{"unix_time": 123}])

    client = MailcowClient(settings("/tmp/test.sqlite3"), transport=httpx.MockTransport(handler))
    payload = await client.get_rspamd_history_range(49, 49)
    await client.close()

    assert payload == [{"unix_time": 123}]
    assert paths == ["/api/v1/get/logs/rspamd-history/49-49"]
