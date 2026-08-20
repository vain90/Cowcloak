from __future__ import annotations

import re

from playwright.sync_api import Page, expect

AMAZON = "amazon-k7@example.org"
UNEXPECTED_SENDER = "odd@unexpected.example"


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-alias-results-region]")).to_be_visible()

    used_dialog = page.locator("dialog[data-used-pool-prompt]")
    expect(used_dialog).to_be_visible(timeout=5000)
    used_dialog.locator(".used-pool-actions button").nth(1).click()

    review_dialog = page.locator("dialog[data-unexpected-review-dialog]")
    expect(review_dialog).to_be_visible(timeout=5000)
    review_dialog.locator(".dialog-close").click()


def _open_amazon_senders(page: Page):
    row = _alias_row(page, AMAZON)
    trigger = row.locator(".sender-stats-trigger")
    dialog_id = trigger.get_attribute("aria-controls")
    assert dialog_id
    trigger.click()
    dialog = page.locator(f"#{dialog_id}")
    expect(dialog).to_be_visible()
    return dialog


def _sender_row(dialog, sender: str):
    return dialog.locator(".sender-stats-row").filter(has_text=sender)


def test_full_mode_domain_approval_warns_and_can_be_overridden_per_address(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    dialog = _open_amazon_senders(page)
    sender = _sender_row(dialog, UNEXPECTED_SENDER)
    expect(sender).to_have_class(re.compile(r"\bunexpected\b"))
    expect(sender.locator('[data-expect-domain]')).to_be_visible()

    sender.locator('[data-expect-domain]').click()
    confirmation = page.locator('dialog[data-cowcloak-dialog="confirm"]')
    expect(confirmation).to_be_visible()
    expect(confirmation).to_contain_text("unexpected.example")
    confirmation.locator('[data-cowcloak-dialog-cancel]').click()
    expect(sender).to_have_class(re.compile(r"\bunexpected\b"))

    sender.locator('[data-expect-domain]').click()
    confirmation = page.locator('dialog[data-cowcloak-dialog="confirm"]')
    expect(confirmation).to_be_visible()
    confirmation.locator('[data-cowcloak-dialog-confirm]').click()

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"), timeout=5000)
    dialog = _open_amazon_senders(page)
    sender = _sender_row(dialog, UNEXPECTED_SENDER)
    expect(sender).to_have_class(re.compile(r"\bexpected\b"))
    expect(sender.locator('[data-specific-unexpected]')).to_be_visible()

    sender.locator('[data-specific-unexpected]').click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"), timeout=5000)

    dialog = _open_amazon_senders(page)
    sender = _sender_row(dialog, UNEXPECTED_SENDER)
    expect(sender).to_have_class(re.compile(r"\bunexpected\b"))
    expect(sender.locator('[data-expect-domain]')).to_be_visible()
