from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from cowcloak.aliases import is_owned_alias, is_primary_mailbox_alias
from cowcloak.config import Settings
from cowcloak.mailcow import MailcowClient
from cowcloak.stats import StatsStore, UsageEvent

LOGGER = logging.getLogger(__name__)

# These Rspamd actions still represent accepted mail. Reject/soft reject/greylist
# entries are deliberately excluded because they were not delivered to the alias.
ACCEPTED_INCOMING_ACTIONS = frozenset(
    {
        "clean",
        "no action",
        "add header",
        "rewrite subject",
        "probable spam",
    }
)


def _tags(payload: dict[str, Any]) -> set[str]:
    tags = payload.get("tags")
    if not isinstance(tags, list):
        return set()
    return {str(tag).strip().casefold() for tag in tags if str(tag).strip()}


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


def _received_event_key(item: dict[str, Any], alias: str, event_at: int) -> str:
    # Only the SHA-256 digest is persisted. Subject/message IDs are used solely to
    # reduce accidental collisions when Rspamd history contains near-identical rows.
    fingerprint = {
        "kind": "received",
        "alias": alias.lower(),
        "event_at": event_at,
        "message_id": str(item.get("message-id") or item.get("message_id") or ""),
        "queue_id": str(item.get("qid") or item.get("queue_id") or ""),
        "sender": str(item.get("sender_smtp") or ""),
        "subject": str(item.get("subject") or ""),
        "user": str(item.get("user") or ""),
    }
    payload = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


class UsageCollector:
    def __init__(self, settings: Settings, mailcow: MailcowClient, store: StatsStore) -> None:
        self.settings = settings
        self.mailcow = mailcow
        self.store = store

    async def eligible_mailboxes(self) -> set[str]:
        usage_tag = self.settings.usage_tag.casefold()
        domains, mailboxes = await asyncio.gather(
            self.mailcow.list_domains(),
            self.mailcow.list_mailboxes(),
        )
        tagged_domains = {
            str(domain.get("domain") or "").strip().lower()
            for domain in domains
            if usage_tag in _tags(domain)
        }
        tagged_domains.discard("")

        eligible: set[str] = set()
        for mailbox in mailboxes:
            username = str(mailbox.get("username") or "").strip().lower()
            if not username or "@" not in username:
                continue
            domain = str(mailbox.get("domain") or username.rsplit("@", 1)[1]).strip().lower()
            if usage_tag in _tags(mailbox) or domain in tagged_domains:
                eligible.add(username)
        return eligible

    async def collect_once(self) -> int:
        tracking_started_at = await self.store.tracking_started_at()
        eligible = await self.eligible_mailboxes()
        if not eligible:
            await self.store.prune_processed_events()
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

        events: list[UsageEvent] = []
        for item in history:
            action = str(item.get("action") or "").strip().lower()
            if action not in ACCEPTED_INCOMING_ACTIONS:
                continue
            event_at = _event_timestamp(item)
            if event_at is None or event_at < tracking_started_at:
                continue
            recipients = _normalise_recipients(item.get("rcpt_smtp"))
            for alias in recipients.intersection(alias_targets):
                events.append(
                    UsageEvent(
                        event_key=_received_event_key(item, alias, event_at),
                        mailbox=alias_targets[alias],
                        alias=alias,
                        event_at=event_at,
                    )
                )

        recorded = await self.store.record_received(events)
        await self.store.prune_processed_events()
        if recorded:
            LOGGER.info("Recorded %d new Cowcloak alias delivery event(s)", recorded)
        return recorded

    async def run_forever(self) -> None:
        while True:
            try:
                await self.collect_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Cowcloak usage statistics collection failed")
            await asyncio.sleep(self.settings.usage_poll_seconds)
