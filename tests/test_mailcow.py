import json
from urllib.parse import parse_qs

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


async def test_create_alias_sets_public_purpose_sender_permission_and_sogo_visibility():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_added"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.create_alias(
        "amazon-k7p4@example.org",
        "hidden@example.org",
        "Amazon",
        sogo_visible=True,
    )
    await client.close()

    assert captured["path"] == "/api/v1/add/alias"
    assert captured["json"]["goto"] == "hidden@example.org"
    assert captured["json"]["public_comment"] == "Amazon"
    assert captured["json"]["private_comment"] == ""
    assert captured["json"]["sender_allowed"] == 1
    assert captured["json"]["sogo_visible"] == 1


async def test_reserved_alias_uses_private_marker_and_stays_hidden_from_sogo():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_added"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.create_alias(
        "pool-42@example.org",
        "hidden@example.org",
        private_comment="[cowcloak:reserved]",
        sogo_visible=False,
    )
    await client.close()

    assert captured["json"]["public_comment"] == ""
    assert captured["json"]["private_comment"] == "[cowcloak:reserved]"
    assert captured["json"]["sogo_visible"] == 0


async def test_alias_preferences_never_touch_private_comment_address_or_target():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.update_alias_preferences(42, "Amazon shopping", True)
    await client.close()

    assert captured["json"] == {
        "items": ["42"],
        "attr": {
            "public_comment": "Amazon shopping",
            "sogo_visible": 1,
        },
    }


async def test_assign_reserved_alias_clears_only_reservation_marker_fields():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.assign_reserved_alias(42, "Hotel", False)
    await client.close()

    assert captured["json"] == {
        "items": ["42"],
        "attr": {
            "private_comment": "",
            "public_comment": "Hotel",
            "sogo_visible": 0,
        },
    }


async def test_set_active_many_updates_all_selected_aliases_in_one_request():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.set_active_many([12, 42, 77], False)
    await client.close()

    assert captured["path"] == "/api/v1/edit/alias"
    assert captured["json"] == {
        "items": ["12", "42", "77"],
        "attr": {"active": 0},
    }


async def test_set_sogo_visible_many_updates_all_selected_aliases_in_one_request():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_modified"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.set_sogo_visible_many([12, 42], True)
    await client.close()

    assert captured["json"] == {
        "items": ["12", "42"],
        "attr": {"sogo_visible": 1},
    }


async def test_delete_alias_uses_mailcow_alias_delete_endpoint():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(200, json=[{"type": "success", "msg": ["alias_deleted"]}])

    client = MailcowClient(settings(), transport=httpx.MockTransport(handler))
    await client.delete_alias(42)
    await client.close()

    assert captured["path"] == "/api/v1/delete/alias"
    assert captured["form"]["items"] == ['["42"]']
