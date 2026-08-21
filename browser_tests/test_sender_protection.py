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


def test_sender_protection_lives_in_settings_and_updates_warning(
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
                        "managed": True,
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
                    "managed": True,
                    "retry_after": 1,
                }
            ),
        )

    page.route("**/aliases/sender-protection", sender_protection_route)
    _login(page, base_url)

    expect(page.locator(".sender-protection-card")).to_have_count(0)

    warning = page.locator("[data-sender-protection-warning]")
    expect(warning).to_be_visible(timeout=5000)
    expect(warning).to_contain_text("primary address")

    settings_button = page.locator("[data-open-settings-dialog]")
    expect(settings_button).to_be_visible()
    settings_button.click()

    settings_dialog = page.locator("[data-settings-dialog]")
    expect(settings_dialog).to_be_visible()
    protection = settings_dialog.locator("[data-sender-protection-settings]")
    expect(protection).to_be_visible()

    switch = protection.locator('input[role="switch"]')
    expect(switch).not_to_be_checked()
    expect(protection.locator(".sender-protection-state")).to_have_text("Sending allowed")

    switch.check()

    expect(switch).to_be_checked()
    expect(switch).to_be_disabled()
    expect(protection.locator(".sender-protection-state")).to_have_text("Protected")
    expect(protection.locator(".sender-protection-message")).to_contain_text("1 second")
    expect(warning).to_be_hidden()
    assert requests == [{"blocked": True}]

    page.wait_for_timeout(1100)
    expect(switch).to_be_enabled()

    switch.uncheck()

    expect(switch).not_to_be_checked()
    expect(warning).to_be_visible()
    assert requests == [{"blocked": True}, {"blocked": False}]
