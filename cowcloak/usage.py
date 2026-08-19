from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from email.utils import parseaddr
from typing import Any

from cowcloak.aliases import is_owned_alias, is_primary_mailbox_alias
from cowcloak.config import Settings
from cowcloak.mailcow import MailcowClient
from cowcloak.stats import SenderEvent, StatsStore, UsageEvent
from cowcloak.stats_mode import (
    StatsMode,
    StatsModeState,
    normalise_tags,
    resolve_stats_mode,
)

LOGGER = logging.getLogger(__name__)

# These Rspamd actions still represent accepted mail. Reject/soft reject/greylist
# entries are deliberately excluded because the message was not accepted.
ACCEPTED_ACTIONS = frozenset(
    {
        "clean",
        "no action",
        "add header",
        "rewrite subject",
        "probable spam",
    }
)


def _normalise_address(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalise_recipients(value: Any) -> set[str]:
    if isinstance(value, list):
        entries = value
    elif isinstance(value, str):
        entries = value.split(",")
    else:
        return set()
    return {str(entry).strip().lower() for entry in entries if str(entry).strip()}


def _event_timestamp(item: dict[str, Any]) -> int | None:
    value = item.get("unix_time")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _event_key(kind: str, item: dict[str, Any], alias: str, event_at: int) -> str:
    # Only the SHA-256 digest is persisted. When a message ID is available it is
    # preferred over scan time so repeated Rspamd scans of the same message do not
    # inflate the counter. Raw message IDs and subjects never enter SQLite.
    message_id = str(item.get("message-id") or item.get("message_id") or "").strip()
    if message_id:
        fingerprint = {
            "kind": kind,
            "alias": alias.lower(),
            "message_id": message_id,
        }
    else:
        fingerprint = {
            "kind": kind,
            "alias": alias.lower(),
            "event_at": event_at,
            "queue_id": str(item.get("qid") or item.get("queue_id") or ""),
            "sender_smtp": str(item.get("sender_smtp") or ""),
            "sender_mime": str(item.get("sender_mime") or ""),
            "subject": str(item.get("subject") or ""),
            "user": str(item.get("user") or ""),
        }
    payload = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _sender_identity(item: dict[str, Any]) -> tuple[str, str] | None:
    raw = item.get("sender_mime") or item.get("sender_smtp")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    _, address = parseaddr(str(raw or ""))
    address = address.strip().lower()
    if "@" not in address:
        return None
    local_part, domain = address.rsplit("@", 1)
    domain = domain.strip().strip(".").lower()
    if not local_part or not domain:
        return None
    return address, domain


async def mailbox_stats_state(
    settings: Settings,
    mailcow: MailcowClient,
    email: str,
) -> StatsModeState:
    if not settings.usage_stats:
        return resolve_stats_mode([], [], settings.usage_tag)

    mailbox = await mailcow.get_mailbox(email)
    domain = str(mailbox.get("domain") or email.rsplit("@", 1)[-1]).strip().lower()
    domain_details = await mailcow.get_domain(domain)
    return resolve_stats_mode(
        mailbox.get("tags"),
        domain_details.get("tags"),
        settings.usage_tag,
    )


async def mailbox_usage_enabled(
    settings: Settings,
    mailcow: MailcowClient,
    email: str,
) -> bool:
    return (await mailbox_stats_state(settings, mailcow, email)).enabled


class UsageCollector:
    def __init__(self, settings: Settings, mailcow: MailcowClient, store: StatsStore) -> None:
        self.settings = settings
        self.mailcow = mailcow
        self.store = store
        self._reported_conflicts: set[str] = set()

    def _resolve_inventory(
        self,
        domains: list[dict[str, Any]],
        mailboxes: list[dict[str, Any]],
    ) -> dict[str, StatsModeState]:
        domain_payloads: dict[str, dict[str, Any]] = {}
        for domain_payload in domains:
            domain = str(
                domain_payload.get("domain") or domain_payload.get("domain_name") or ""
            ).strip().lower()
            if domain:
                domain_payloads[domain] = domain_payload

        access_tag = self.settings.access_tag.casefold()
        access_domains = {
            domain
            for domain, payload in domain_payloads.items()
            if access_tag and access_tag in normalise_tags(payload.get("tags"))
        }

        states: dict[str, StatsModeState] = {}
        for mailbox in mailboxes:
            username = str(mailbox.get("username") or "").strip().lower()
            if not username or "@" not in username:
                continue
            domain = str(mailbox.get("domain") or username.rsplit("@", 1)[1]).strip().lower()
            mailbox_tags = normalise_tags(mailbox.get("tags"))
            access_allowed = (
                not access_tag or access_tag in mailbox_tags or domain in access_domains
            )
            if not access_allowed:
                continue

            domain_payload = domain_payloads.get(domain, {})
            states[username] = resolve_stats_mode(
                mailbox.get("tags"),
                domain_payload.get("tags"),
                self.settings.usage_tag,
            )
        return states

    async def mailbox_states(self) -> dict[str, StatsModeState]:
        domains, mailboxes = await asyncio.gather(
            self.mailcow.list_domains(),
            self.mailcow.list_mailboxes(),
        )
        states = self._resolve_inventory(domains, mailboxes)
        self._log_new_conflicts(states)
        return states

    def _log_new_conflicts(self, states: dict[str, StatsModeState]) -> None:
        conflicts = {mailbox for mailbox, state in states.items() if state.conflict}
        for mailbox in sorted(conflicts - self._reported_conflicts):
            state = states[mailbox]
            LOGGER.warning(
                "Conflicting Cowcloak statistics tags for %s on %s level; statistics disabled",
                mailbox,
                state.conflict_source.value if state.conflict_source is not None else "unknown",
            )
        self._reported_conflicts = conflicts

    async def eligible_mailboxes(self) -> set[str]:
        return {
            mailbox
            for mailbox, state in (await self.mailbox_states()).items()
            if state.enabled
        }

    async def collect_once(self) -> int:
        tracking_started_at = await self.store.tracking_started_at()
        states = await self.mailbox_states()
        if not states:
            return 0

        sender_starts = await self.store.sync_sender_modes(
            {mailbox: state.effective.value for mailbox, state in states.items()}
        )
        eligible = {mailbox for mailbox, state in states.items() if state.enabled}
        if not eligible:
            return 0

        aliases, history = await asyncio.gather(
            self.mailcow.list_aliases(),
            self.mailcow.get_rspamd_history(self.settings.usage_history_count),
        )

        alias_targets: dict[str, str] = {}
        for alias in aliases:
            target = alias.goto.strip().lower()
            address = alias.address.strip().lower()
            if target not in eligible or not address:
                continue
            if alias.is_reserved or alias.is_catch_all or is_primary_mailbox_alias(alias, target):
                continue
            if is_owned_alias(alias, target):
                alias_targets[address] = target

        received_events: list[UsageEvent] = []
        sent_events: list[UsageEvent] = []
        sender_events: list[SenderEvent] = []

        for item in history:
            action = str(item.get("action") or "").strip().lower()
            if action not in ACCEPTED_ACTIONS:
                continue

            event_at = _event_timestamp(item)
            if event_at is None or event_at < tracking_started_at:
                continue

            recipients = _normalise_recipients(item.get("rcpt_smtp"))
            sender_identity = _sender_identity(item)
            for alias in recipients.intersection(alias_targets):
                mailbox = alias_targets[alias]
                received_events.append(
                    UsageEvent(
                        event_key=_event_key("received", item, alias, event_at),
                        mailbox=mailbox,
                        alias=alias,
                        event_at=event_at,
                    )
                )

                mode = states[mailbox].effective
                sender_start = sender_starts.get(mailbox, event_at + 1)
                if (
                    mode in {StatsMode.DOMAIN, StatsMode.FULL}
                    and event_at >= sender_start
                    and sender_identity is not None
                ):
                    sender_address, sender_domain = sender_identity
                    sender_events.append(
                        SenderEvent(
                            event_key=_event_key("sender-detail", item, alias, event_at),
                            mailbox=mailbox,
                            alias=alias,
                            sender_domain=sender_domain,
                            sender_address=(
                                sender_address if mode is StatsMode.FULL else None
                            ),
                            event_at=event_at,
                        )
                    )

            authenticated_user = _normalise_address(item.get("user"))
            if authenticated_user not in eligible:
                continue

            # Prefer the visible MIME From address. Fall back to the SMTP envelope
            # sender because some clients or mail paths may rewrite one but not the other.
            sender_mime = _normalise_address(item.get("sender_mime"))
            sender_smtp = _normalise_address(item.get("sender_smtp"))
            sent_alias = ""
            if alias_targets.get(sender_mime) == authenticated_user:
                sent_alias = sender_mime
            elif alias_targets.get(sender_smtp) == authenticated_user:
                sent_alias = sender_smtp

            if sent_alias:
                sent_events.append(
                    UsageEvent(
                        event_key=_event_key("sent", item, sent_alias, event_at),
                        mailbox=authenticated_user,
                        alias=sent_alias,
                        event_at=event_at,
                    )
                )

        received = await self.store.record_received(received_events)
        sent = await self.store.record_sent(sent_events)
        senders = await self.store.record_senders(sender_events)
        if received or sent or senders:
            LOGGER.info(
                "Recorded %d received, %d sent and %d sender-detail Cowcloak event(s)",
                received,
                sent,
                senders,
            )
        return received + sent + senders

    async def run_forever(self) -> None:
        while True:
            try:
                await self.collect_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Cowcloak usage statistics collection failed")
            await asyncio.sleep(self.settings.usage_poll_seconds)
