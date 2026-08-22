from __future__ import annotations

import re

from playwright.sync_api import Page, expect


UNUSED_POOL = "feder-hafen-27@example.org"


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))


def test_offline_pool_uses_neutral_create_buttons_and_inline_assignment(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    add_one = page.locator('form:has(input[name="count"][value="1"]) button')
    expect(add_one).to_be_visible()
    assert "primary" not in (add_one.get_attribute("class") or "").split()

    item = page.locator(".pool-item").filter(has_text=UNUSED_POOL)
    details = item.locator('details[data-pool-inline-assign="10"]')
    expect(details).to_be_visible(timeout=5000)
    details.locator("summary").click()
    expect(details).to_have_attribute("open", "")
    expect(page.locator("dialog[data-assign-dialog][open]")).to_have_count(0)

    description = details.locator('input[name="description"]')
    expect(description.locator("xpath=..")).to_contain_text("Alias name / purpose")
    expect(description).to_be_focused()


def test_global_controls_and_statistics_wording_are_polished(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    settings = page.locator(".header-icon-button[data-open-settings]")
    expect(settings).to_be_visible()
    font_size = settings.evaluate("element => parseFloat(getComputedStyle(element).fontSize)")
    assert font_size >= 20

    chevron = page.locator(".account-chevron")
    transform = chevron.evaluate("element => getComputedStyle(element).transform")
    assert transform != "none"

    page.goto(f"{base_url}/statistics")
    review_link = page.locator('a[href="/aliases?status=unexpected"]')
    expect(review_link).to_contain_text("unrecognized aliases to review")
