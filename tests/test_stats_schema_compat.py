import sqlite3

from moolias.stats import StatsStore


def create_schema_v1(path) -> None:
    with sqlite3.connect(path) as connection:
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
            PRAGMA user_version = 1;
            """
        )
        connection.execute(
            "INSERT INTO usage_meta (key, value) VALUES (?, ?)",
            ("tracking_started_at", "123"),
        )
        connection.execute(
            """
            INSERT INTO alias_usage (
                mailbox, alias, received_count, sent_count, last_received_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("user@example.org", "shop@example.org", 2, 1, 120),
        )


async def test_fresh_statistics_database_uses_schema_v2(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    store = StatsStore(str(db_path))
    await store.initialize()

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version == 2
    assert {
        "usage_meta",
        "alias_usage",
        "processed_events",
        "sender_usage",
        "sender_expectations",
        "sender_mode_state",
        "sender_processed_events",
        "sender_alias_settings",
        "collector_health",
    }.issubset(tables)


async def test_schema_v1_migrates_to_v2_without_losing_usage(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    create_schema_v1(db_path)

    store = StatsStore(str(db_path))
    await store.initialize()

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        row = connection.execute(
            """
            SELECT received_count, sent_count, last_received_at
            FROM alias_usage
            WHERE mailbox = ? AND alias = ?
            """,
            ("user@example.org", "shop@example.org"),
        ).fetchone()
        collector_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'collector_health'"
        ).fetchone()

    assert version == 2
    assert row == (2, 1, 120)
    assert collector_table is not None
