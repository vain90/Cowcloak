from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEDUP_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
DEDUP_MIN_SAFETY_SECONDS = 60 * 60
DEDUP_FLOOR_KEY = "deduplication_floor_at"
DEDUP_LAST_PRUNED_KEY = "deduplication_last_pruned_at"


@dataclass(frozen=True, slots=True)
class DedupPruneResult:
    floor_at: int
    processed_events: int
    sender_processed_events: int

    @property
    def total(self) -> int:
        return self.processed_events + self.sender_processed_events


def dedup_safety_seconds(*, poll_interval_seconds: int, stale_polls: int) -> int:
    return max(
        DEDUP_MIN_SAFETY_SECONDS,
        int(poll_interval_seconds) * int(stale_polls) * 2,
    )


def dedup_prune_cutoff(
    *,
    previous_watermark: int | None,
    coverage_state: str | None,
    poll_interval_seconds: int,
    stale_polls: int,
) -> int | None:
    if previous_watermark is None or coverage_state != "healthy":
        return None
    safety_seconds = dedup_safety_seconds(
        poll_interval_seconds=poll_interval_seconds,
        stale_polls=stale_polls,
    )
    return max(0, int(previous_watermark) - safety_seconds)


def dedup_cleanup_due(*, last_pruned_at: int | None, now: int) -> bool:
    if last_pruned_at is None:
        return True
    return int(now) - int(last_pruned_at) >= DEDUP_CLEANUP_INTERVAL_SECONDS


class DedupStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _meta_int(connection: sqlite3.Connection, key: str) -> int | None:
        row = connection.execute(
            "SELECT value FROM usage_meta WHERE key = ?",
            (key,),
        ).fetchone()
        return int(row["value"]) if row is not None else None

    async def last_pruned_at(self) -> int | None:
        return await asyncio.to_thread(self._last_pruned_at)

    def _last_pruned_at(self) -> int | None:
        with self._connect() as connection:
            return self._meta_int(connection, DEDUP_LAST_PRUNED_KEY)

    async def floor_at(self) -> int | None:
        return await asyncio.to_thread(self._floor_at)

    def _floor_at(self) -> int | None:
        with self._connect() as connection:
            return self._meta_int(connection, DEDUP_FLOOR_KEY)

    async def prune(
        self,
        cutoff_at: int,
        *,
        pruned_at: int | None = None,
    ) -> DedupPruneResult:
        timestamp = int(time.time()) if pruned_at is None else int(pruned_at)
        return await asyncio.to_thread(self._prune, int(cutoff_at), timestamp)

    def _prune(self, cutoff_at: int, pruned_at: int) -> DedupPruneResult:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS processed_events_dedup_floor_guard
                BEFORE INSERT ON processed_events
                WHEN EXISTS (
                    SELECT 1
                    FROM usage_meta
                    WHERE key = '{DEDUP_FLOOR_KEY}'
                      AND NEW.event_at <= CAST(value AS INTEGER)
                )
                BEGIN
                    SELECT RAISE(IGNORE);
                END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS sender_processed_events_dedup_floor_guard
                BEFORE INSERT ON sender_processed_events
                WHEN EXISTS (
                    SELECT 1
                    FROM usage_meta
                    WHERE key = '{DEDUP_FLOOR_KEY}'
                      AND NEW.event_at <= CAST(value AS INTEGER)
                )
                BEGIN
                    SELECT RAISE(IGNORE);
                END
                """
            )

            existing_floor = self._meta_int(connection, DEDUP_FLOOR_KEY)
            floor_at = max(cutoff_at, existing_floor if existing_floor is not None else 0)
            connection.execute(
                """
                INSERT INTO usage_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (DEDUP_FLOOR_KEY, str(floor_at)),
            )

            processed = connection.execute(
                "DELETE FROM processed_events WHERE event_at <= ?",
                (floor_at,),
            ).rowcount
            sender_processed = connection.execute(
                "DELETE FROM sender_processed_events WHERE event_at <= ?",
                (floor_at,),
            ).rowcount

            connection.execute(
                """
                INSERT INTO usage_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (DEDUP_LAST_PRUNED_KEY, str(pruned_at)),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return DedupPruneResult(
            floor_at=floor_at,
            processed_events=max(0, int(processed)),
            sender_processed_events=max(0, int(sender_processed)),
        )
