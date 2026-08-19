from __future__ import annotations

import re
import unicodedata

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "alias",
        "email",
        "mail",
        "newsletter",
        "shop",
        "store",
        "info",
        "kontakt",
        "contact",
        "service",
        "support",
        "konto",
        "account",
        "login",
        "online",
        "web",
        "www",
        "app",
        "test",
    }
)


def _ascii(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(_ascii(value))
        if len(token) >= 4 and not token.isdigit() and token not in _STOPWORDS
    }


def alias_identity_tokens(alias_address: str, description: str) -> set[str]:
    local_part = alias_address.split("@", 1)[0]
    return _tokens(local_part) | _tokens(description)


def sender_domain_tokens(sender_domain: str) -> set[str]:
    labels: list[str] = []
    for label in sender_domain.strip().strip(".").split("."):
        try:
            decoded = label.encode("ascii").decode("idna")
        except (UnicodeError, UnicodeDecodeError):
            decoded = label
        labels.extend(re.split(r"[-_]", decoded))
    return _tokens(" ".join(labels))


def sender_matches_alias(
    alias_address: str,
    description: str,
    sender_domain: str,
) -> bool:
    alias_tokens = alias_identity_tokens(alias_address, description)
    if not alias_tokens:
        return False
    return bool(alias_tokens & sender_domain_tokens(sender_domain))
