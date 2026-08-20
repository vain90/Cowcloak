from moolias.stats import SenderEvent, StatsStore, UsageEvent


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


async def test_domain_full_domain_roundtrip_redacts_and_aggregates_sender_addresses(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    alias = "amazon-k7@example.org"
    mailbox = "user@example.org"

    await store.sync_sender_modes({mailbox: "domain"}, now=100)
    assert await store.record_senders(
        [
            SenderEvent(
                event_key="domain-before-upgrade",
                mailbox=mailbox,
                alias=alias,
                sender_domain="amazon.de",
                sender_address=None,
                mode="domain",
                event_at=101,
            )
        ]
    ) == 1
    await store.set_sender_expectation(mailbox, alias, "amazon.de", True)

    await store.sync_sender_modes({mailbox: "full"}, now=200)
    assert await store.record_senders(
        [
            SenderEvent(
                event_key="full-amazon-news",
                mailbox=mailbox,
                alias=alias,
                sender_domain="amazon.de",
                sender_address="news@amazon.de",
                mode="full",
                event_at=201,
            ),
            SenderEvent(
                event_key="full-amazon-deals",
                mailbox=mailbox,
                alias=alias,
                sender_domain="amazon.de",
                sender_address="deals@amazon.de",
                mode="full",
                event_at=202,
            ),
            SenderEvent(
                event_key="full-other",
                mailbox=mailbox,
                alias=alias,
                sender_domain="other.example",
                sender_address="alert@other.example",
                mode="full",
                event_at=203,
            ),
        ]
    ) == 3
    await store.set_sender_expectation(mailbox, alias, "news@amazon.de", True)
    await store.set_sender_expectation(mailbox, alias, "deals@amazon.de", True)
    await store.set_sender_expectation(mailbox, alias, "alert@other.example", False)

    await store.sync_sender_modes({mailbox: "domain"}, now=300)

    usage = await store.sender_usage(mailbox, [alias])
    rows = {row.sender_key: row for row in usage[alias]}

    assert set(rows) == {"amazon.de", "other.example"}
    assert rows["amazon.de"].sender_address is None
    assert rows["amazon.de"].received_count == 3
    assert rows["amazon.de"].last_received_at == 202
    assert rows["amazon.de"].manual_expected is True
    assert rows["other.example"].sender_address is None
    assert rows["other.example"].received_count == 1
    assert rows["other.example"].manual_expected is False


async def test_full_to_domain_drops_conflicting_address_reviews(tmp_path):
    store = StatsStore(str(tmp_path / "usage.sqlite3"))
    await store.initialize()
    alias = "amazon-k7@example.org"
    mailbox = "user@example.org"
    await store.sync_sender_modes({mailbox: "full"}, now=100)

    assert await store.record_senders(
        [
            SenderEvent(
                event_key="full-1",
                mailbox=mailbox,
                alias=alias,
                sender_domain="amazon.de",
                sender_address="one@amazon.de",
                mode="full",
                event_at=101,
            ),
            SenderEvent(
                event_key="full-2",
                mailbox=mailbox,
                alias=alias,
                sender_domain="amazon.de",
                sender_address="two@amazon.de",
                mode="full",
                event_at=102,
            ),
        ]
    ) == 2
    await store.set_sender_expectation(mailbox, alias, "one@amazon.de", True)
    await store.set_sender_expectation(mailbox, alias, "two@amazon.de", False)

    await store.sync_sender_modes({mailbox: "domain"}, now=200)

    usage = await store.sender_usage(mailbox, [alias])
    row = usage[alias][0]
    assert row.sender_key == "amazon.de"
    assert row.sender_address is None
    assert row.received_count == 2
    assert row.manual_expected is None


async def test_full_to_basic_removes_sender_details_and_reviews(tmp_path):
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

    await store.sync_sender_modes({"user@example.org": "basic"}, now=200)

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
