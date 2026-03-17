"""
Pytest fixtures for Clinical Ally E2E tests.

Note: Playwright for Firefox cannot auto-load unpacked extensions at launch time
(unlike Chromium which supports --load-extension). Sprint 1 uses page.add_script_tag()
to inject content.js directly.
TODO Sprint 2: load extension via web-ext + Playwright Firefox profile trick.
"""

import pytest
from playwright.sync_api import sync_playwright, Browser, Page


@pytest.fixture(scope="session")
def browser() -> Browser:
    with sync_playwright() as pw:
        # headed=True so the tester can see the sidebar during development
        # Set headless=True in CI
        browser = pw.firefox.launch(headless=False)
        yield browser
        browser.close()


@pytest.fixture()
def page(browser: Browser) -> Page:
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()
