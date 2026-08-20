from pathlib import Path

import pytest

from moolias.stats import SenderEvent, StatsStore

MAILBOX = "user@example.org"
ALIAS = "vendor-k7@example.org"
DOMAIN = "mailer.vendor.example"
SENDER_ONE = f"one@{DOMAIN}"
SENDER_TWO = f"two@{DOMAIN}"


async def _full_store(path: Path) -> StatsStore:
    store = StatsStore(str(path))
    await store.initialize()
    await store.sync_sender_modes({MAILBOX: "full"}, now=100)
    await store.record_senders(
        [
            SenderEvent("one", MAILBOX, ALIAS, DOMAIN, SENDER_ONE, "full", 101),
            SenderEvent("two", MAILBOX, ALIAS, DOMAIN, SENDER_TWO, "full", 102),
        ]
    )
    return store


@pytest.mark.asyncio
async def test_full_domain_expectation_applies_to_all_addresses(tmp_path: Path) -> None:
    store = await _full_store(tmp_path / "stats.sqlite3")

    await store.set_sender_expectation(MAILBOX, ALIAS, DOMAIN, True)
    rows = await store.sender_usage(MAILBOX, [ALIAS])

    assert {row.sender_key: row.manual_expected for row in rows[ALIAS]} == {
        SENDER_ONE: True,
        SENDER_TWO: True,
    }


@pytest.mark.asyncio
async def test_full_address_decision_overrides_domain_expectation(tmp_path: Path) -> None:
    store = await _full_store(tmp_path / "stats.sqlite3")
    await store.set_sender_expectation(MAILBOX, ALIAS, DOMAIN, True)

    await store.set_sender_expectation(MAILBOX, ALIAS, SENDER_ONE, False)
    rows = await store.sender_usage(MAILBOX, [ALIAS])
    assert {row.sender_key: row.manual_expected for row in rows[ALIAS]} == {
        SENDER_ONE: False,
        SENDER_TWO: True,
    }

    await store.set_sender_expectation(MAILBOX, ALIAS, SENDER_ONE, None)
    rows = await store.sender_usage(MAILBOX, [ALIAS])
    assert {row.sender_key: row.manual_expected for row in rows[ALIAS]} == {
        SENDER_ONE: True,
        SENDER_TWO: True,
    }


@pytest.mark.asyncio
async def test_clearing_domain_inherited_row_removes_domain_expectation(tmp_path: Path) -> None:
    store = await _full_store(tmp_path / "stats.sqlite3")
    await store.set_sender_expectation(MAILBOX, ALIAS, DOMAIN, True)

    await store.set_sender_expectation(MAILBOX, ALIAS, SENDER_ONE, None)
    rows = await store.sender_usage(MAILBOX, [ALIAS])

    assert all(row.manual_expected is None for row in rows[ALIAS])


@pytest.mark.asyncio
async def test_full_to_domain_preserves_only_unanimous_resolved_decision(tmp_path: Path) -> None:
    store = await _full_store(tmp_path / "conflict.sqlite3")
    await store.set_sender_expectation(MAILBOX, ALIAS, DOMAIN, True)
    await store.set_sender_expectation(MAILBOX, ALIAS, SENDER_ONE, False)

    await store.sync_sender_modes({MAILBOX: "domain"}, now=200)
    rows = await store.sender_usage(MAILBOX, [ALIAS])
    assert len(rows[ALIAS]) == 1
    assert rows[ALIAS][0].sender_key == DOMAIN
    assert rows[ALIAS][0].manual_expected is None

    store = await _full_store(tmp_path / "partial.sqlite3")
    await store.set_sender_expectation(MAILBOX, ALIAS, SENDER_ONE, True)

    await store.sync_sender_modes({MAILBOX: "domain"}, now=200)
    rows = await store.sender_usage(MAILBOX, [ALIAS])
    assert len(rows[ALIAS]) == 1
    assert rows[ALIAS][0].manual_expected is None

    store = await _full_store(tmp_path / "unanimous.sqlite3")
    await store.set_sender_expectation(MAILBOX, ALIAS, DOMAIN, True)

    await store.sync_sender_modes({MAILBOX: "domain"}, now=200)
    rows = await store.sender_usage(MAILBOX, [ALIAS])
    assert len(rows[ALIAS]) == 1
    assert rows[ALIAS][0].manual_expected is True
