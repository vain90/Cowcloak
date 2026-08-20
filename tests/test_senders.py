from cowcloak.senders import registered_domain_label, sender_match_token, sender_matches_alias


def test_service_name_matches_registered_sender_domain():
    assert sender_match_token(
        "amazon-k7@example.org",
        "Amazon",
        "amazon.de",
    ) == "amazon"
    assert sender_matches_alias(
        "amazon-k7@example.org",
        "Amazon",
        "mail.amazon.de",
    )


def test_multilabel_public_suffix_uses_registered_domain_label():
    assert registered_domain_label("service.vodafone.co.uk") == "vodafone"
    assert sender_matches_alias(
        "vodafone-k7@example.org",
        "Vodafone - MeinVodafone",
        "service.vodafone.co.uk",
    )


def test_hyphenated_or_embedded_brand_domains_do_not_auto_match():
    alias = "vodafone-k7@example.org"
    description = "Vodafone - MeinVodafone"

    assert not sender_matches_alias(alias, description, "kundenservice.vodafone-mail.com")
    assert not sender_matches_alias(alias, description, "kundenservice.vodafone-service.com")
    assert not sender_matches_alias(alias, description, "vodafone-example.com")
    assert not sender_matches_alias(alias, description, "mail-vodafone.example.net")


def test_lookalike_domains_do_not_auto_match():
    alias = "vodafone-k7@example.org"
    description = "Vodafone - MeinVodafone"

    assert not sender_matches_alias(alias, description, "kundenservice.vodafonee.com")
    assert not sender_matches_alias(alias, description, "vodaf0ne.com")


def test_brand_in_subdomain_does_not_auto_match():
    assert not sender_matches_alias(
        "vodafone-k7@example.org",
        "Vodafone - MeinVodafone",
        "vodafone.login-example.com",
    )


def test_prefix_only_match_is_not_enough():
    assert not sender_matches_alias(
        "amazon-k7@example.org",
        "Amazon",
        "amazonaws.com",
    )


def test_generic_alias_words_do_not_auto_approve_sender():
    assert not sender_matches_alias(
        "shop-k7@example.org",
        "Newsletter Shop",
        "shop.example.net",
    )


def test_unrelated_sender_remains_unexpected():
    assert not sender_matches_alias(
        "betten-leinetal@example.org",
        "Betten Leinetal",
        "gwdg.de",
    )
