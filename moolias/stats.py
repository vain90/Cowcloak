from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from moolias.stats_mode import StatsMode, is_stats_mode_downgrade

SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class UsageEvent:
    event_key: str
    mailbox: str
    alias: str
    event_at: int


@dataclass(frozen=True, slots=True)
class SenderEvent:
    event_key: str
    mailbox: str
    alias: str
    sender_domain: str
    sender_address: str | None
    mode: str
    event_at: int


@dataclass(frozen=True, slots=True)
class AliasUsage:
    received_count: int = 0
    sent_count: int = 0
    last_received_at: int | None = None
    last_sent_at: int | None = None


@dataclass(frozen=True, slots=True)
class SenderUsage:
    sender_key: str
    sender_domain: str
    sender_address: str | None
    received_count: int
    last_received_at: int | None
    manual_expected: bool | None = None


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
            if version == 1:
                self._migrate_v1_to_v2(connection)
                version = 2
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
        connection.execute("PRAGMA user_version = 1")

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sender_mode_state (
                mailbox TEXT PRIMARY KEY COLLATE NOCASE,
                mode TEXT NOT NULL,
                tracking_started_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sender_usage (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                sender_key TEXT NOT NULL COLLATE NOCASE,
                sender_domain TEXT NOT NULL COLLATE NOCASE,
                sender_address TEXT COLLATE NOCASE,
                received_count INTEGER NOT NULL DEFAULT 0,
                last_received_at INTEGER,
                PRIMARY KEY (mailbox, alias, sender_key)
            );

            CREATE INDEX IF NOT EXISTS sender_usage_mailbox_alias_idx
                ON sender_usage (mailbox, alias);

            CREATE TABLE IF NOT EXISTS sender_processed_events (
                event_key TEXT PRIMARY KEY,
                event_at INTEGER NOT NULL,
                mailbox TEXT NOT NULL COLLATE NOCASE
            );

            CREATE INDEX IF NOT EXISTS sender_processed_events_mailbox_idx
                ON sender_processed_events (mailbox);
            CREATE INDEX IF NOT EXISTS sender_processed_events_event_at_idx
                ON sender_processed_events (event_at);

            CREATE TABLE IF NOT EXISTS sender_expectations (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                sender_key TEXT NOT NULL COLLATE NOCASE,
                expected INTEGER NOT NULL CHECK (expected IN (0, 1)),
                PRIMARY KEY (mailbox, alias, sender_key)
            );

            CREATE TABLE IF NOT EXISTS sender_alias_settings (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                ignore_unexpected INTEGER NOT NULL DEFAULT 0
                    CHECK (ignore_unexpected IN (0, 1)),
                PRIMARY KEY (mailbox, alias)
            );

            CREATE TABLE IF NOT EXISTS collector_health (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_attempt_at INTEGER,
                last_success_at INTEGER,
                last_error TEXT,
                last_duration_ms INTEGER,
                poll_interval_seconds INTEGER,
                history_limit INTEGER,
                history_count INTEGER,
                oldest_event_at INTEGER,
                newest_event_at INTEGER,
                previous_watermark INTEGER,
                watermark INTEGER,
                overlap_count INTEGER,
                headroom_percent REAL,
                coverage_state TEXT
            );
            """
        )
        connection.execute("PRAGMA user_version = 2")

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

    async def sender_mode(self, mailbox: str) -> str | None:
        return await asyncio.to_thread(self._sender_mode, mailbox)

    def _sender_mode(self, mailbox: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT mode FROM sender_mode_state WHERE mailbox = ?",
                (mailbox.lower(),),
            ).fetchone()
        return str(row["mode"]) if row is not None else None

    async def sync_sender_modes(
        self,
        modes: dict[str, str],
        *,
        now: int | None = None,
    ) -> dict[str, int]:
        if not modes:
            return {}
        timestamp = int(time.time()) if now is None else int(now)
        return await asyncio.to_thread(self._sync_sender_modes, modes, timestamp)

    def _sync_sender_modes(self, modes: dict[str, str], now: int) -> dict[str, int]:
        starts: dict[str, int] = {}
        with self._connect() as connection:
            initial_row = connection.execute(
                "SELECT value FROM usage_meta WHERE key = ?",
                ("tracking_started_at",),
            ).fetchone()
            initial_start = int(initial_row["value"]) if initial_row is not None else now

            for mailbox, mode in modes.items():
                mailbox = mailbox.lower()
                target_mode = StatsMode(mode)
                row = connection.execute(
                    "SELECT mode, tracking_started_at FROM sender_mode_state WHERE mailbox = ?",
                    (mailbox,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO sender_mode_state (mailbox, mode, tracking_started_at)
                        VALUES (?, ?, ?)
                        """,
                        (mailbox, mode, initial_start),
                    )
                    starts[mailbox] = initial_start
                    continue

                current_mode = StatsMode(str(row["mode"]))
                current_start = int(row["tracking_started_at"])
                if current_mode is target_mode:
                    starts[mailbox] = current_start
                    continue

                if is_stats_mode_downgrade(current_mode, target_mode):
                    if current_mode is StatsMode.FULL and target_mode is StatsMode.DOMAIN:
                        domain_rows = connection.execute(
                            """
                            SELECT
                                alias,
                                sender_domain,
                                SUM(received_count) AS received_count,
                                MAX(last_received_at) AS last_received_at
                            FROM sender_usage
                            WHERE mailbox = ?
                            GROUP BY alias, sender_domain
                            """,
                            (mailbox,),
                        ).fetchall()
                        expectation_rows = connection.execute(
                            """
                            SELECT
                                s.alias,
                                s.sender_domain,
                                MIN(COALESCE(exact_e.expected, domain_e.expected)) AS min_expected,
                                MAX(COALESCE(exact_e.expected, domain_e.expected)) AS max_expected,
                                COUNT(
                                    COALESCE(exact_e.expected, domain_e.expected)
                                ) AS reviewed_count,
                                COUNT(*) AS sender_count
                            FROM sender_usage AS s
                            LEFT JOIN sender_expectations AS exact_e
                                ON exact_e.mailbox = s.mailbox
                                AND exact_e.alias = s.alias
                                AND exact_e.sender_key = s.sender_key
                            LEFT JOIN sender_expectations AS domain_e
                                ON domain_e.mailbox = s.mailbox
                                AND domain_e.alias = s.alias
                                AND domain_e.sender_key = s.sender_domain
                            WHERE s.mailbox = ?
                            GROUP BY s.alias, s.sender_domain
                            """,
                            (mailbox,),
                        ).fetchall()

                        connection.execute(
                            "DELETE FROM sender_usage WHERE mailbox = ?",
                            (mailbox,),
                        )
                        connection.execute(
                            "DELETE FROM sender_expectations WHERE mailbox = ?",
                            (mailbox,),
                        )

                        connection.executemany(
                            """
                            INSERT INTO sender_usage (
                                mailbox,
                                alias,
                                sender_key,
                                sender_domain,
                                sender_address,
                                received_count,
                                last_received_at
                            ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                            """,
                            [
                                (
                                    mailbox,
                                    str(item["alias"]).lower(),
                                    str(item["sender_domain"]).lower(),
                                    str(item["sender_domain"]).lower(),
                                    int(item["received_count"]),
                                    (
                                        int(item["last_received_at"])
                                        if item["last_received_at"] is not None
                                        else None
                                    ),
                                )
                                for item in domain_rows
                            ],
                        )

                        for item in expectation_rows:
                            if int(item["reviewed_count"]) != int(item["sender_count"]):
                                continue
                            if item["min_expected"] != item["max_expected"]:
                                continue
                            connection.execute(
                                """
                                INSERT INTO sender_expectations (
                                    mailbox,
                                    alias,
                                    sender_key,
                                    expected
                                ) VALUES (?, ?, ?, ?)
                                """,
                                (
                                    mailbox,
                                    str(item["alias"]).lower(),
                                    str(item["sender_domain"]).lower(),
                                    int(item["min_expected"]),
                                ),
                            )
                    else:
                        connection.execute(
                            "DELETE FROM sender_usage WHERE mailbox = ?",
                            (mailbox,),
                        )
                        connection.execute(
                            "DELETE FROM sender_expectations WHERE mailbox = ?",
                            (mailbox,),
                        )

                    connection.execute(
                        "DELETE FROM sender_processed_events WHERE mailbox = ?",
                        (mailbox,),
                    )
                    if target_mode is StatsMode.OFF:
                        connection.execute("DELETE FROM alias_usage WHERE mailbox = ?", (mailbox,))

                connection.execute(
                    """
                    UPDATE sender_mode_state
                    SET mode = ?, tracking_started_at = ?
                    WHERE mailbox = ?
                    """,
                    (mode, now, mailbox),
                )
                starts[mailbox] = now
        return starts

    async def record_received(self, events: list[UsageEvent]) -> int:
        if not events:
            return 0
        return await asyncio.to_thread(self._record_events, events, "received")

    async def record_sent(self, events: list[UsageEvent]) -> int:
        if not events:
            return 0
        return await asyncio.to_thread(self._record_events, events, "sent")

    def _record_events(self, events: list[UsageEvent], kind: str) -> int:
        if kind not in {"received", "sent"}:
            raise ValueError(f"Unsupported usage event kind: {kind}")

        count_column = "received_count" if kind == "received" else "sent_count"
        timestamp_column = "last_received_at" if kind == "received" else "last_sent_at"
        received_count = 1 if kind == "received" else 0
        sent_count = 1 if kind == "sent" else 0
        last_received = "?" if kind == "received" else "NULL"
        last_sent = "?" if kind == "sent" else "NULL"

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
                    f"""
                    INSERT INTO alias_usage (
                        mailbox,
                        alias,
                        received_count,
                        sent_count,
                        last_received_at,
                        last_sent_at
                    )
                    VALUES (?, ?, {received_count}, {sent_count}, {last_received}, {last_sent})
                    ON CONFLICT(mailbox, alias) DO UPDATE SET
                        {count_column} = alias_usage.{count_column} + 1,
                        {timestamp_column} = MAX(
                            COALESCE(
                                alias_usage.{timestamp_column},
                                excluded.{timestamp_column}
                            ),
                            excluded.{timestamp_column}
                        )
                    """,
                    [event.mailbox, event.alias, event.event_at],
                )
                recorded += 1
        return recorded

    async def record_senders(self, events: list[SenderEvent]) -> int:
        if not events:
            return 0
        return await asyncio.to_thread(self._record_senders, events)

    def _record_senders(self, events: list[SenderEvent]) -> int:
        recorded = 0
        with self._connect() as connection:
            for event in events:
                current_mode = connection.execute(
                    "SELECT mode FROM sender_mode_state WHERE mailbox = ?",
                    (event.mailbox.lower(),),
                ).fetchone()
                if current_mode is None or str(current_mode["mode"]) != event.mode:
                    continue

                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO sender_processed_events (
                        event_key,
                        event_at,
                        mailbox
                    ) VALUES (?, ?, ?)
                    """,
                    (event.event_key, event.event_at, event.mailbox),
                )
                if inserted.rowcount != 1:
                    continue

                sender_key = event.sender_address or event.sender_domain
                connection.execute(
                    """
                    INSERT INTO sender_usage (
                        mailbox,
                        alias,
                        sender_key,
                        sender_domain,
                        sender_address,
                        received_count,
                        last_received_at
                    )
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(mailbox, alias, sender_key) DO UPDATE SET
                        received_count = sender_usage.received_count + 1,
                        last_received_at = MAX(
                            COALESCE(sender_usage.last_received_at, excluded.last_received_at),
                            excluded.last_received_at
                        )
                    """,
                    (
                        event.mailbox,
                        event.alias,
                        sender_key,
                        event.sender_domain,
                        event.sender_address,
                        event.event_at,
                    ),
                )
                recorded += 1
        return recorded

    async def set_sender_expectation(
        self,
        mailbox: str,
        alias: str,
        sender_key: str,
        expected: bool | None,
    ) -> None:
        await asyncio.to_thread(
            self._set_sender_expectation,
            mailbox,
            alias,
            sender_key,
            expected,
        )

    def _set_sender_expectation(
        self,
        mailbox: str,
        alias: str,
        sender_key: str,
        expected: bool | None,
    ) -> None:
        mailbox = mailbox.lower()
        alias = alias.lower()
        sender_key = sender_key.lower()
        with self._connect() as connection:
            if expected is None:
                exact = connection.execute(
                    """
                    SELECT 1
                    FROM sender_expectations
                    WHERE mailbox = ? AND alias = ? AND sender_key = ?
                    """,
                    (mailbox, alias, sender_key),
                ).fetchone()
                if exact is not None:
                    connection.execute(
                        """
                        DELETE FROM sender_expectations
                        WHERE mailbox = ? AND alias = ? AND sender_key = ?
                        """,
                        (mailbox, alias, sender_key),
                    )
                    return

                if "@" in sender_key:
                    sender_key = sender_key.rsplit("@", 1)[1]
                connection.execute(
                    """
                    DELETE FROM sender_expectations
                    WHERE mailbox = ? AND alias = ? AND sender_key = ?
                    """,
                    (mailbox, alias, sender_key),
                )
                return
            connection.execute(
                """
                INSERT INTO sender_expectations (mailbox, alias, sender_key, expected)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(mailbox, alias, sender_key) DO UPDATE SET
                    expected = excluded.expected
                """,
                (mailbox, alias, sender_key, 1 if expected else 0),
            )

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
                last_sent_at=(
                    int(row["last_sent_at"])
                    if row["last_sent_at"] is not None
                    else None
                ),
            )
            for row in rows
        }

    async def sender_usage(
        self,
        mailbox: str,
        aliases: list[str],
    ) -> dict[str, list[SenderUsage]]:
        if not aliases:
            return {}
        return await asyncio.to_thread(self._sender_usage, mailbox, aliases)

    def _sender_usage(
        self,
        mailbox: str,
        aliases: list[str],
    ) -> dict[str, list[SenderUsage]]:
        placeholders = ",".join("?" for _ in aliases)
        params = [mailbox.lower(), *(alias.lower() for alias in aliases)]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    s.alias,
                    s.sender_key,
                    s.sender_domain,
                    s.sender_address,
                    s.received_count,
                    s.last_received_at,
                    exact_e.expected AS exact_expected,
                    domain_e.expected AS domain_expected
                FROM sender_usage AS s
                LEFT JOIN sender_expectations AS exact_e
                    ON exact_e.mailbox = s.mailbox
                    AND exact_e.alias = s.alias
                    AND exact_e.sender_key = s.sender_key
                LEFT JOIN sender_expectations AS domain_e
                    ON domain_e.mailbox = s.mailbox
                    AND domain_e.alias = s.alias
                    AND domain_e.sender_key = s.sender_domain
                WHERE s.mailbox = ? AND s.alias IN ({placeholders})
                ORDER BY s.alias, s.last_received_at DESC, s.sender_key
                """,
                params,
            ).fetchall()

        result: dict[str, list[SenderUsage]] = {}
        for row in rows:
            alias = str(row["alias"]).lower()
            exact_expected = row["exact_expected"]
            domain_expected = row["domain_expected"]
            manual_expected = exact_expected if exact_expected is not None else domain_expected
            result.setdefault(alias, []).append(
                SenderUsage(
                    sender_key=str(row["sender_key"]).lower(),
                    sender_domain=str(row["sender_domain"]).lower(),
                    sender_address=(
                        str(row["sender_address"]).lower()
                        if row["sender_address"] is not None
                        else None
                    ),
                    received_count=int(row["received_count"]),
                    last_received_at=(
                        int(row["last_received_at"])
                        if row["last_received_at"] is not None
                        else None
                    ),
                    manual_expected=(
                        bool(manual_expected) if manual_expected is not None else None
                    ),
                )
            )
        return result
