"""Browser smoke test for the web console: in-process uvicorn with the fake runner, driven by Playwright Chromium.

Skipped automatically when Playwright browsers are not installed.
"""

import socket
import threading
import time

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from demo_common.settings import Settings  # noqa: E402
from web_console.app import create_app  # noqa: E402
from web_console_fakes import LIVE_URL, FakeRunner  # noqa: E402

SETTINGS = Settings(project_endpoint="https://unit-test.services.ai.azure.com/api/projects/test",
                    demo_site_url="https://demo.contoso.example")  # same as tests/conftest.py (reserved domain)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def console_url(tmp_path_factory):
    runs = tmp_path_factory.mktemp("runs")
    port = _free_port()
    runner = FakeRunner(runs, delay=0.05)
    app = create_app(settings=SETTINGS, runs_dir=runs, runner=runner, port=port)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           timeout_graceful_shutdown=1))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    RUNNERS[0] = runner
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


RUNNERS = [None]


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browsers not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def context(browser):
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    context.route("https://live.playwright.microsoft.com/**", lambda route: route.fulfill(
        status=200, content_type="text/html", body="<title>Live view</title><p>live view stub</p>"))
    yield context
    context.close()


def open_run_page(context, url, mode):
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(f"{url}/#/run")
    page.wait_for_selector("#scenario-select option[value='02-site-search']", state="attached")
    if page.locator("#config-edit").is_visible():
        page.click("#config-edit")
    page.select_option("#scenario-select", "02-site-search")
    page.click(f".mode-card[data-mode='{mode}']")
    page.wait_for_function("() => !document.querySelector('#run-button').disabled")
    if page.locator("#live-run").is_hidden():
        assert "The browser preview appears here" in page.inner_text("#side-preview")
    return page, errors


def wait_until_done(page, mode_label):
    page.wait_for_selector(f"#live-meta:has-text('{mode_label}')", timeout=10000)
    page.wait_for_selector("#live-status:has-text('Completed')", timeout=30000)


def test_run_streams_timeline_answer_and_opens_the_live_view(console_url, context):
    page, errors = open_run_page(context, console_url, "prompt")
    with context.expect_page() as popup_info:
        page.click("#run-button")  # the live-view window opens inside the click, before the run starts
    popup = popup_info.value
    wait_until_done(page, "Prompt agent")
    popup.wait_for_url(f"{LIVE_URL}-prompt", timeout=10000)
    assert page.locator("#timeline li").count() >= 5
    assert "Open demo.contoso.example" in page.inner_text("#timeline")
    assert "Water damage: what's covered" in page.inner_text("#answer")
    assert page.inner_text("#checks-badge") == "2/2 passed"
    assert "test-browser-prompt" in page.inner_text("#live-sessions")
    assert page.get_by_role("button", name="Copy browser session ID test-browser-prompt", exact=True).is_visible()
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.bring_to_front()
    page.get_by_role("button", name="Copy browser session ID test-browser-prompt", exact=True).click()
    page.wait_for_selector("text=Browser session ID copied to the clipboard.")
    assert page.evaluate("navigator.clipboard.readText()") == "test-browser-prompt"
    preview = page.inner_text("#side-preview")
    assert "Cloud browser live view" in preview and "session has ended" in preview
    assert "demo.contoso.example" in page.inner_text("#side-preview .current-page")
    assert "signed-token" not in page.content()  # the signed link never appears as text in the console
    page.click("#tab-event")
    assert "signed-token" not in page.inner_text("#event-code")
    assert not errors


def test_browser_session_id_is_shown_during_run_and_in_history(console_url, context):
    RUNNERS[0].gate = threading.Event()
    try:
        page, errors = open_run_page(context, console_url, "prompt")
        page.click("#run-button")
        page.wait_for_selector("#live-status:has-text('Running')")
        page.wait_for_selector("#live-sessions:has-text('test-browser-prompt')")
        assert page.inner_text("#live-status") == "Running"
    finally:
        RUNNERS[0].gate.set()
        RUNNERS[0].gate = None
    wait_until_done(page, "Prompt agent")
    page.reload()
    page.wait_for_selector("#live-sessions:has-text('test-browser-prompt')")
    page.goto(f"{console_url}/#/history")
    page.wait_for_selector("#history-detail .browser-session-id:has-text('test-browser-prompt')")
    assert "signed-token" not in page.content()
    assert not errors


def test_live_view_fallback_when_windows_are_blocked(console_url, context):
    context.add_init_script("window.open = () => null;")  # like a popup blocker or an app's embedded browser
    page, errors = open_run_page(context, console_url, "hosted")
    page.click("#run-button")
    wait_until_done(page, "Hosted agent")
    assert len(context.pages) == 1
    assert "session has ended" in page.inner_text("#side-preview")
    # A second run, held mid-way by the gate, offers the button while its live-view link is still valid.
    RUNNERS[0].gate = threading.Event()
    try:
        page.click("#live-again")
        page.wait_for_selector("#side-preview button:has-text('Open live view'):not([disabled])", timeout=10000)
        assert "blocked the side window" in page.inner_text("#side-preview")
        page.click("#side-preview button:has-text('Open live view')")
        page.wait_for_selector("#side-preview .preview-status:has-text('cannot open windows')")
        assert page.locator("#side-preview button:has-text('Open live view')").is_hidden()
    finally:
        RUNNERS[0].gate.set()
        RUNNERS[0].gate = None
    page.wait_for_selector("#live-status:has-text('Completed')", timeout=30000)
    assert not errors


def test_computer_use_screenshots_fill_the_preview(console_url, context):
    page, errors = open_run_page(context, console_url, "cua")
    page.click("#run-button")
    wait_until_done(page, "Computer Use")
    page.wait_for_function("() => { const img = document.querySelector('#side-preview .screen img');"
                           " return img && !img.hidden && img.complete && img.naturalWidth > 0; }")
    assert page.locator("#side-preview .filmstrip button").count() == 2
    assert "What the model sees" in page.inner_text("#side-preview")
    assert len(context.pages) == 1  # no live-view window for Computer Use
    assert not errors


def test_catalog_history_and_costs_pages(console_url, context):
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(f"{console_url}/#/scenarios")
    page.wait_for_selector(".scenario-card h3")
    assert page.locator(".scenario-card").count() == 15  # 14 scenarios + the ad-hoc card
    page.fill("#catalog-search", "4-step claim")
    page.wait_for_function("() => document.querySelectorAll('.scenario-card').length === 1")
    page.click(".scenario-card button:has-text('Run')")
    page.wait_for_selector("#page-run:not([hidden])")
    assert page.input_value("#scenario-select") == "07-file-claim"
    calls = len(RUNNERS[0].calls)
    page.press("#input-first_name", "Enter")  # runs cost money: Enter in a field must not start one
    page.wait_for_timeout(500)
    assert len(RUNNERS[0].calls) == calls
    page.goto(f"{console_url}/#/history")
    page.wait_for_selector(".history-row")
    page.wait_for_selector("#history-detail .md h1")
    assert "Automatic checks" in page.inner_text("#history-detail")
    page.goto(f"{console_url}/#/costs")
    page.wait_for_selector("#costs-by-mode table")
    assert not errors
