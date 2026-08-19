import os

os.environ.setdefault("COWCLOAK_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("COWCLOAK_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

from fastapi.testclient import TestClient

import cowcloak.main as main_module
from cowcloak.aliases import AliasRecord
from cowcloak.config import Settings
from cowcloak.mailcow import MailcowError


def settings() -> Settings:
    return Settings(
        COWCLOAK_BASE_URL="https://aliases.example.org",
        COWCLOAK_SESSION_SECRET="x" * 64,
        COWCLOAK_COOKIE_SECURE=False,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, alias: AliasRecord, *, fail_disable: bool = False) -> None:
        self.alias = alias
        self.fail_disable = fail_disable
        self.created: list[dict[str, object]] = []
        self.active_updates: list[tuple[int, bool]] = []

    async def close(self) -> None:
        pass

    async def get_alias(self, alias_id: int) -> AliasRecord:
        assert alias_id == self.alias.id
        return self.alias

    async def create_alias(
        self,
        address: str,
        target: str,
        public_comment: str = "",
        *,
        private_comment: str = "",
        sogo_visible: bool = False,
    ) -> None:
        self.created.append(
            {
                "address": address,
                "target": target,
                "public_comment": public_comment,
                "private_comment": private_comment,
                "sogo_visible": sogo_visible,
            }
        )

    async def set_active(self, alias_id: int, active: bool) -> None:
        self.active_updates.append((alias_id, active))
        if self.fail_disable:
            raise MailcowError("disable failed")


def alias_record(**overrides) -> AliasRecord:
    values = {
        "id": 42,
        "address": "amazon-k7@example.org",
        "goto": "hidden@example.org",
        "domain": "example.org",
        "active": True,
        "private_comment": "",
        "public_comment": "Amazon",
        "sogo_visible": True,
    }
    values.update(overrides)
    return AliasRecord(**values)


def make_client(monkeypatch, fake: FakeMailcow) -> TestClient:
    monkeypatch.setattr(main_module, "MailcowClient", lambda _: fake)
    monkeypatch.setattr(main_module, "require_user", lambda _: "hidden@example.org")
    monkeypatch.setattr(main_module, "validate_csrf", lambda _request, _token: None)
    return TestClient(main_module.create_app(settings()))


def test_replace_alias_copies_purpose_and_sogo_then_disables_old_alias(monkeypatch):
    fake = FakeMailcow(alias_record())

    with make_client(monkeypatch, fake) as client:
        response = client.post("/aliases/42/replace", data={"csrf_token": "test"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["old_address"] == "amazon-k7@example.org"
    assert payload["address"].startswith("amazon-")
    suffix = payload["address"].split("@", 1)[0].rsplit("-", 1)[1]
    assert len(suffix) == 2
    assert fake.created == [
        {
            "address": payload["address"],
            "target": "hidden@example.org",
            "public_comment": "Amazon",
            "private_comment": "",
            "sogo_visible": True,
        }
    ]
    assert fake.active_updates == [(42, False)]


def test_replace_alias_reports_partial_result_when_old_alias_cannot_be_disabled(monkeypatch):
    fake = FakeMailcow(alias_record(), fail_disable=True)

    with make_client(monkeypatch, fake) as client:
        response = client.post("/aliases/42/replace", data={"csrf_token": "test"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "partial_replacement"
    assert detail["address"].startswith("amazon-")
    assert fake.active_updates == [(42, False)]


def test_primary_mailbox_alias_cannot_be_replaced(monkeypatch):
    primary = alias_record(
        address="hidden@example.org",
        goto="hidden@example.org",
        public_comment="",
        sogo_visible=False,
    )
    fake = FakeMailcow(primary)

    with make_client(monkeypatch, fake) as client:
        response = client.post("/aliases/42/replace", data={"csrf_token": "test"})

    assert response.status_code == 409
    assert fake.created == []
    assert fake.active_updates == []
