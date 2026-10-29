"""End-to-end browser tests for the demo site's JavaScript (correct wizard + planted bug-lab defects).

Runs the site locally with uvicorn and drives it with Playwright Chromium.
Skipped automatically when Playwright browsers are not installed.
"""

import socket
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
SITE_DIR = Path(__file__).resolve().parents[1] / "src" / "demo_site"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--port", str(port), "--no-server-header"],
                            cwd=SITE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(url + "/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield url
    proc.terminate()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browsers not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


def _step1(page, phone="+1 425-555-0100"):
    page.fill("#first_name", "Ana")
    page.fill("#last_name", "Morales")
    page.fill("#email", "ana@example.com")
    page.fill("#phone", phone)
    page.fill("#dob", "1988-04-12")
    page.check("input[name=contact_method][value=email]")


def test_happy_path_claim(base_url, browser):
    page = browser.new_page()
    page.goto(base_url + "/claims/new")
    _step1(page)
    page.click("fieldset[data-step='1'] [data-next]")
    page.fill("#policy_number", "CI-100200")
    page.select_option("#policy_type", "travel")
    assert page.locator("#coverage_level option").count() == 3  # placeholder + 2 travel options
    page.select_option("#coverage_level", "Annual multi-trip")
    page.click("fieldset[data-step='2'] [data-next]")
    page.fill("#incident_date", (date.today() - timedelta(days=2)).isoformat())
    page.select_option("#claim_category", "Lost baggage")
    page.fill("#estimated_amount", "1,250.50")
    page.fill("#description", "My suitcase did not arrive at the destination airport after the flight.")
    page.check("input[name=police_report][value=no]")
    page.check("#witnesses")
    assert page.is_visible("#witness_count")
    page.fill("#witness_count", "2")
    page.click("fieldset[data-step='3'] [data-next]")
    assert "$1,250.50" in page.inner_text("#review-summary")
    page.check("#consent")
    page.click("#submit-claim")
    page.wait_for_url("**/claims/confirmation/**")
    assert page.inner_text("#claim-reference").startswith("CLM-")


def test_validation_blocks_future_date(base_url, browser):
    page = browser.new_page()
    page.goto(base_url + "/claims/new")
    _step1(page)
    page.click("fieldset[data-step='1'] [data-next]")
    page.fill("#policy_number", "CI-100200")
    page.select_option("#policy_type", "home")
    page.select_option("#coverage_level", "Plus")
    page.click("fieldset[data-step='2'] [data-next]")
    page.fill("#incident_date", (date.today() + timedelta(days=10)).isoformat())
    page.click("fieldset[data-step='3'] [data-next]")
    assert "future" in page.inner_text("#incident_date-error")


def test_bug_lab_defects(base_url, browser):
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(base_url + "/bug-lab/claims/new")
    # BL-01: the close button does not dismiss the cookie dialog, "Accept all" does.
    page.click("#cookie-close")
    assert page.is_visible("#cookie-banner")
    page.click("#cookie-accept")
    assert not page.is_visible("#cookie-banner")
    # BL-03: valid formatted phone number is rejected.
    _step1(page)
    page.click("fieldset[data-step='1'] [data-next]")
    assert "valid phone" in page.inner_text("#phone-error").lower()
    page.fill("#phone", "4255550100")
    page.click("fieldset[data-step='1'] [data-next]")
    # BL-05: travel has no coverage options.
    page.fill("#policy_number", "CI-300400")
    page.select_option("#policy_type", "travel")
    assert page.locator("#coverage_level option").count() == 1
    page.select_option("#policy_type", "home")
    page.select_option("#coverage_level", "Plus")
    page.click("fieldset[data-step='2'] [data-next]")
    # BL-08: JavaScript TypeError when step 3 initialises; witness count never appears.
    page.wait_for_timeout(300)
    assert any("addEventListener" in e or "null" in e for e in errors), errors
    page.check("#witnesses")
    assert not page.is_visible("#witness_count")
    # BL-09: Back on step 3 goes to step 1.
    page.click("fieldset[data-step='3'] [data-back]")
    assert page.is_visible("fieldset[data-step='1']")
    page.click("fieldset[data-step='1'] [data-next]")
    page.click("fieldset[data-step='2'] [data-next]")
    # BL-06: future incident date accepted; BL-07: amount parsed wrongly in the summary.
    page.fill("#incident_date", (date.today() + timedelta(days=30)).isoformat())
    page.select_option("#claim_category", "Water damage")
    page.fill("#estimated_amount", "1,250.50")
    page.fill("#description", "A pipe burst under the kitchen sink and flooded the floor overnight.")
    page.check("input[name=police_report][value=no]")
    page.click("fieldset[data-step='3'] [data-next]")
    assert "$1.00" in page.inner_text("#review-summary")
    # BL-10: submitting lands on a 404 page.
    page.check("#consent")
    page.click("#submit-claim")
    page.wait_for_load_state()
    assert "404" in page.inner_text("h1")
