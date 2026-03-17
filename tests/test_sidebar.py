"""
Sprint 1 E2E tests for Clinical Ally sidebar.

Prerequisites:
  - OpenEMR running at http://localhost/openemr/
  - LLM proxy running at http://localhost:8000
  - Ollama running at http://localhost:11434 with llama3 pulled

Run:
  pytest tests/ -v
"""

import pathlib
import pytest
from playwright.sync_api import Page, expect

OPENEMR_URL = "http://localhost/openemr/"
CONTENT_JS_PATH = pathlib.Path(__file__).parent.parent / "extension" / "content.js"

# LLM can be slow on CPU — allow generous timeout
LLM_TIMEOUT_MS = 90_000


def inject_sidebar(page: Page) -> None:
    """
    Inject content.js into the page.

    Sprint 1 workaround: Playwright Firefox can't sideload unpacked extensions,
    so we inject the script directly. Shadow DOM host will be created just as it
    would by the real extension — minus browser.runtime.getURL() for the iframe src.
    TODO Sprint 2: replace with real extension loading via web-ext.
    """
    js_source = CONTENT_JS_PATH.read_text()
    # Stub browser.runtime.getURL so the script doesn't throw when loading the iframe
    page.evaluate("""
        window.browser = window.browser || {
            runtime: {
                getURL: (path) => `http://localhost:8000/static/${path}`
            }
        };
    """)
    page.add_script_tag(content=js_source)


def test_sidebar_injects(page: Page) -> None:
    """Sidebar host element is created after content.js injection."""
    page.goto(OPENEMR_URL, wait_until="domcontentloaded")
    inject_sidebar(page)

    # Shadow host should exist in the DOM
    host = page.locator("#clinical-ally-host")
    expect(host).to_be_attached(timeout=5_000)


def test_sidebar_asks_question(page: Page) -> None:
    """
    Full round-trip: inject sidebar → type question → submit → assert non-empty response.

    Uses page.evaluate() for shadow DOM access because Playwright locators
    do not pierce shadow roots in Firefox.
    """
    page.goto(OPENEMR_URL, wait_until="domcontentloaded")
    inject_sidebar(page)

    # Wait for the iframe to be present inside shadow root
    page.wait_for_selector("#clinical-ally-host", timeout=5_000)

    # Type into the input inside the shadow DOM's iframe
    # Access via JavaScript since Playwright doesn't pierce shadow roots in Firefox
    page.evaluate("""
        const host = document.getElementById('clinical-ally-host');
        const shadow = host.shadowRoot;
        const iframe = shadow.querySelector('iframe');
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        const input = doc.getElementById('prompt-input');
        input.value = 'What is hypertension?';
        const form = doc.getElementById('prompt-form');
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    """)

    # Wait for a response message to appear (LLM can take a while on CPU)
    response_text = page.evaluate_handle("""
        () => new Promise((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error('Timeout waiting for response')), 90000);
            const host = document.getElementById('clinical-ally-host');
            const shadow = host.shadowRoot;
            const iframe = shadow.querySelector('iframe');
            const doc = iframe.contentDocument || iframe.contentWindow.document;
            const observer = new MutationObserver(() => {
                const msgs = doc.querySelectorAll('.message.assistant, .message.error');
                if (msgs.length > 0) {
                    clearTimeout(timeout);
                    observer.disconnect();
                    resolve(msgs[msgs.length - 1].textContent);
                }
            });
            observer.observe(doc.getElementById('response-area'), { childList: true, subtree: true });
        })
    """)

    response = page.evaluate("(handle) => handle", response_text)
    assert response, "Expected a non-empty response from the LLM"
    # TODO Sprint 2: assert response is NOT an error message
    # TODO Sprint 2: assert response contains clinically relevant content
