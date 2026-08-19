from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
PROCESSED_EVENT_RETENTION_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class UsageEvent:
    event_key: str
    mailbox: str
    alias: str
    event_at: int


@dataclass(frozen=True, slots=True)
class AliasUsage:
    received_count: int = 0
    sent_count: int = 0
    last_received_at: int | None = None
    last_sent_at: int | None = None


class StatsStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Usage database schema {version} is newer than supported schema "
                    f"{SCHEMA_VERSION}"
                )
            if version == 0:
                self._create_schema_v1(connection)
                version = 1
            if version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"No migration path for usage database schema {version} to {SCHEMA_VERSION}"
                )

    @staticmethod
    def _create_schema_v1(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE usage_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE alias_usage (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                received_count INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                last_received_at INTEGER,
                last_sent_at INTEGER,
                PRIMARY KEY (mailbox, alias)
            );

            CREATE TABLE processed_events (
                event_key TEXT PRIMARY KEY,
                event_at INTEGER NOT NULL
            );

            CREATE INDEX processed_events_event_at_idx
                ON processed_events (event_at);
            """
        )
        connection.execute(
            "INSERT INTO usage_meta (key, value) VALUES (?, ?)",
            ("tracking_started_at", str(int(time.time()))),
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    async def tracking_started_at(self) -> int:
        return await asyncio.to_thread(self._tracking_started_at)

    def _tracking_started_at(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM usage_meta WHERE key = ?",
                ("tracking_started_at",),
            ).fetchone()
        if row is None:
            raise RuntimeError("Usage database does not contain tracking_started_at")
        return int(row["value"])

    async def record_received(self, events: list[UsageEvent]) -> int:
        if not events:
            return 0
        return await asyncio.to_thread(self._record_received, events)

    def _record_received(self, events: list[UsageEvent]) -> int:
        recorded = 0
        with self._connect() as connection:
            for event in events:
                inserted = connection.execute(
                    "INSERT OR IGNORE INTO processed_events (event_key, event_at) VALUES (?, ?)",
                    (event.event_key, event.event_at),
                )
                if inserted.rowcount != 1:
                    continue
                connection.execute(
                    """
                    INSERT INTO alias_usage (
                        mailbox,
                        alias,
                        received_count,
                        sent_count,
                        last_received_at,
                        last_sent_at
                    )
                    VALUES (?, ?, 1, 0, ?, NULL)
                    ON CONFLICT(mailbox, alias) DO UPDATE SET
                        received_count = alias_usage.received_count + 1,
                        last_received_at = MAX(alias_usage.last_received_at, excluded.last_received_at)
                    """,
                    (event.mailbox, event.alias, event.event_at),
                )
                recorded += 1
        return recorded

    async def alias_usage(self, mailbox: str, aliases: list[str]) -> dict[str, AliasUsage]:
        if not aliases:
            return {}
        return await asyncio.to_thread(self._alias_usage, mailbox, aliases)

    def _alias_usage(self, mailbox: str, aliases: list[str]) -> dict[str, AliasUsage]:
        placeholders = ",".join("?" for _ in aliases)
        params = [mailbox.lower(), *(alias.lower() for alias in aliases)]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT alias, received_count, sent_count, last_received_at, last_sent_at
                FROM alias_usage
                WHERE mailbox = ? AND alias IN ({placeholders})
                """,
                params,
            ).fetchall()
        return {
            str(row["alias"]).lower(): AliasUsage(
                received_count=int(row["received_count"]),
                sent_count=int(row["sent_count"]),
                last_received_at=(
                    int(row["last_received_at"]) if row["last_received_at"] is not None else None
                ),
                last_sent_at=(int(row["last_sent_at"]) if row["last_sent_at"] is not None else None),
            )
            for row in rows
        }

    async def prune_processed_events(self, now: int | None = None) -> int:
        cutoff = (now if now is not None else int(time.time())) - PROCESSED_EVENT_RETENTION_SECONDS
        return await asyncio.to_thread(self._prune_processed_events, cutoff)

    def _prune_processed_events(self, cutoff: int) -> int:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM processed_events WHERE event_at < ?",
                (cutoff,),
            )
        return max(deleted.rowcount, 0)
