from moolias.i18n import detect_language, translations


def test_cookie_language_wins_over_browser_language():
    assert detect_language("de", "en-US,en;q=0.9") == "de"
    assert detect_language("en", "de-DE,de;q=0.9") == "en"


def test_only_german_browser_preference_switches_to_german():
    assert detect_language(None, "de-DE,de;q=0.9,en;q=0.8") == "de"
    assert detect_language(None, "es-ES,es;q=0.9,de;q=0.8") == "en"
    assert detect_language(None, None) == "en"


def test_translations_fall_back_to_english():
    assert translations("de")["sign_in"] == "Mit mailcow anmelden"
    assert translations("unsupported")["sign_in"] == "Sign in with mailcow"
