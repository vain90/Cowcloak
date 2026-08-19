import pytest

from cowcloak.aliases import (
    RESERVED_COMMENT,
    AliasRecord,
    is_mailbox_catch_all,
    is_owned_alias,
    is_primary_mailbox_alias,
    load_words,
    mailbox_domain,
    readable_local_part,
    slugify,
    validate_local_part,
)


def test_mailbox_domain_is_derived_from_login():
    assert mailbox_domain("Hidden.PK@Sky-Post.de") == "sky-post.de"


def test_slugify_is_stable_and_ascii():
    assert slugify("Müller & Amazon Privat") == "muller-amazon-privat"


def test_local_part_is_conservative():
    assert validate_local_part("amazon-k7p4") == "amazon-k7p4"
    with pytest.raises(ValueError):
        validate_local_part("Not Allowed!")


@pytest.mark.parametrize("language", ["de", "en"])
def test_wordlists_are_short_unique_and_varied(language: str):
    words = load_words(language)
    assert 200 <= len(words) <= 250
    assert len(words) == len(set(words))
    assert max(map(len, words)) <= 6


@pytest.mark.parametrize("language", ["de", "en"])
def test_readable_aliases_are_compact_valid_local_parts(language: str):
    for _ in range(100):
        local_part = readable_local_part(language)
        parts = local_part.split("-")
        assert len(parts) == 3
        assert len(parts[0]) <= 6
        assert len(parts[1]) <= 6
        assert len(parts[2]) == 2 and parts[2].isdigit()
        assert len(local_part) <= 16
        assert validate_local_part(local_part) == local_part


def test_owned_alias_requires_exact_single_target_and_same_domain():
    alias = AliasRecord(
        id=1,
        address="amazon-k7p4@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="Admin-only note",
        public_comment="Amazon",
        sogo_visible=True,
    )
    assert alias.description == "Amazon"
    assert is_owned_alias(alias, "hidden@example.org")
    assert not is_owned_alias(alias, "other@example.org")

    shared = AliasRecord(
        id=2,
        address="shared@example.org",
        goto="hidden@example.org,other@example.org",
        domain="example.org",
        active=True,
        private_comment="Shared admin note",
        public_comment="Shared",
    )
    assert not is_owned_alias(shared, "hidden@example.org")


def test_primary_mailbox_alias_is_detected_separately():
    primary = AliasRecord(
        id=7,
        address="hidden@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="",
        sender_allowed=False,
    )
    assert is_primary_mailbox_alias(primary, "hidden@example.org")
    assert not is_primary_mailbox_alias(primary, "other@example.org")


def test_active_catch_all_for_mailbox_is_detected_without_exposing_targets():
    catch_all = AliasRecord(
        id=8,
        address="@example.org",
        goto="hidden@example.org,other@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="",
        is_catch_all=True,
    )
    assert is_mailbox_catch_all(catch_all, "hidden@example.org")
    assert is_mailbox_catch_all(catch_all, "other@example.org")
    assert not is_mailbox_catch_all(catch_all, "nobody@example.org")

    inactive = AliasRecord(
        id=9,
        address="@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=False,
        private_comment="",
        public_comment="",
        is_catch_all=True,
    )
    assert not is_mailbox_catch_all(inactive, "hidden@example.org")


def test_private_comments_are_not_exposed_as_description():
    alias = AliasRecord(
        id=3,
        address="legacy@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="Sensitive admin note",
        public_comment="",
    )
    assert alias.description == ""


def test_current_and_legacy_offline_markers_are_recognized():
    current = AliasRecord(
        id=4,
        address="current@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment=RESERVED_COMMENT,
        public_comment="",
    )
    legacy = AliasRecord(
        id=5,
        address="legacy-pool@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="[reserved] Offline alias",
        public_comment="",
    )
    assert current.is_reserved
    assert legacy.is_reserved
