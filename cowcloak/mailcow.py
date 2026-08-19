from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from cowcloak.aliases import AliasRecord
from cowcloak.config import Settings


class MailcowError(RuntimeError):
    pass


class MailcowClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.mailcow_url,
            headers={"X-API-Key": settings.mailcow_api_key, "Accept": "application/json"},
            verify=settings.mailcow_verify_tls,
            timeout=15.0,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MailcowError(f"mailcow API request failed: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise MailcowError("mailcow API returned invalid JSON") from exc

    @staticmethod
    def _ensure_success(payload: Any) -> None:
        entries = payload if isinstance(payload, list) else [payload]
        failures = [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("type") != "success"
        ]
        if failures:
            messages = [str(entry.get("msg", "unknown mailcow error")) for entry in failures]
            raise MailcowError("; ".join(messages))

    async def list_aliases(self) -> list[AliasRecord]:
        payload = await self._request("GET", "/api/v1/get/alias/all")
        if not isinstance(payload, list):
            return []
        return [
            AliasRecord.from_mailcow(item)
            for item in payload
            if isinstance(item, dict) and "id" in item
        ]

    async def get_alias(self, alias_id: int) -> AliasRecord:
        payload = await self._request("GET", f"/api/v1/get/alias/{alias_id}")
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict) or "id" not in payload:
            raise MailcowError("Alias does not exist")
        return AliasRecord.from_mailcow(payload)

    async def get_mailbox(self, email: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/api/v1/get/mailbox/{quote(email, safe='@')}")
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict) or not payload:
            raise MailcowError("Authenticated mailcow mailbox does not exist")
        return payload

    async def create_alias(
        self,
        address: str,
        target: str,
        public_comment: str = "",
        *,
        private_comment: str = "",
        sogo_visible: bool = False,
    ) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/add/alias",
            json={
                "address": address,
                "goto": target,
                "active": 1,
                "internal": 0,
                "sender_allowed": 1,
                "sogo_visible": 1 if sogo_visible else 0,
                "goto_null": 0,
                "goto_spam": 0,
                "goto_ham": 0,
                "private_comment": private_comment,
                "public_comment": public_comment,
            },
        )
        self._ensure_success(payload)

    async def update_alias_preferences(
        self,
        alias_id: int,
        public_comment: str,
        sogo_visible: bool,
    ) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={
                "items": [str(alias_id)],
                "attr": {
                    "public_comment": public_comment,
                    "sogo_visible": 1 if sogo_visible else 0,
                },
            },
        )
        self._ensure_success(payload)

    async def assign_reserved_alias(
        self,
        alias_id: int,
        public_comment: str,
        sogo_visible: bool,
    ) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={
                "items": [str(alias_id)],
                "attr": {
                    "private_comment": "",
                    "public_comment": public_comment,
                    "sogo_visible": 1 if sogo_visible else 0,
                },
            },
        )
        self._ensure_success(payload)

    async def set_sender_allowed(self, alias_id: int, allowed: bool) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={
                "items": [str(alias_id)],
                "attr": {"sender_allowed": 1 if allowed else 0},
            },
        )
        self._ensure_success(payload)

    async def set_active(self, alias_id: int, active: bool) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={"items": [str(alias_id)], "attr": {"active": 1 if active else 0}},
        )
        self._ensure_success(payload)

    async def delete_alias(self, alias_id: int) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/delete/alias",
            data={"items": json.dumps([str(alias_id)])},
        )
        self._ensure_success(payload)
