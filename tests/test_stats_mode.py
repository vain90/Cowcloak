from cowcloak.stats_mode import (
    StatsMode,
    StatsModeSource,
    replace_mailbox_stats_tags,
    resolve_stats_mode,
)


def test_mailbox_mode_overrides_domain_mode():
    state = resolve_stats_mode(
        ["cowcloak-stats-domain"],
        ["cowcloak-stats-full"],
        "cowcloak-stats",
    )

    assert state.effective is StatsMode.DOMAIN
    assert state.source is StatsModeSource.MAILBOX
    assert state.mailbox_override is StatsMode.DOMAIN
    assert state.domain_default is StatsMode.FULL


def test_mailbox_basic_and_off_are_explicit_overrides():
    basic = resolve_stats_mode(
        ["cowcloak-stats"],
        ["cowcloak-stats-full"],
        "cowcloak-stats",
    )
    off = resolve_stats_mode(
        ["cowcloak-stats-off"],
        ["cowcloak-stats-full"],
        "cowcloak-stats",
    )

    assert basic.effective is StatsMode.BASIC
    assert basic.source is StatsModeSource.MAILBOX
    assert off.effective is StatsMode.OFF
    assert off.source is StatsModeSource.MAILBOX


def test_domain_mode_is_used_without_mailbox_override():
    state = resolve_stats_mode(
        ["cowcloak", "other-tag"],
        ["cowcloak-stats-domain"],
        "cowcloak-stats",
    )

    assert state.effective is StatsMode.DOMAIN
    assert state.source is StatsModeSource.DOMAIN
    assert state.mailbox_override is None


def test_conflicting_tags_disable_stats_on_that_level():
    state = resolve_stats_mode(
        ["cowcloak-stats", "cowcloak-stats-full"],
        ["cowcloak-stats-domain"],
        "cowcloak-stats",
    )

    assert state.effective is StatsMode.OFF
    assert state.conflict
    assert state.conflict_source is StatsModeSource.MAILBOX


def test_replacing_mailbox_stats_mode_preserves_unrelated_tags():
    tags = replace_mailbox_stats_tags(
        ["cowcloak", "other-tag", "cowcloak-stats-full"],
        "cowcloak-stats",
        "domain",
    )

    assert tags == ["cowcloak", "other-tag", "cowcloak-stats-domain"]


def test_inherit_removes_only_mailbox_stats_family():
    tags = replace_mailbox_stats_tags(
        [
            "cowcloak",
            "other-tag",
            "cowcloak-stats",
            "cowcloak-stats-domain",
            "cowcloak-stats-full",
            "cowcloak-stats-off",
        ],
        "cowcloak-stats",
        "inherit",
    )

    assert tags == ["cowcloak", "other-tag"]
