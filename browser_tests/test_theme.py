from __future__ import annotations

from playwright.sync_api import Page, expect


def test_theme_follows_system_and_persists_explicit_choice(page: Page, base_url: str) -> None:
    page.emulate_media(color_scheme="dark")
    page.goto(base_url)

    root = page.locator("html")
    theme_select = page.locator("[data-theme-select]")
    theme_color = page.locator('meta[name="theme-color"]')

    expect(theme_select).to_have_value("system")
    expect(root).to_have_attribute("data-theme-preference", "system")
    expect(root).to_have_attribute("data-theme", "dark")
    expect(theme_color).to_have_attribute("content", "#101418")

    theme_select.select_option("light")
    expect(root).to_have_attribute("data-theme-preference", "light")
    expect(root).to_have_attribute("data-theme", "light")
    expect(theme_color).to_have_attribute("content", "#f6f8fa")
    assert page.evaluate("window.localStorage.getItem('moolias-theme')") == "light"

    page.reload()
    expect(page.locator("[data-theme-select]")).to_have_value("light")
    expect(root).to_have_attribute("data-theme", "light")

    page.locator("[data-theme-select]").select_option("system")
    expect(root).to_have_attribute("data-theme", "dark")
    assert page.evaluate("window.localStorage.getItem('moolias-theme')") == "system"

    page.emulate_media(color_scheme="light")
    expect(root).to_have_attribute("data-theme", "light")
    expect(theme_color).to_have_attribute("content", "#f6f8fa")
