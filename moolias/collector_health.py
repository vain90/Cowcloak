from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOW_HEADROOM_PERCENT = 10.0


@dataclass(frozen=True, slots=True)
class CollectorHealth:
    last_attempt_at: int | None = None
    last_success_at: int | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None
    poll_interval_seconds: int | None = None
    history_limit: int | None = None
    history_count: int | None = None
    oldest_event_at: int | None = None
    newest_event_at: int | None = None
    previous_watermark: int | None = None
    watermark: int | None = None
    overlap_count: int | None = None
    headroom_percent: float | None = None
    coverage_state: str | None = None

    @property
    def history_full(self) -> bool:
        return (
            self.history_count is not None
            and self.history_limit is not None
            and self.history_count >= self.history_limit
        )

    @property
    def history_buffer_percent(self) -> float | None:
        """Remaining configured Rspamd-history capacity since the previous watermark."""
        if (
            self.history_limit is None
            or self.history_limit <= 0
            or self.history_count is None
            or self.overlap_count is None
            or self.coverage_state in {None, "initial", "unavailable", "unknown", "gap"}
        ):
            return None

        # overlap_count deliberately includes only entries strictly older than the
        # previous watermark. Entries with the same timestamp are therefore treated
        # as consumed capacity, which keeps this user-facing buffer conservative.
        consumed = max(0, self.history_count - self.overlap_count)
        remaining = max(0, self.history_limit - consumed)
        return min(100.0, (remaining / self.history_limit) * 100.0)


@dataclass(frozen=True, slots=True)
class CollectorHealthView:
    state: str
    health: CollectorHealth
    stale: bool
    stale_after_seconds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "stale": self.stale,
            "stale_after_seconds": self.stale_after_seconds,
            "history_full": self.health.history_full,
            "history_buffer_percent": self.health.history_buffer_percent,
            "last_attempt_at": self.health.last_attempt_at,
            "last_success_at": self.health.last_success_at,
            "last_error": self.health.last_error,
            "last_duration_ms": self.health.last_duration_ms,
            "poll_interval_seconds": self.health.poll_interval_seconds,
            "history_limit": self.health.history_limit,
            "history_count": self.health.history_count,
            "oldest_event_at": self.health.oldest_event_at,
            "newest_event_at": self.health.newest_event_at,
            "previous_watermark": self.health.previous_watermark,
            "watermark": self.health.watermark,
            "overlap_count": self.health.overlap_count,
            "headroom_percent": self.health.headroom_percent,
            "coverage_state": self.health.coverage_state,
        }


def _history_timestamps(history: list[dict[str, Any]]) -> list[int]:
    result: list[int] = []
    for item in history:
        value = item.get("unix_time")
        try:
            result.append(int(float(value)))
        except (TypeError, ValueError):
            continue
    return result


def assess_collector_health(
    health: CollectorHealth,
    *,
    poll_interval_seconds: int,
    stale_polls: int,
    now: int | None = None,
) -> CollectorHealthView:
    timestamp = int(time.time()) if now is None else int(now)
    stale_after_seconds = poll_interval_seconds * stale_polls
    stale = (
        health.last_success_at is not None
        and timestamp - health.last_success_at >= stale_after_seconds
    )
    history_buffer_percent = health.history_buffer_percent

    if health.last_error:
        state = "failed"
    elif health.coverage_state == "gap":
        state = "gap"
    elif stale:
        state = "stale"
    elif (
        history_buffer_percent is not None
        and history_buffer_percent < LOW_HEADROOM_PERCENT
    ):
        state = "low"
    elif health.last_success_at is None or health.coverage_state == "initial":
        state = "starting"
    else:
        state = "healthy"

    return CollectorHealthView(
        state=state,
        health=health,
        stale=stale,
        stale_after_seconds=stale_after_seconds,
    )


class CollectorHealthStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def read(self) -> CollectorHealth:
        return await asyncio.to_thread(self._read)

    def _read(self) -> CollectorHealth:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM collector_health WHERE id = 1"
            ).fetchone()
        if row is None:
            return CollectorHealth()
        return CollectorHealth(
            last_attempt_at=row["last_attempt_at"],
            last_success_at=row["last_success_at"],
            last_error=row["last_error"],
            last_duration_ms=row["last_duration_ms"],
            poll_interval_seconds=row["poll_interval_seconds"],
            history_limit=row["history_limit"],
            history_count=row["history_count"],
            oldest_event_at=row["oldest_event_at"],
            newest_event_at=row["newest_event_at"],
            previous_watermark=row["previous_watermark"],
            watermark=row["watermark"],
            overlap_count=row["overlap_count"],
            headroom_percent=row["headroom_percent"],
            coverage_state=row["coverage_state"],
        )

    async def record_attempt(
        self,
        *,
        attempted_at: int,
        poll_interval_seconds: int,
        history_limit: int,
    ) -> None:
        await asyncio.to_thread(
            self._record_attempt,
            attempted_at,
            poll_interval_seconds,
            history_limit,
        )

    def _record_attempt(
        self,
        attempted_at: int,
        poll_interval_seconds: int,
        history_limit: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO collector_health (
                    id,
                    last_attempt_at,
                    poll_interval_seconds,
                    history_limit
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_attempt_at = excluded.last_attempt_at,
                    poll_interval_seconds = excluded.poll_interval_seconds,
                    history_limit = excluded.history_limit
                """,
                (attempted_at, poll_interval_seconds, history_limit),
            )

    async def record_success(
        self,
        *,
        finished_at: int,
        duration_ms: int,
        history: list[dict[str, Any]] | None,
    ) -> CollectorHealth:
        return await asyncio.to_thread(
            self._record_success,
            finished_at,
            duration_ms,
            history,
        )

    def _record_success(
        self,
        finished_at: int,
        duration_ms: int,
        history: list[dict[str, Any]] | None,
    ) -> CollectorHealth:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT watermark FROM collector_health WHERE id = 1"
            ).fetchone()
            previous_watermark = (
                int(row["watermark"])
                if row is not None and row["watermark"] is not None
                else None
            )

            if history is None:
                values = (None, None, None, None, None, None, "unavailable")
            else:
                history_count = len(history)
                timestamps = _history_timestamps(history)
                oldest_event_at = min(timestamps) if timestamps else None
                newest_event_at = max(timestamps) if timestamps else None
                watermark = newest_event_at
                overlap_count: int | None = None
                headroom_percent: float | None = None
                coverage_state = "unknown"

                if previous_watermark is None:
                    coverage_state = "initial"
                elif history_count == 0 or oldest_event_at is None or newest_event_at is None:
                    coverage_state = "gap"
                    overlap_count = 0
                    headroom_percent = 0.0
                elif not (oldest_event_at <= previous_watermark <= newest_event_at):
                    coverage_state = "gap"
                    overlap_count = sum(value < previous_watermark for value in timestamps)
                    headroom_percent = (overlap_count / history_count) * 100.0
                else:
                    overlap_count = sum(value < previous_watermark for value in timestamps)
                    headroom_percent = (overlap_count / history_count) * 100.0
                    coverage_state = (
                        "low" if headroom_percent < LOW_HEADROOM_PERCENT else "healthy"
                    )

                values = (
                    history_count,
                    oldest_event_at,
                    newest_event_at,
                    previous_watermark,
                    watermark,
                    overlap_count,
                    headroom_percent,
                    coverage_state,
                )

            if history is None:
                connection.execute(
                    """
                    UPDATE collector_health
                    SET last_success_at = ?,
                        last_error = NULL,
                        last_duration_ms = ?,
                        history_count = NULL,
                        oldest_event_at = NULL,
                        newest_event_at = NULL,
                        previous_watermark = NULL,
                        watermark = NULL,
                        overlap_count = NULL,
                        headroom_percent = NULL,
                        coverage_state = ?
                    WHERE id = 1
                    """,
                    (finished_at, duration_ms, values[-1]),
                )
            else:
                connection.execute(
                    """
                    UPDATE collector_health
                    SET last_success_at = ?,
                        last_error = NULL,
                        last_duration_ms = ?,
                        history_count = ?,
                        oldest_event_at = ?,
                        newest_event_at = ?,
                        previous_watermark = ?,
                        watermark = ?,
                        overlap_count = ?,
                        headroom_percent = ?,
                        coverage_state = ?
                    WHERE id = 1
                    """,
                    (finished_at, duration_ms, *values),
                )
        return self._read()

    async def record_failure(
        self,
        *,
        duration_ms: int,
        error: BaseException,
    ) -> CollectorHealth:
        return await asyncio.to_thread(self._record_failure, duration_ms, error)

    def _record_failure(self, duration_ms: int, error: BaseException) -> CollectorHealth:
        error_name = type(error).__name__[:120]
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE collector_health
                SET last_error = ?, last_duration_ms = ?
                WHERE id = 1
                """,
                (error_name, duration_ms),
            )
        return self._read()
