import json

import httpx

from cowcloak.config import Settings
from cowcloak.mailcow import MailcowClient


def settings() -> Settings:
    return Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


async def test_create_alias_sets_target_comment_and_sender_permission():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_added"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.create_alias("amazon-k7p4@example.org", "hidden@example.org", "Amazon")
    await client.close()

    assert captured["path"] == "/api/v1/add/alias"
    assert captured["json"]["goto"] == "hidden@example.org"
    assert captured["json"]["private_comment"] == "Amazon"
    assert captured["json"]["sender_allowed"] == 1


async def test_description_update_never_changes_address_or_target():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.update_description(42, "Amazon private")
    await client.close()

    assert captured["json"] == {"items": ["42"], "attr": {"private_comment": "Amazon private"}}
