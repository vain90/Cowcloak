from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceIcon:
    key: str
    label: str
    glyph: str
    tone: str
    keywords: tuple[str, ...] = ()


_GENERIC = ServiceIcon("generic", "Allgemein", "?", "neutral")

SERVICE_ICONS: tuple[ServiceIcon, ...] = (
    ServiceIcon("amazon", "Amazon", "A", "orange", ("amazon", "aws")),
    ServiceIcon("apple", "Apple", "A", "dark", ("apple", "icloud", "appstore")),
    ServiceIcon("booking", "Booking.com", "B", "blue", ("booking", "bookingcom")),
    ServiceIcon("discord", "Discord", "D", "violet", ("discord",)),
    ServiceIcon("dropbox", "Dropbox", "D", "blue", ("dropbox",)),
    ServiceIcon("ebay", "eBay", "e", "multi", ("ebay",)),
    ServiceIcon("facebook", "Facebook", "f", "blue", ("facebook", "meta")),
    ServiceIcon("github", "GitHub", "G", "dark", ("github",)),
    ServiceIcon("gitlab", "GitLab", "G", "orange", ("gitlab",)),
    ServiceIcon("google", "Google", "G", "multi", ("google", "gmail", "youtube")),
    ServiceIcon("instagram", "Instagram", "I", "pink", ("instagram",)),
    ServiceIcon("linkedin", "LinkedIn", "in", "blue", ("linkedin",)),
    ServiceIcon("microsoft", "Microsoft", "M", "blue", ("microsoft", "office", "outlook", "azure")),
    ServiceIcon("netflix", "Netflix", "N", "red", ("netflix",)),
    ServiceIcon("notion", "Notion", "N", "dark", ("notion",)),
    ServiceIcon("openai", "OpenAI", "O", "teal", ("openai", "chatgpt")),
    ServiceIcon("paypal", "PayPal", "P", "blue", ("paypal",)),
    ServiceIcon("reddit", "Reddit", "r", "orange", ("reddit",)),
    ServiceIcon("signal", "Signal", "S", "blue", ("signal",)),
    ServiceIcon("slack", "Slack", "S", "multi", ("slack",)),
    ServiceIcon("spotify", "Spotify", "S", "green", ("spotify",)),
    ServiceIcon("steam", "Steam", "S", "blue", ("steam",)),
    ServiceIcon("stripe", "Stripe", "S", "violet", ("stripe",)),
    ServiceIcon("telegram", "Telegram", "T", "blue", ("telegram",)),
    ServiceIcon("tiktok", "TikTok", "T", "dark", ("tiktok",)),
    ServiceIcon("twitch", "Twitch", "T", "violet", ("twitch",)),
    ServiceIcon("x", "X / Twitter", "X", "dark", ("twitter", "xcom")),
    ServiceIcon("zalando", "Zalando", "Z", "orange", ("zalando",)),
    ServiceIcon("zoom", "Zoom", "Z", "blue", ("zoom",)),
)

_ICON_BY_KEY = {icon.key: icon for icon in SERVICE_ICONS}


def icon_catalog() -> tuple[ServiceIcon, ...]:
    return (_GENERIC, *SERVICE_ICONS)


def icon_by_key(key: str | None) -> ServiceIcon:
    if not key:
        return _GENERIC
    return _ICON_BY_KEY.get(key.strip().lower(), _GENERIC)


def detect_service_icon(address: str, description: str = "") -> ServiceIcon:
    local_part = address.partition("@")[0]
    haystack = f"{description} {local_part}".casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", haystack)
    tokens = set(normalized.split())
    compact = normalized.replace(" ", "")

    for icon in SERVICE_ICONS:
        for keyword in icon.keywords:
            folded = keyword.casefold()
            if folded in tokens or (len(folded) >= 4 and folded in compact):
                return icon
    return _GENERIC


def resolve_service_icon(
    address: str,
    description: str,
    override: str | None,
) -> ServiceIcon:
    if override and override != "auto":
        return icon_by_key(override)
    return detect_service_icon(address, description)
