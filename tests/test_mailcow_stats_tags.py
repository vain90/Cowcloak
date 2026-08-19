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


async def test_set_mailbox_tags_updates_only_tags_attribute():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=[{"type": "success", "msg": ["mailbox_modified"]}],
        )

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.set_mailbox_tags(
        "user@example.org",
        ["cowcloak", "other-tag", "cowcloak-stats-domain"],
    )
    await client.close()

    assert captured["path"] == "/api/v1/edit/mailbox"
    assert captured["json"] == {
        "items": ["user@example.org"],
        "attr": {
            "tags": ["cowcloak", "other-tag", "cowcloak-stats-domain"],
        },
    }
