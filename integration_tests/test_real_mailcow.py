from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest

from moolias.aliases import RESERVED_COMMENT
from moolias.config import Settings
from moolias.mailcow import MailcowClient
from moolias.stats_mode import replace_mailbox_stats_tags

DOMAIN = "moolias-ci.test"
MAILBOX = f"owner@{DOMAIN}"
ACCESS_TAG = "moolias-ci-access"
STATS_TAG = "moolias-stats"
PASSWORD = "Moolias-CI-Only-4f9d!A7"


@dataclass
class RealMailcow:
    client: MailcowClient


async def _post_success(
    admin: httpx.AsyncClient,
    path: str,
    payload: dict[str, object],
) -> object:
    response = await admin.post(path, json=payload)
    response.raise_for_status()
    body = response.json()
    entries = body if isinstance(body, list) else [body]
    result_types = [
        str(getattr(entry, "get", lambda *_: "")("type", "")).strip().casefold()
        for entry in entries
    ]
    if "success" not in result_types:
        raise AssertionError(
            f"Mailcow {path} did not report success "
            f"(result types: {result_types}): {body!r}"
        )
    return body


async def _create_domain(admin: httpx.AsyncClient) -> None:
    await _post_success(
        admin,
        "/api/v1/add/domain",
        {
            "active": 1,
            "aliases": 50,
            "backupmx": 0,
            "defquota": 128,
            "description": "Disposable Moolias integration domain",
            "domain": DOMAIN,
            "mailboxes": 10,
            "maxquota": 512,
            "quota": 1024,
            "relay_all_recipients": 0,
            "rl_frame": "s",
            "rl_value": 10,
            "restart_sogo": 0,
            "tags": [ACCESS_TAG],
        },
    )


async def _create_mailbox(admin: httpx.AsyncClient) -> None:
    await _post_success(
        admin,
        "/api/v1/add/mailbox",
        {
            "active": 1,
            "domain": DOMAIN,
            "local_part": "owner",
            "name": "Moolias CI",
            "password": PASSWORD,
            "password2": PASSWORD,
            "quota": 128,
            "force_pw_update": 0,
            "tls_enforce_in": 0,
            "tls_enforce_out": 0,
        },
    )


def _settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="http://moolias-ci.test",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_ACCESS_TAG=ACCESS_TAG,
        MAILCOW_URL=os.environ["MAILCOW_URL"],
        MAILCOW_API_KEY=os.environ["MAILCOW_API_KEY"],
        MAILCOW_OAUTH_CLIENT_ID="integration-not-used",
        MAILCOW_OAUTH_CLIENT_SECRET="integration-not-used",
        MAILCOW_VERIFY_TLS=False,
    )


@pytest.fixture(scope="module")
async def provision_real_mailcow() -> None:
    base_url = os.environ.get("MAILCOW_URL")
    api_key = os.environ.get("MAILCOW_API_KEY")
    if not base_url or not api_key:
        pytest.skip("real Mailcow integration environment is not configured")

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        timeout=30.0,
        trust_env=False,
    ) as admin:
        await _create_domain(admin)
        await _create_mailbox(admin)


@pytest.fixture
async def real_mailcow(provision_real_mailcow: None) -> AsyncIterator[RealMailcow]:
    client = MailcowClient(_settings())
    try:
        yield RealMailcow(client=client)
    finally:
        await client.close()


async def _alias_by_address(real_mailcow: RealMailcow, address: str):
    aliases = await real_mailcow.client.list_aliases()
    return next(alias for alias in aliases if alias.address == address)


async def test_profile_mailbox_identity_and_domain_access_tag(real_mailcow: RealMailcow):
    mailbox = await real_mailcow.client.get_mailbox(MAILBOX)

    assert mailbox["username"] == MAILBOX
    assert mailbox["domain"] == DOMAIN


async def test_alias_create_read_edit_disable_and_delete_contract(real_mailcow: RealMailcow):
    address = f"lifecycle@{DOMAIN}"

    await real_mailcow.client.create_alias(
        address,
        MAILBOX,
        "Initial purpose",
        private_comment="private-integration-marker",
        sogo_visible=True,
    )
    created = await _alias_by_address(real_mailcow, address)

    assert created.goto == MAILBOX
    assert created.public_comment == "Initial purpose"
    assert created.private_comment == "private-integration-marker"
    assert created.sogo_visible is True
    assert created.sender_allowed is True
    assert created.active is True

    await real_mailcow.client.update_alias_preferences(created.id, "Updated purpose", False)
    updated = await real_mailcow.client.get_alias(created.id)
    assert updated.public_comment == "Updated purpose"
    assert updated.private_comment == "private-integration-marker"
    assert updated.sogo_visible is False

    await real_mailcow.client.set_active(created.id, False)
    disabled = await real_mailcow.client.get_alias(created.id)
    assert disabled.active is False

    await real_mailcow.client.set_active(created.id, True)
    await real_mailcow.client.delete_alias(created.id)
    assert all(alias.address != address for alias in await real_mailcow.client.list_aliases())


async def test_reserved_and_reserved_used_markers_round_trip(real_mailcow: RealMailcow):
    address = f"reserved@{DOMAIN}"

    await real_mailcow.client.create_alias(
        address,
        MAILBOX,
        private_comment=RESERVED_COMMENT,
        sogo_visible=False,
    )
    reserved = await _alias_by_address(real_mailcow, address)
    assert reserved.is_reserved is True
    assert reserved.is_reserved_used is False
    assert reserved.sogo_visible is False

    await real_mailcow.client.mark_reserved_alias_used(reserved.id)
    used = await real_mailcow.client.get_alias(reserved.id)
    assert used.is_reserved is True
    assert used.is_reserved_used is True

    await real_mailcow.client.assign_reserved_alias(reserved.id, "Assigned purpose", True)
    assigned = await real_mailcow.client.get_alias(reserved.id)
    assert assigned.is_reserved is False
    assert assigned.is_reserved_used is False
    assert assigned.private_comment == ""
    assert assigned.public_comment == "Assigned purpose"
    assert assigned.sogo_visible is True

    await real_mailcow.client.delete_alias(reserved.id)


async def test_mailbox_tag_add_remove_and_stats_mode_replacement(real_mailcow: RealMailcow):
    await real_mailcow.client.set_mailbox_tags(
        MAILBOX,
        ["keep-me", f"{STATS_TAG}-domain"],
    )
    domain_mode = await real_mailcow.client.get_mailbox(MAILBOX)
    assert {tag.casefold() for tag in domain_mode.get("tags", [])} == {
        "keep-me",
        f"{STATS_TAG}-domain",
    }

    full_tags = replace_mailbox_stats_tags(domain_mode.get("tags"), STATS_TAG, "full")
    await real_mailcow.client.set_mailbox_tags(MAILBOX, full_tags)
    full_mode = await real_mailcow.client.get_mailbox(MAILBOX)
    assert {tag.casefold() for tag in full_mode.get("tags", [])} == {
        "keep-me",
        f"{STATS_TAG}-full",
    }

    await real_mailcow.client.set_mailbox_tags(MAILBOX, ["keep-me"])
    without_stats = await real_mailcow.client.get_mailbox(MAILBOX)
    assert {tag.casefold() for tag in without_stats.get("tags", [])} == {"keep-me"}


async def test_rspamd_history_endpoint_is_reachable(real_mailcow: RealMailcow):
    history = await real_mailcow.client.get_rspamd_history(10)
    assert isinstance(history, list)
