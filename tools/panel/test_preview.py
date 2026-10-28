"""Exercise shipped panel with the standalone mock; requires Playwright Chromium."""

from __future__ import annotations

from pathlib import Path

from build import main


def test_preview():
    from playwright.sync_api import sync_playwright

    main()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((Path(__file__).parent / "preview.html").resolve().as_uri())
        panel = page.locator("everlights-panel")
        panel.locator(".pcard").first.wait_for()
        assert panel.locator(".pcard").count() == 2
        panel.locator(".send").click()
        page.wait_for_function("window.mockCalls.length > 0")
        assert page.evaluate("window.mockCalls[0].domain") == "everlights_v3"
        panel.locator(".add-playlist").first.click()
        panel.locator(".switch").click()
        page.wait_for_function("window.mockCalls.some(c=>c.service==='start_playlist')")
        panel.locator("#pattern-name").fill("Preview saved")
        panel.locator(".save-actions .save").click()
        page.wait_for_function("window.mockCalls.some(c=>c.service==='save_preset')")
        assert panel.locator(".pcard").count() == 3
        page.set_viewport_size({"width": 390, "height": 844})
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    test_preview()
    print("Panel preview checks passed")
