import pytest

from cowcloak.aliases import (
    AliasRecord,
    is_owned_alias,
    mailbox_domain,
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


def test_owned_alias_requires_exact_single_target_and_same_domain():
    alias = AliasRecord(
        id=1,
        address="amazon-k7p4@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="Amazon",
        public_comment="",
    )
    assert is_owned_alias(alias, "hidden@example.org")
    assert not is_owned_alias(alias, "other@example.org")

    shared = AliasRecord(
        id=2,
        address="shared@example.org",
        goto="hidden@example.org,other@example.org",
        domain="example.org",
        active=True,
        private_comment="Shared",
        public_comment="",
    )
    assert not is_owned_alias(shared, "hidden@example.org")
