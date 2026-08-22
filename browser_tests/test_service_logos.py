from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def test_bundled_service_logo_and_restricted_fallback(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))

    github_badge = _alias_row(page, "github-m4@example.org").locator(".service-badge")
    github_logo = github_badge.locator("svg.service-logo use")
    expect(github_logo).to_have_count(1)
    expect(github_logo).to_have_attribute(
        "href",
        "/static/service-icons.svg#service-github",
    )
    page.wait_for_function(
        """() => {
            const logo = document.querySelector(
                '.alias-row:has([data-alias-select][data-address="github-m4@example.org"]) svg.service-logo'
            );
            if (!logo) return false;
            const box = logo.getBBox();
            return box.width > 0 && box.height > 0;
        }"""
    )

    amazon_badge = _alias_row(page, "amazon-k7@example.org").locator(".service-badge")
    expect(amazon_badge.locator("svg.service-logo")).to_have_count(0)
    expect(amazon_badge).to_have_text("A")
