from __future__ import annotations

import re

from playwright.sync_api import Page, expect

AMAZON = "amazon-k7@example.org"
GITHUB = "github-m4@example.org"
UNUSED_POOL = "feder-hafen-27@example.org"
USED_POOL = "mond-segel-42@example.org"


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def _pool_item(page: Page, address: str):
    return page.locator(".pool-item").filter(has_text=address)


def _login(page: Page, base_url: str, *, dismiss_action: bool = True) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-alias-results-region]")).to_be_visible()

    dialog = page.locator("dialog[data-action-required-dialog]")
    expect(dialog).to_be_visible(timeout=5000)
    if dismiss_action:
        dialog.locator(".dialog-close").click()


def test_login_callback_opens_one_action_required_surface(page: Page, base_url: str) -> None:
    _login(page, base_url, dismiss_action=False)

    dialog = page.locator("dialog[data-action-required-dialog]")
    expect(dialog).to_contain_text("Action required")
    expect(dialog).to_contain_text("Used offline aliases")
    expect(dialog).to_contain_text(USED_POOL)
    expect(dialog).to_contain_text("Unexpected senders")
    expect(dialog).to_contain_text(AMAZON)
    expect(dialog).to_contain_text("odd@unexpected.example")
    expect(page.locator("dialog[open]")).to_have_count(1)
    expect(page.locator("dialog[data-used-pool-prompt]")).to_have_count(0)

    dialog.locator(".dialog-close").click()
    page.reload()
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)

    action = page.locator("[data-action-required-open]")
    expect(action).to_be_visible()
    expect(action).to_contain_text("Action required")
    action.click()
    expect(dialog).to_be_visible()


def test_live_search_keeps_server_unexpected_filter_and_filtering_works(
    page: Page,
    base_url: str,
) -> None:
    requested_urls: list[str] = []
    page.on("request", lambda request: requested_urls.append(request.url))
    _login(page, base_url)

    search = page.locator("[data-live-search]")
    search.fill("GitHub")

    expect(page.locator(".alias-list .alias-row")).to_have_count(1, timeout=5000)
    expect(_alias_row(page, GITHUB)).to_have_count(1)

    unexpected = page.locator("[data-unexpected-filter]")
    expect(unexpected).to_be_visible()
    expect(unexpected.locator("span")).to_have_text("1", timeout=5000)

    page.locator("[data-search-clear]").click()
    expect(_alias_row(page, AMAZON)).to_have_count(1, timeout=5000)
    expect(unexpected).to_be_visible()

    unexpected.click()
    expect(page).to_have_url(re.compile(r"[?&]status=unexpected(?:&|$)"))
    expect(page.locator(".alias-list .alias-row")).to_have_count(1, timeout=5000)
    expect(_alias_row(page, AMAZON)).to_have_count(1)
    expect(_alias_row(page, GITHUB)).to_have_count(0)

    search = page.locator("[data-live-search]")
    search.fill("GitHub")
    expect(page.locator(".alias-list .alias-row")).to_have_count(0, timeout=5000)
    expect(page).to_have_url(re.compile(r"[?&]status=unexpected(?:&|$)"))

    assert not any(
        "status=all" in url and "per_page=100" in url
        for url in requested_urls
    )


def test_sender_review_reopens_action_required_with_fresh_state(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    amazon_row = _alias_row(page, AMAZON)
    sender_trigger = amazon_row.locator(".sender-stats-trigger")
    expect(sender_trigger).to_be_visible()
    dialog_id = sender_trigger.get_attribute("aria-controls")
    assert dialog_id
    sender_trigger.click()

    sender_dialog = page.locator(f"#{dialog_id}")
    expect(sender_dialog).to_be_visible()
    expect(sender_dialog).to_contain_text("news@amazon.de")
    expect(sender_dialog).to_contain_text("odd@unexpected.example")
    sender_dialog.locator(".dialog-close").click()

    page.locator("[data-action-required-open]").click()
    action_dialog = page.locator("dialog[data-action-required-dialog]")
    expect(action_dialog).to_be_visible()
    amazon_review = action_dialog.locator(".unexpected-review-alias").filter(has_text=AMAZON)
    unexpected_sender = amazon_review.locator(".sender-stats-row.unexpected")
    expect(unexpected_sender).to_have_count(1)
    expect(unexpected_sender).to_contain_text("odd@unexpected.example")

    unexpected_sender.locator('.sender-review-form button[type="submit"]').click()

    expect(action_dialog).to_be_visible(timeout=5000)
    expect(action_dialog.locator(".unexpected-review-alias")).to_have_count(0)
    expect(action_dialog).to_contain_text("Used offline aliases")
    action_dialog.locator(".dialog-close").click()
    expect(page.locator("[data-unexpected-filter] span")).to_have_text("0", timeout=5000)


def test_action_required_can_disable_per_alias_unexpected_review(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url, dismiss_action=False)

    dialog = page.locator("dialog[data-action-required-dialog]")
    amazon_review = dialog.locator(".unexpected-review-alias").filter(has_text=AMAZON)
    checkbox = amazon_review.locator(".sender-review-settings input[type=checkbox]")
    expect(checkbox).not_to_be_checked()
    checkbox.check()

    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator(".unexpected-review-alias")).to_have_count(0)
    expect(page.locator("[data-unexpected-filter] span")).to_have_text("0", timeout=5000)
    dialog.locator(".dialog-close").click()

    fresh_row = _alias_row(page, AMAZON)
    expect(fresh_row.locator(".sender-review-muted")).to_be_visible()


def test_action_required_can_replace_alias_and_continue(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url, dismiss_action=False)

    action_dialog = page.locator("dialog[data-action-required-dialog]")
    amazon_review = action_dialog.locator(".unexpected-review-alias").filter(has_text=AMAZON)
    replace_button = amazon_review.locator('[data-review-replace-alias="1"]')
    expect(replace_button).to_be_visible()
    replace_button.click()

    replacement_dialog = page.locator("dialog.assign-dialog[open]").filter(
        has=page.locator('input[name="replacement-mode"]')
    )
    expect(replacement_dialog).to_be_visible()
    replacement_dialog.locator(
        'label.mode-option:has(input[value="custom"])'
    ).click()
    replacement_dialog.locator(".address-input input").fill("amazon-safe")
    replacement_dialog.locator(".button.primary").click()

    result_dialog = page.locator("dialog.assign-dialog-single[open]").filter(
        has_text="Alias replaced"
    )
    expect(result_dialog).to_be_visible(timeout=5000)
    expect(result_dialog).to_contain_text("amazon-safe@example.org")
    result_dialog.locator(".dialog-close").click()

    expect(action_dialog).to_be_visible(timeout=5000)
    expect(action_dialog.locator(".unexpected-review-alias")).to_have_count(0)
    expect(action_dialog).to_contain_text("Used offline aliases")
    action_dialog.locator(".dialog-close").click()

    old_alias = _alias_row(page, AMAZON)
    expect(old_alias).to_have_count(1)
    expect(old_alias.locator("[data-alias-select]")).to_have_attribute("data-active", "0")
    new_alias = _alias_row(page, "amazon-safe@example.org")
    expect(new_alias).to_have_count(1)
    expect(new_alias.locator(".alias-info strong")).to_have_text("Amazon")
    expect(new_alias.locator("[data-alias-select]")).to_have_attribute("data-sogo", "1")


def test_used_offline_alias_stays_protected_and_sender_dialog_survives_filter(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    used = _pool_item(page, USED_POOL)
    unused = _pool_item(page, UNUSED_POOL)
    expect(used).to_have_count(1)
    expect(unused).to_have_count(1)

    expect(used.locator('form[action$="/delete-reserved"]')).to_have_count(0)
    expect(unused.locator('form[action$="/delete-reserved"]')).to_have_count(1)

    used_assign_box = used.locator("[data-open-assign-dialog]").bounding_box()
    unused_assign_box = unused.locator("[data-open-assign-dialog]").bounding_box()
    used_copy_box = used.locator("[data-copy]").bounding_box()
    unused_copy_box = unused.locator("[data-copy]").bounding_box()
    assert used_assign_box and unused_assign_box and used_copy_box and unused_copy_box
    assert abs(used_assign_box["x"] - unused_assign_box["x"]) <= 1
    assert abs(used_copy_box["x"] - unused_copy_box["x"]) <= 1

    page.locator("[data-unexpected-filter]").click()
    expect(page).to_have_url(re.compile(r"[?&]status=unexpected(?:&|$)"))
    expect(page.locator(".alias-list .alias-row")).to_have_count(1, timeout=5000)

    pool_sender_trigger = used.locator(".sender-stats-trigger")
    expect(pool_sender_trigger).to_be_visible()
    pool_sender_trigger.click()
    stable_dialog = page.locator('dialog[data-review-pool-dialog="11"]')
    expect(stable_dialog).to_be_visible()
    expect(stable_dialog).to_contain_text("booking@example.net")
    stable_dialog.locator(".dialog-close").click()

    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"],
        origin=base_url,
    )
    page.locator("[data-copy-pool]").click()
    clipboard = page.evaluate("navigator.clipboard.readText()")
    assert UNUSED_POOL in clipboard
    assert USED_POOL not in clipboard

    exported = page.evaluate(
        "async () => await (await fetch('/aliases/pool.txt')).text()"
    )
    assert UNUSED_POOL in exported
    assert USED_POOL not in exported


def test_action_required_assigns_used_offline_alias(page: Page, base_url: str) -> None:
    _login(page, base_url, dismiss_action=False)

    dialog = page.locator("dialog[data-action-required-dialog]")
    row = dialog.locator('[data-pool-alias-id="11"]')
    expect(row).to_be_visible()
    row.locator(".used-pool-purpose input").fill("Hotel booking")
    dialog.locator(".used-pool-actions .primary").click()

    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator('[data-pool-alias-id="11"]')).to_have_count(0)
    expect(dialog).to_contain_text("Unexpected senders")
    dialog.locator(".dialog-close").click()

    assigned = _alias_row(page, USED_POOL)
    expect(assigned).to_have_count(1)
    expect(assigned.locator(".alias-info strong")).to_have_text("Hotel booking")
    expect(_pool_item(page, USED_POOL)).to_have_count(0)


def test_action_required_empty_state_after_pending_work_is_resolved(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url, dismiss_action=False)
    dialog = page.locator("dialog[data-action-required-dialog]")

    pool_row = dialog.locator('[data-pool-alias-id="11"]')
    pool_row.locator(".used-pool-purpose input").fill("Hotel booking")
    dialog.locator(".used-pool-actions .primary").click()

    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator(".unexpected-review-alias")).to_have_count(2)

    amazon_review = dialog.locator(".unexpected-review-alias").filter(has_text=AMAZON)
    amazon_sender = amazon_review.locator(".sender-stats-row.unexpected")
    expect(amazon_sender).to_have_count(1)
    expect(amazon_sender).to_contain_text("odd@unexpected.example")
    amazon_sender.locator('.sender-review-form button[type="submit"]').click()

    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator(".unexpected-review-alias")).to_have_count(1)
    assigned_review = dialog.locator(".unexpected-review-alias").filter(has_text=USED_POOL)
    assigned_sender = assigned_review.locator(".sender-stats-row.unexpected")
    expect(assigned_sender).to_have_count(1)
    expect(assigned_sender).to_contain_text("booking@example.net")
    assigned_sender.locator('.sender-review-form button[type="submit"]').click()

    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator(".action-required-empty")).to_have_text("Nothing to do.")


def test_expired_browser_session_redirects_to_login(page: Page, base_url: str) -> None:
    _login(page, base_url)

    page.context.clear_cookies()
    page.reload()

    expect(page).to_have_url(f"{base_url}/")
    expect(page.locator('a[href="/login"]')).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("Authentication required")


def test_mobile_action_required_and_alias_actions_stay_inside_viewport(
    page: Page,
    base_url: str,
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url, dismiss_action=False)

    dialog = page.locator("dialog[data-action-required-dialog]")
    expect(dialog).to_be_visible()
    box = dialog.bounding_box()
    assert box
    assert box["x"] >= -1
    assert box["y"] >= -1
    assert box["x"] + box["width"] <= 391
    assert box["y"] + box["height"] <= 845
    dialog.locator(".dialog-close").click()

    amazon_row = _alias_row(page, AMAZON)
    expect(amazon_row.locator(".alias-copy-action")).to_be_visible()
    expect(amazon_row.locator("details.alias-edit-action > summary")).to_be_visible()
    expect(amazon_row.locator(".alias-toggle-action button")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
