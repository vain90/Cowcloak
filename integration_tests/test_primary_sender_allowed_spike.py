from __future__ import annotations

import os
import warnings

import httpx
import pytest

DOMAIN = "moolias-primary-sender.test"
MAILBOX = f"owner@{DOMAIN}"
PASSWORD = "Moolias-Primary-Sender-CI-4f9d!A7"


def _result_types(body: object) -> list[str]:
    entries = body if isinstance(body, list) else [body]
    return [
        str(entry.get("type", "")).strip().casefold()
        for entry in entries
        if isinstance(entry, dict)
    ]


async def _post_success(
    admin: httpx.AsyncClient,
    path: str,
    payload: dict[str, object],
) -> object:
    response = await admin.post(path, json=payload)
    response.raise_for_status()
    body = response.json()
    if "success" not in _result_types(body):
        raise AssertionError(f"Mailcow {path} did not report success: {body!r}")
    return body


async def _get_json(admin: httpx.AsyncClient, path: str) -> object:
    response = await admin.get(path)
    response.raise_for_status()
    return response.json()


async def test_primary_mailbox_sender_allowed_alias_api_spike() -> None:
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
        await _post_success(
            admin,
            "/api/v1/add/domain",
            {
                "active": 1,
                "aliases": 10,
                "backupmx": 0,
                "defquota": 128,
                "description": "Moolias primary sender API spike",
                "domain": DOMAIN,
                "mailboxes": 2,
                "maxquota": 512,
                "quota": 1024,
                "relay_all_recipients": 0,
                "rl_frame": "s",
                "rl_value": 10,
                "restart_sogo": 0,
            },
        )
        await _post_success(
            admin,
            "/api/v1/add/mailbox",
            {
                "active": 1,
                "domain": DOMAIN,
                "local_part": "owner",
                "name": "Moolias Primary Sender CI",
                "password": PASSWORD,
                "password2": PASSWORD,
                "quota": 128,
                "force_pw_update": 0,
                "tls_enforce_in": 0,
                "tls_enforce_out": 0,
            },
        )

        aliases = await _get_json(admin, "/api/v1/get/alias/all")
        self_alias_visible = any(
            isinstance(alias, dict)
            and str(alias.get("address", "")).casefold() == MAILBOX.casefold()
            for alias in aliases
        ) if isinstance(aliases, list) else False

        edit_response = await admin.post(
            "/api/v1/edit/alias",
            json={
                "items": [MAILBOX],
                "attr": {"sender_allowed": 0},
            },
        )
        edit_response.raise_for_status()
        edit_body = edit_response.json()
        edit_succeeded = "success" in _result_types(edit_body)

        mailbox_after = await _get_json(admin, f"/api/v1/get/mailbox/{MAILBOX}")
        mailbox_payload = (
            mailbox_after[0]
            if isinstance(mailbox_after, list) and mailbox_after
            else mailbox_after
        )
        fixed_allowed = (
            mailbox_payload.get("fixed_sender_aliases_allowed", [])
            if isinstance(mailbox_payload, dict)
            else []
        )
        fixed_blocked = (
            mailbox_payload.get("fixed_sender_aliases_blocked", [])
            if isinstance(mailbox_payload, dict)
            else []
        )

        if edit_succeeded:
            restore = await admin.post(
                "/api/v1/edit/alias",
                json={
                    "items": [MAILBOX],
                    "attr": {"sender_allowed": 1},
                },
            )
            restore.raise_for_status()

        warnings.warn(
            "Primary sender API spike: "
            f"self_alias_visible={self_alias_visible!r}, "
            f"edit_succeeded={edit_succeeded!r}, "
            f"edit_body={edit_body!r}, "
            f"fixed_allowed={fixed_allowed!r}, "
            f"fixed_blocked={fixed_blocked!r}",
            stacklevel=1,
        )

        assert self_alias_visible is False
        assert edit_succeeded is False
