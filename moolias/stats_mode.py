from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class StatsMode(StrEnum):
    OFF = "off"
    BASIC = "basic"
    DOMAIN = "domain"
    FULL = "full"


class StatsModeSource(StrEnum):
    NONE = "none"
    DOMAIN = "domain"
    MAILBOX = "mailbox"


@dataclass(frozen=True, slots=True)
class StatsModeState:
    effective: StatsMode
    source: StatsModeSource
    mailbox_override: StatsMode | None
    domain_default: StatsMode | None
    conflict: bool = False
    conflict_source: StatsModeSource | None = None

    @property
    def enabled(self) -> bool:
        return self.effective is not StatsMode.OFF

    @property
    def sender_detail_enabled(self) -> bool:
        return self.effective in {StatsMode.DOMAIN, StatsMode.FULL}


def normalise_tags(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set, frozenset)):
        entries = value
    elif isinstance(value, str):
        entries = value.split(",")
    else:
        return set()
    return {str(tag).strip().casefold() for tag in entries if str(tag).strip()}


def stats_mode_tags(base_tag: str) -> dict[StatsMode, str]:
    base = base_tag.strip().casefold()
    if not base:
        raise ValueError("Statistics base tag must not be empty")
    return {
        StatsMode.OFF: f"{base}-off",
        StatsMode.BASIC: base,
        StatsMode.DOMAIN: f"{base}-domain",
        StatsMode.FULL: f"{base}-full",
    }


def stats_mode_rank(mode: StatsMode) -> int:
    return {
        StatsMode.OFF: 0,
        StatsMode.BASIC: 1,
        StatsMode.DOMAIN: 2,
        StatsMode.FULL: 3,
    }[mode]


def selected_effective_mode(
    selection: str,
    domain_default: StatsMode | None,
) -> StatsMode:
    if selection == "inherit":
        return domain_default or StatsMode.OFF
    try:
        return StatsMode(selection)
    except ValueError as exc:
        raise ValueError(f"Unknown statistics mode: {selection}") from exc


def is_stats_mode_downgrade(current: StatsMode, target: StatsMode) -> bool:
    return stats_mode_rank(target) < stats_mode_rank(current)


def _explicit_mode(tags: Any, base_tag: str) -> tuple[StatsMode | None, bool]:
    configured = normalise_tags(tags)
    matches = [mode for mode, tag in stats_mode_tags(base_tag).items() if tag in configured]
    if len(matches) == 1:
        return matches[0], False
    if len(matches) > 1:
        return None, True
    return None, False


def resolve_stats_mode(
    mailbox_tags: Any,
    domain_tags: Any,
    base_tag: str,
) -> StatsModeState:
    mailbox_mode, mailbox_conflict = _explicit_mode(mailbox_tags, base_tag)
    domain_mode, domain_conflict = _explicit_mode(domain_tags, base_tag)

    if mailbox_conflict:
        return StatsModeState(
            effective=StatsMode.OFF,
            source=StatsModeSource.MAILBOX,
            mailbox_override=None,
            domain_default=domain_mode,
            conflict=True,
            conflict_source=StatsModeSource.MAILBOX,
        )
    if mailbox_mode is not None:
        return StatsModeState(
            effective=mailbox_mode,
            source=StatsModeSource.MAILBOX,
            mailbox_override=mailbox_mode,
            domain_default=domain_mode,
        )
    if domain_conflict:
        return StatsModeState(
            effective=StatsMode.OFF,
            source=StatsModeSource.DOMAIN,
            mailbox_override=None,
            domain_default=None,
            conflict=True,
            conflict_source=StatsModeSource.DOMAIN,
        )
    if domain_mode is not None:
        return StatsModeState(
            effective=domain_mode,
            source=StatsModeSource.DOMAIN,
            mailbox_override=None,
            domain_default=domain_mode,
        )
    return StatsModeState(
        effective=StatsMode.OFF,
        source=StatsModeSource.NONE,
        mailbox_override=None,
        domain_default=None,
    )


def replace_mailbox_stats_tags(
    existing_tags: Iterable[str] | str | None,
    base_tag: str,
    selection: str,
) -> list[str]:
    if isinstance(existing_tags, str):
        original = [tag.strip() for tag in existing_tags.split(",") if tag.strip()]
    else:
        original = [str(tag).strip() for tag in (existing_tags or []) if str(tag).strip()]

    family = set(stats_mode_tags(base_tag).values())
    preserved = [tag for tag in original if tag.casefold() not in family]

    if selection == "inherit":
        return preserved

    mode = selected_effective_mode(selection, None)
    preserved.append(stats_mode_tags(base_tag)[mode])
    return preserved
