import sqlite3

from cowcloak.stats import StatsStore


async def test_sender_tables_keep_schema_v1_user_version(tmp_path):
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

    assert version == 1
    assert "sender_usage" in tables
    assert "sender_expectations" in tables
    assert "sender_mode_state" in tables
