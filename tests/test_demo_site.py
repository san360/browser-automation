"""Tests for the Contoso Insurance demo target site."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app as site

client = TestClient(site.app)

VALID_CLAIM = {
    "first_name": "Ana", "last_name": "Morales", "email": "ana@example.com", "phone": "+1 425-555-0100",
    "dob": "1988-04-12", "contact_method": "email", "policy_number": "CI-100200", "policy_type": "home",
    "coverage_level": "Plus", "incident_date": (date.today() - timedelta(days=3)).isoformat(),
    "claim_category": "Water damage", "estimated_amount": "1,250.50",
    "description": "A pipe burst under the kitchen sink and flooded the floor.", "police_report": "no",
    "witnesses": "on", "witness_count": "2", "photos_available": "on", "consent": "on",
}


@pytest.mark.parametrize("path", ["/", "/search?q=deductible", "/products", "/products/compare?plans=auto-basic&plans=auto-plus",
                                  "/quote", "/faq", "/agents?city=Seattle", "/claims/new", "/bug-lab/claims/new", "/terms"])
def test_public_pages_are_hardened(path):
    response = client.get(path)
    assert response.status_code == 200
    assert "content-security-policy" in response.headers
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["server"] == "contoso-web"


def test_security_lab_is_deliberately_weak():
    response = client.get("/security-lab/")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-powered-by"].startswith("PHP/")
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("sessionid=") and "HttpOnly" not in c for c in cookies)
    assert "DEMO-NOT-A-REAL-KEY" in response.text


def test_hardened_twin_has_csrf_and_headers():
    response = client.get("/security-lab/secure")
    assert "csrf_token" in response.text
    assert "content-security-policy" in response.headers


def test_claim_submission_round_trip():
    response = client.post("/claims", data=VALID_CLAIM, follow_redirects=False)
    assert response.status_code == 303
    reference = response.headers["location"].rsplit("/", 1)[-1]
    record = client.get(f"/api/claims/{reference}").json()
    assert record["policy_number"] == "CI-100200"
    assert record["estimated_amount"] == pytest.approx(1250.5)
    assert record["witness_count"] == 2


@pytest.mark.parametrize("field,value,message", [
    ("incident_date", (date.today() + timedelta(days=5)).isoformat(), "future"),
    ("policy_number", "100200", "CI-123456"),
    ("phone", "12345", "phone"),
])
def test_claim_validation(field, value, message):
    response = client.post("/claims", data={**VALID_CLAIM, field: value})
    assert response.status_code == 400
    assert message.lower() in response.text.lower()


def test_quote_calculation_matches_scenario_expectations():
    product = next(p for p in site.PRODUCTS if p["slug"] == "auto-plus")
    assert site.calculate_quote(product, 23, ["roadside-plus"], "monthly")["monthly"] == pytest.approx(92.40)
    assert site.calculate_quote(product, 45, [], "annual")["annual"] == pytest.approx(706.56)
    assert site.calculate_quote(product, 72, ["legal-cover"], "monthly")["monthly"] == pytest.approx(78.10)


def test_bug_lab_has_planted_defects():
    page = client.get("/bug-lab/claims/new").text
    assert 'form id="claim-form"' in page and 'action="/claim"' in page  # BL-10 wrong endpoint
    assert "logo-v2.png" in page  # BL-02 broken logo
    assert 'for="policy-no"' in page  # BL-04 label mismatch
    assert client.get("/static/img/logo-v2.png").status_code == 404
    assert client.get("/terms-of-use").status_code == 404  # BL-11
    assert client.post("/claim", data=VALID_CLAIM).status_code == 404


def test_robots_and_security_txt():
    assert "admin-old" in client.get("/robots.txt").text
    assert client.get("/.well-known/security.txt").status_code == 200
