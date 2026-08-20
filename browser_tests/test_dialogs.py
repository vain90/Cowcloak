from __future__ import annotations

import re

from playwright.sync_api import Page, expect

UNUSED_POOL = "feder-hafen-27@example.org"


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-alias-results-region]")).to_be_visible()

    action_dialog = page.locator("dialog[data-action-required-dialog]")
    expect(action_dialog).to_be_visible(timeout=5000)
    action_dialog.locator(".dialog-close").click()


def _pool_item(page: Page, address: str):
    return page.locator(".pool-item").filter(has_text=address)


def test_destructive_confirmation_is_internal_and_cancellable(page: Page, base_url: str) -> None:
    _login(page, base_url)

    unused = _pool_item(page, UNUSED_POOL)
    unused.locator('form[action$="/delete-reserved"] button').click()

    dialog = page.locator('dialog[data-cowcloak-dialog="confirm"]')
    expect(dialog).to_be_visible()
    expect(dialog.locator('[data-cowcloak-dialog-cancel]')).to_be_focused()
    dialog.locator('[data-cowcloak-dialog-cancel]').click()
    expect(_pool_item(page, UNUSED_POOL)).to_have_count(1)

    _pool_item(page, UNUSED_POOL).locator('form[action$="/delete-reserved"] button').click()
    dialog = page.locator('dialog[data-cowcloak-dialog="confirm"]')
    expect(dialog).to_be_visible()
    dialog.locator('[data-cowcloak-dialog-confirm]').click()
    expect(_pool_item(page, UNUSED_POOL)).to_have_count(0, timeout=5000)


def test_statistics_downgrade_uses_internal_confirmation(page: Page, base_url: str) -> None:
    _login(page, base_url)

    form = page.locator(".usage-mode-form")
    form.locator('select[name="mode"]').select_option("basic")
    form.locator('button[type="submit"]').click()

    dialog = page.locator('dialog[data-cowcloak-dialog="confirm"]')
    expect(dialog).to_be_visible()
    dialog.locator('[data-cowcloak-dialog-cancel]').click()
    expect(page.locator("body")).to_have_attribute("data-stats-effective", "full")


def test_bulk_failure_is_rendered_inside_cowcloak(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.route("**/aliases/bulk", lambda route: route.fulfill(status=500, body="failed"))

    page.locator("[data-alias-select]").first.check()
    page.locator("[data-bulk-action-select]").select_option("disable")
    page.locator(".bulk-actions button").click()

    dialog = page.locator('dialog[data-cowcloak-dialog="message"]')
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator('[data-cowcloak-dialog-confirm]')).to_be_visible()


def test_confirmation_fits_mobile_viewport(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)

    _pool_item(page, UNUSED_POOL).locator('form[action$="/delete-reserved"] button').click()
    dialog = page.locator('dialog[data-cowcloak-dialog="confirm"]')
    expect(dialog).to_be_visible()

    box = dialog.bounding_box()
    assert box is not None
    assert box["x"] >= 0
    assert box["y"] >= 0
    assert box["x"] + box["width"] <= 390
    assert box["y"] + box["height"] <= 844
