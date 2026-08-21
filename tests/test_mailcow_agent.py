from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from moolias.mailcow_agent import (
    AgentCooldownError,
    AgentStateStore,
    create_agent_app,
)
from moolias.sender_protocol import (
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    request_signature,
)

SECRET = "a" * 64


def _signed_headers(
    path: str,
    body: bytes,
    *,
    timestamp: int,
    nonce: str,
) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: str(timestamp),
        NONCE_HEADER: nonce,
        SIGNATURE_HEADER: request_signature(
            SECRET,
            "POST",
            path,
            timestamp,
            nonce,
            body,
        ),
    }


def test_state_store_blocks_exact_mailbox_and_enforces_per_mailbox_cooldown(tmp_path):
    now = [1000.0]
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "postfix-policy" / "blocked_sender_login.pcre"
    store = AgentStateStore(
        state_dir,
        cooldown_seconds=10,
        policy_path=policy_path,
        clock=lambda: now[0],
    )
    store.ensure_files()

    changed = store.set_blocked("User+tag@example.org", True)
    assert changed["blocked"] is True
    assert changed["changed"] is True
    assert changed["retry_after"] == 10

    pcre = policy_path.read_text(encoding="utf-8")
    assert "/^user\\+tag@example\\.org$/" in pcre
    assert "__moolias_blocked_primary_sender__" in pcre
    assert not (state_dir / "blocked_sender_login.pcre").exists()

    with pytest.raises(AgentCooldownError) as error:
        store.set_blocked("user+tag@example.org", False)
    assert error.value.retry_after == 10

    # Cooldowns are isolated per mailbox, so another user is not delayed.
    second = store.set_blocked("other@example.org", True)
    assert second["changed"] is True

    now[0] += 10
    cleared = store.set_blocked("USER+TAG@example.org", False)
    assert cleared["blocked"] is False

    state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    assert "user+tag@example.org" not in state["blocked"]
    assert "other@example.org" in state["blocked"]


async def test_agent_requires_valid_signature_and_rejects_replay(tmp_path):
    now = [2000.0]
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "policy" / "blocked_sender_login.pcre"
    app = create_agent_app(
        secret=SECRET,
        state_dir=state_dir,
        policy_path=policy_path,
        cooldown_seconds=10,
        clock=lambda: now[0],
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        unsigned = await client.post("/v1/status", json={"mailbox": "user@example.org"})
        assert unsigned.status_code == 401

        body = b'{"mailbox":"user@example.org"}'
        headers = _signed_headers(
            "/v1/status",
            body,
            timestamp=2000,
            nonce="nonce-abcdefghijklmnop",
        )
        signed = await client.post("/v1/status", content=body, headers=headers)
        assert signed.status_code == 200
        assert signed.json()["mailbox"] == "user@example.org"

        replay = await client.post("/v1/status", content=body, headers=headers)
        assert replay.status_code == 401


async def test_agent_rejects_client_supplied_regex_and_rate_limits_changes(tmp_path):
    now = [3000.0]
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "policy" / "blocked_sender_login.pcre"
    app = create_agent_app(
        secret=SECRET,
        state_dir=state_dir,
        policy_path=policy_path,
        cooldown_seconds=10,
        clock=lambda: now[0],
    )
    transport = httpx.ASGITransport(app=app)

    async def post(client, path, payload, nonce):
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        headers = _signed_headers(path, body, timestamp=int(now[0]), nonce=nonce)
        return await client.post(path, content=body, headers=headers)

    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        extra = await post(
            client,
            "/v1/protection",
            {
                "mailbox": "user@example.org",
                "blocked": True,
                "pattern": "/.*/",
            },
            "nonce-extra-abcdefghijkl",
        )
        assert extra.status_code == 400

        blocked = await post(
            client,
            "/v1/protection",
            {"mailbox": "user@example.org", "blocked": True},
            "nonce-block-abcdefghijkl",
        )
        assert blocked.status_code == 200
        assert blocked.json()["blocked"] is True

        too_fast = await post(
            client,
            "/v1/protection",
            {"mailbox": "user@example.org", "blocked": False},
            "nonce-unblock-abcdefghij",
        )
        assert too_fast.status_code == 429
        assert too_fast.headers["Retry-After"] == "10"

        # A malicious mailbox string cannot become a PCRE expression.
        invalid = await post(
            client,
            "/v1/protection",
            {"mailbox": "victim@example.org\n/.*/", "blocked": True},
            "nonce-invalid-abcdefghij",
        )
        assert invalid.status_code == 400

    pcre = Path(policy_path).read_text(encoding="utf-8")
    assert "/.*/" not in pcre
