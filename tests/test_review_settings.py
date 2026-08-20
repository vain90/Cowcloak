from moolias.review_settings import AliasReviewSettingsStore


async def test_ignore_unexpected_setting_is_persistent_per_alias(tmp_path):
    store = AliasReviewSettingsStore(tmp_path / "usage.sqlite3")

    assert await store.ignored_aliases("user@example.org") == set()

    await store.set_ignore_unexpected(
        "user@example.org",
        "newsletter-k7@example.org",
        True,
    )

    assert await store.ignored_aliases("USER@example.org") == {
        "newsletter-k7@example.org"
    }


async def test_reenabling_unexpected_monitoring_removes_setting(tmp_path):
    store = AliasReviewSettingsStore(tmp_path / "usage.sqlite3")
    await store.set_ignore_unexpected(
        "user@example.org",
        "newsletter-k7@example.org",
        True,
    )

    await store.set_ignore_unexpected(
        "user@example.org",
        "NEWSLETTER-k7@example.org",
        False,
    )

    assert await store.ignored_aliases("user@example.org") == set()


async def test_settings_are_isolated_by_mailbox(tmp_path):
    store = AliasReviewSettingsStore(tmp_path / "usage.sqlite3")
    await store.set_ignore_unexpected(
        "first@example.org",
        "shared-name@example.org",
        True,
    )

    assert await store.ignored_aliases("first@example.org") == {
        "shared-name@example.org"
    }
    assert await store.ignored_aliases("second@example.org") == set()
