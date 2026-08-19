from cowcloak.senders import sender_match_token, sender_matches_alias


def test_service_name_matches_sender_domain_conservatively():
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


def test_hyphenated_sender_domain_can_match_service_token():
    assert sender_matches_alias(
        "amazon-k7@example.org",
        "Amazon",
        "mail-amazon.example.net",
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
