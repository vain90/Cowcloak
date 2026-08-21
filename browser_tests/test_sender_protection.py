from __future__ import annotations

import json
import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-alias-results-region]")).to_be_visible()

    dialog = page.locator("dialog[data-action-required-dialog]")
    if dialog.is_visible():
        dialog.locator(".dialog-close").click()


def test_sender_protection_switch_updates_and_enforces_visible_cooldown(
    page: Page,
    base_url: str,
) -> None:
    requests: list[dict[str, object]] = []
    state = {"blocked": False}

    def sender_protection_route(route, request) -> None:
        if request.method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "enabled": True,
                        "available": True,
                        "blocked": state["blocked"],
                        "retry_after": 0,
                    }
                ),
            )
            return

        payload = request.post_data_json
        requests.append(payload)
        assert request.headers.get("x-csrf-token")
        assert set(payload) == {"blocked"}
        state["blocked"] = bool(payload["blocked"])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "blocked": state["blocked"],
                    "retry_after": 1,
                }
            ),
        )

    page.route("**/aliases/sender-protection", sender_protection_route)
    _login(page, base_url)

    card = page.locator(".sender-protection-card")
    expect(card).to_be_visible(timeout=5000)
    switch = card.locator('input[role="switch"]')
    expect(switch).not_to_be_checked()
    expect(card.locator(".sender-protection-state")).to_have_text("Sending allowed")

    switch.check()

    expect(switch).to_be_checked()
    expect(switch).to_be_disabled()
    expect(card.locator(".sender-protection-state")).to_have_text("Protected")
    expect(card.locator(".sender-protection-message")).to_contain_text("1 second")
    assert requests == [{"blocked": True}]

    page.wait_for_timeout(1100)
    expect(switch).to_be_enabled()
