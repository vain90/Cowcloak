from cowcloak.stats import SenderEvent, StatsStore, UsageEvent


async def test_sender_store_keeps_all_sender_rows_and_manual_reviews(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    await store.sync_sender_modes({"user@example.org": "full"}, now=100)

    events = [
        SenderEvent(
            event_key=f"sender-{index}",
            mailbox="user@example.org",
            alias="amazon-k7@example.org",
            sender_domain=f"sender{index}.example.net",
            sender_address=f"person{index}@sender{index}.example.net",
            mode="full",
            event_at=101 + index,
        )
        for index in range(7)
    ]

    assert await store.record_senders(events) == 7
    usage = await store.sender_usage("user@example.org", ["amazon-k7@example.org"])
    assert len(usage["amazon-k7@example.org"]) == 7

    sender_key = "person6@sender6.example.net"
    await store.set_sender_expectation(
        "user@example.org",
        "amazon-k7@example.org",
        sender_key,
        True,
    )
    usage = await store.sender_usage("user@example.org", ["amazon-k7@example.org"])
    reviewed = next(
        row
        for row in usage["amazon-k7@example.org"]
        if row.sender_key == sender_key
    )
    assert reviewed.manual_expected is True

    await store.set_sender_expectation(
        "user@example.org",
        "amazon-k7@example.org",
        sender_key,
        None,
    )
    usage = await store.sender_usage("user@example.org", ["amazon-k7@example.org"])
    reviewed = next(
        row
        for row in usage["amazon-k7@example.org"]
        if row.sender_key == sender_key
    )
    assert reviewed.manual_expected is None


async def test_mode_downgrade_removes_sender_details_and_reviews(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    await store.sync_sender_modes({"user@example.org": "full"}, now=100)

    event = SenderEvent(
        event_key="sender-1",
        mailbox="user@example.org",
        alias="amazon-k7@example.org",
        sender_domain="amazon.de",
        sender_address="news@amazon.de",
        mode="full",
        event_at=101,
    )
    assert await store.record_senders([event]) == 1
    await store.set_sender_expectation(
        "user@example.org",
        "amazon-k7@example.org",
        "news@amazon.de",
        True,
    )

    await store.sync_sender_modes({"user@example.org": "domain"}, now=200)

    assert await store.sender_usage("user@example.org", ["amazon-k7@example.org"]) == {}


async def test_turning_stats_off_deletes_alias_usage(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    await store.sync_sender_modes({"user@example.org": "basic"}, now=100)
    event = UsageEvent(
        event_key="received-1",
        mailbox="user@example.org",
        alias="amazon-k7@example.org",
        event_at=101,
    )
    assert await store.record_received([event]) == 1
    assert "amazon-k7@example.org" in await store.alias_usage(
        "user@example.org",
        ["amazon-k7@example.org"],
    )

    await store.sync_sender_modes({"user@example.org": "off"}, now=200)

    assert await store.alias_usage("user@example.org", ["amazon-k7@example.org"]) == {}


async def test_upgrade_keeps_existing_lower_detail_sender_data(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    await store.sync_sender_modes({"user@example.org": "domain"}, now=100)
    event = SenderEvent(
        event_key="domain-1",
        mailbox="user@example.org",
        alias="amazon-k7@example.org",
        sender_domain="amazon.de",
        sender_address=None,
        mode="domain",
        event_at=101,
    )
    assert await store.record_senders([event]) == 1

    await store.sync_sender_modes({"user@example.org": "full"}, now=200)

    usage = await store.sender_usage("user@example.org", ["amazon-k7@example.org"])
    assert usage["amazon-k7@example.org"][0].sender_key == "amazon.de"


async def test_stale_full_event_is_rejected_after_downgrade(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    await store.sync_sender_modes({"user@example.org": "full"}, now=100)
    await store.sync_sender_modes({"user@example.org": "domain"}, now=200)

    stale = SenderEvent(
        event_key="stale-full",
        mailbox="user@example.org",
        alias="amazon-k7@example.org",
        sender_domain="amazon.de",
        sender_address="news@amazon.de",
        mode="full",
        event_at=201,
    )
    current = SenderEvent(
        event_key="current-domain",
        mailbox="user@example.org",
        alias="amazon-k7@example.org",
        sender_domain="amazon.de",
        sender_address=None,
        mode="domain",
        event_at=202,
    )

    assert await store.record_senders([stale, current]) == 1
    usage = await store.sender_usage("user@example.org", ["amazon-k7@example.org"])
    assert usage["amazon-k7@example.org"][0].sender_key == "amazon.de"
    assert usage["amazon-k7@example.org"][0].sender_address is None
