import json

import httpx

from moolias.config import Settings
from moolias.mailcow import MailcowClient


def settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


async def test_set_mailbox_tags_replaces_removed_tags_and_preserves_unrelated_tags():
    captured = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        captured.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "username": "user@example.org",
                    "domain": "example.org",
                    "tags": ["moolias", "other-tag", "moolias-stats-full"],
                },
            )
        return httpx.Response(
            200,
            json=[{"type": "success", "msg": ["mailbox_modified"]}],
        )

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.set_mailbox_tags(
        "user@example.org",
        ["moolias", "other-tag", "moolias-stats-domain"],
    )
    await client.close()

    assert captured == [
        ("GET", "/api/v1/get/mailbox/user@example.org", None),
        (
            "POST",
            "/api/v1/delete/mailbox/tag/user@example.org",
            ["moolias-stats-full"],
        ),
        (
            "POST",
            "/api/v1/edit/mailbox",
            {
                "items": ["user@example.org"],
                "attr": {"tags": ["moolias-stats-domain"]},
            },
        ),
    ]


async def test_set_mailbox_tags_can_remove_stats_override_without_adding_tags():
    captured = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        captured.append((request.method, request.url.path, body))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "username": "user@example.org",
                    "domain": "example.org",
                    "tags": ["moolias", "moolias-stats-domain"],
                },
            )
        return httpx.Response(
            200,
            json=[{"type": "success", "msg": ["mailbox_modified"]}],
        )

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.set_mailbox_tags("user@example.org", ["moolias"])
    await client.close()

    assert captured == [
        ("GET", "/api/v1/get/mailbox/user@example.org", None),
        (
            "POST",
            "/api/v1/delete/mailbox/tag/user@example.org",
            ["moolias-stats-domain"],
        ),
    ]
