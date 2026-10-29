"""Contoso Insurance - demo target website for browser-automation demos.

Sections
--------
/                     Hardened public site: search, products, quote calculator, FAQ, agents, claim wizard
/bug-lab/...          "Beta" claim wizard with planted UI defects (QA / troubleshooting demos)
/security-lab/...     Pages with planted, harmless security misconfigurations (passive review demos)
/security-lab/secure  Hardened twin of the security lab page (before/after comparison)
/api/claims/{ref}     JSON read-back used by the scenario runner to verify submitted claims

Everything is fictitious. There is no real data, no real credential, and no exploitable
server-side vulnerability: the "lab" pages only *look* misconfigured (headers, comments,
cookies, form attributes) so that agents have something realistic to find.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from data import AGENTS, ARTICLES, CITIES, CLAIM_CATEGORIES, COVERAGE, LANGUAGES, PRODUCTS, SPECIALTIES

BASE_DIR = Path(__file__).resolve().parent
SITE_NAME = "Contoso Insurance"
MAX_STORED_CLAIMS = 500

app = FastAPI(title=f"{SITE_NAME} (demo)", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals.update(site_name=SITE_NAME, current_year=date.today().year)

CLAIMS: dict[str, dict] = {}

HARDENED_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "frame-ancestors 'none'; form-action 'self'; base-uri 'self'; object-src 'none'"
    ),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Deliberately weak headers served only under /security-lab (except /security-lab/secure).
LAB_HEADERS = {
    "Server": "Apache/2.2.15 (CentOS)",
    "X-Powered-By": "PHP/5.4.16",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Credentials": "true",
}


def _is_insecure_lab(path: str) -> bool:
    return path.startswith("/security-lab") and not path.startswith("/security-lab/secure")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if _is_insecure_lab(request.url.path):
            for name, value in LAB_HEADERS.items():
                response.headers[name] = value
        else:
            for name, value in HARDENED_HEADERS.items():
                response.headers.setdefault(name, value)
            response.headers["Server"] = "contoso-web"
        # Keep the demo site out of search engines.
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response


app.add_middleware(SecurityHeadersMiddleware)


def render(request: Request, template: str, status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, template, context, status_code=status_code)


# --------------------------------------------------------------------------- public site


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    response = render(request, "index.html", products=PRODUCTS[:3], articles=ARTICLES[:4])
    response.set_cookie("cid_session", secrets.token_urlsafe(16), secure=True, httponly=True, samesite="lax")
    return response


def _search(query: str, category: str) -> list[dict]:
    terms = [t for t in re.split(r"\W+", query.lower()) if t]
    results = []
    for article in ARTICLES:
        if category and article["category"] != category:
            continue
        haystack = " ".join([article["title"], article["summary"], article["body"], " ".join(article["tags"])]).lower()
        score = sum(haystack.count(term) * (3 if term in article["title"].lower() else 1) for term in terms)
        if score or not terms:
            results.append({**article, "score": score})
    return sorted(results, key=lambda a: (-a["score"], a["title"]))


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", category: str = ""):
    categories = sorted({a["category"] for a in ARTICLES})
    results = _search(q, category) if q or category else []
    return render(request, "search.html", q=q, category=category, categories=categories, results=results)


@app.get("/articles/{slug}", response_class=HTMLResponse)
def article(request: Request, slug: str):
    item = next((a for a in ARTICLES if a["slug"] == slug), None)
    if not item:
        return not_found_page(request)
    related = [a for a in ARTICLES if a["category"] == item["category"] and a["slug"] != slug][:3]
    return render(request, "article.html", article=item, related=related)


@app.get("/products", response_class=HTMLResponse)
def products(request: Request, type: str = ""):
    items = [p for p in PRODUCTS if not type or p["type"] == type]
    return render(request, "products.html", products=items, selected_type=type)


@app.get("/products/compare", response_class=HTMLResponse)
def compare(request: Request, plans: list[str] = Query([])):
    chosen = [p for p in PRODUCTS if p["slug"] in plans]
    error = None if len(chosen) >= 2 else "Select at least two plans to compare."
    return render(request, "compare.html", plans=chosen, error=error)


def calculate_quote(product: dict, age: int, add_ons: list[str], payment: str) -> dict:
    base = product["monthly_premium"]
    age_factor = 1.35 if age < 25 else (1.15 if age >= 70 else 1.0)
    add_on_prices = {"roadside-plus": 6.0, "legal-cover": 4.5, "gadget-cover": 7.0, "extreme-sports": 8.0}
    add_on_total = sum(add_on_prices.get(a, 0.0) for a in add_ons)
    monthly = round(base * age_factor + add_on_total, 2)
    annual = round(monthly * 12 * (0.92 if payment == "annual" else 1.0), 2)
    return {
        "base": base,
        "age_factor": age_factor,
        "add_on_total": add_on_total,
        "monthly": monthly,
        "annual": annual,
        "discount": "8% annual payment discount" if payment == "annual" else "none",
    }


@app.get("/quote", response_class=HTMLResponse)
def quote_form(request: Request):
    return render(request, "quote.html", products=PRODUCTS, result=None, form={})


@app.post("/quote", response_class=HTMLResponse)
def quote_submit(
    request: Request,
    plan: str = Form(...),
    age: int = Form(...),
    zip_code: str = Form(...),
    payment: str = Form("monthly"),
    add_ons: list[str] = Form([]),
):
    errors = []
    product = next((p for p in PRODUCTS if p["slug"] == plan), None)
    if not product:
        errors.append("Choose a plan.")
    if not 16 <= age <= 99:
        errors.append("Age must be between 16 and 99.")
    if not re.fullmatch(r"\d{5}", zip_code):
        errors.append("ZIP code must have 5 digits.")
    form = {"plan": plan, "age": age, "zip_code": zip_code, "payment": payment, "add_ons": add_ons}
    if errors:
        return render(request, "quote.html", products=PRODUCTS, result=None, form=form, errors=errors, status_code=400)
    quote_ref = f"Q-{secrets.randbelow(900000) + 100000}"
    result = {"ref": quote_ref, "product": product, **calculate_quote(product, age, add_ons, payment)}
    return render(request, "quote.html", products=PRODUCTS, result=result, form=form)


@app.get("/faq", response_class=HTMLResponse)
def faq(request: Request):
    return render(request, "faq.html", articles=ARTICLES)


@app.get("/agents", response_class=HTMLResponse)
def agents(request: Request, city: str = "", specialty: str = "", language: list[str] = Query([])):
    searched = bool(city or specialty or language)
    results = [
        a for a in AGENTS
        if (not city or a["city"] == city)
        and (not specialty or specialty in a["specialties"])
        and all(lang in a["languages"] for lang in language)
    ] if searched else []
    return render(
        request, "agents.html", cities=CITIES, specialties=SPECIALTIES, languages=LANGUAGES,
        city=city, specialty=specialty, selected_languages=language, results=results, searched=searched,
    )


@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request):
    return render(request, "terms.html")


# --------------------------------------------------------------------------- claim wizard

PHONE_DIGITS = re.compile(r"\d")
POLICY_RE = re.compile(r"^CI-\d{6}$", re.IGNORECASE)
POLICE_RE = re.compile(r"^PR-\d{4,8}$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_amount(raw: str) -> float | None:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if 0 < value <= 1_000_000 else None


def validate_claim(f: dict) -> list[str]:
    errors = []
    for field in ("first_name", "last_name"):
        if not 2 <= len(f.get(field, "").strip()) <= 50:
            errors.append(f"{field.replace('_', ' ').capitalize()} must be 2-50 characters.")
    if not EMAIL_RE.match(f.get("email", "")):
        errors.append("Enter a valid email address.")
    if not 10 <= len(PHONE_DIGITS.findall(f.get("phone", ""))) <= 15:
        errors.append("Enter a valid phone number (10-15 digits).")
    try:
        dob = date.fromisoformat(f.get("dob", ""))
        age = (date.today() - dob).days // 365
        if not 18 <= age <= 120:
            errors.append("Policyholder must be at least 18 years old.")
    except ValueError:
        errors.append("Enter a valid date of birth.")
    if f.get("contact_method") not in {"email", "phone", "sms"}:
        errors.append("Choose a preferred contact method.")
    if not POLICY_RE.match(f.get("policy_number", "")):
        errors.append("Policy number must look like CI-123456.")
    policy_type = f.get("policy_type", "")
    if policy_type not in COVERAGE:
        errors.append("Choose a policy type.")
    elif f.get("coverage_level") not in COVERAGE[policy_type]:
        errors.append("Choose a coverage level.")
    try:
        incident = date.fromisoformat(f.get("incident_date", ""))
        if incident > date.today():
            errors.append("Incident date cannot be in the future.")
    except ValueError:
        errors.append("Enter a valid incident date.")
    if policy_type in CLAIM_CATEGORIES and f.get("claim_category") not in CLAIM_CATEGORIES[policy_type]:
        errors.append("Choose a claim category.")
    if parse_amount(f.get("estimated_amount", "")) is None:
        errors.append("Estimated amount must be a number between 1 and 1,000,000.")
    if len(f.get("description", "").strip()) < 30:
        errors.append("Description must be at least 30 characters.")
    if f.get("police_report") not in {"yes", "no"}:
        errors.append("Tell us whether a police report was filed.")
    elif f.get("police_report") == "yes" and not POLICE_RE.match(f.get("police_report_number", "")):
        errors.append("Police report number must look like PR-1234.")
    if f.get("witnesses") == "on":
        try:
            if not 1 <= int(f.get("witness_count", "0")) <= 10:
                raise ValueError
        except ValueError:
            errors.append("Number of witnesses must be between 1 and 10.")
    if f.get("consent") != "on":
        errors.append("You must confirm the declaration.")
    return errors


def _wizard_context(buggy: bool) -> dict:
    return {
        "buggy": buggy,
        "coverage": COVERAGE,
        "categories": CLAIM_CATEGORIES,
        "today": date.today().isoformat(),
        "form_action": "/claim" if buggy else "/claims",
    }


@app.get("/claims/new", response_class=HTMLResponse)
def claim_new(request: Request):
    return render(request, "claim_wizard.html", **_wizard_context(buggy=False))


@app.post("/claims", response_class=HTMLResponse)
async def claim_submit(request: Request):
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    errors = validate_claim(data)
    if errors:
        return render(request, "claim_errors.html", errors=errors, status_code=400)
    ref = f"CLM-{date.today().year}-{secrets.randbelow(90000) + 10000}"
    record = {
        "reference": ref,
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policyholder": f"{data['first_name'].strip()} {data['last_name'].strip()}",
        "email": data["email"],
        "policy_number": data["policy_number"].upper(),
        "policy_type": data["policy_type"],
        "coverage_level": data["coverage_level"],
        "incident_date": data["incident_date"],
        "claim_category": data["claim_category"],
        "estimated_amount": parse_amount(data["estimated_amount"]),
        "police_report_number": data.get("police_report_number") or None,
        "witness_count": int(data["witness_count"]) if data.get("witnesses") == "on" else 0,
        "photos_available": data.get("photos_available") == "on",
        "status": "Received",
    }
    if len(CLAIMS) >= MAX_STORED_CLAIMS:
        CLAIMS.pop(next(iter(CLAIMS)))
    CLAIMS[ref] = record
    return RedirectResponse(url=f"/claims/confirmation/{ref}", status_code=303)


@app.get("/claims/confirmation/{ref}", response_class=HTMLResponse)
def claim_confirmation(request: Request, ref: str):
    record = CLAIMS.get(ref)
    if not record:
        return not_found_page(request)
    return render(request, "claim_confirmation.html", claim=record)


@app.get("/api/claims/{ref}")
def api_claim(ref: str):
    record = CLAIMS.get(ref.upper())
    if not record:
        return JSONResponse({"error": "not_found", "reference": ref}, status_code=404)
    return record


@app.get("/api/claims")
def api_claims(limit: int = 20):
    return list(CLAIMS.values())[-max(1, min(limit, 100)):]


# --------------------------------------------------------------------------- bug lab


@app.get("/bug-lab", response_class=HTMLResponse)
def bug_lab(request: Request):
    return render(request, "bug_lab.html")


@app.get("/bug-lab/claims/new", response_class=HTMLResponse)
def bug_lab_claim(request: Request):
    return render(request, "claim_wizard.html", **_wizard_context(buggy=True))


# --------------------------------------------------------------------------- security lab


@app.get("/security-lab", response_class=HTMLResponse)
@app.get("/security-lab/", response_class=HTMLResponse)
def security_lab(request: Request):
    response = render(request, "security_lab.html", message=None)
    # Planted: session cookie without Secure / HttpOnly / SameSite, plus a debug flag cookie.
    response.headers.append("Set-Cookie", f"sessionid={secrets.token_hex(12)}; Path=/")
    response.headers.append("Set-Cookie", "debug_mode=true; Path=/")
    return response


@app.get("/security-lab/login", response_class=HTMLResponse)
def security_lab_login(request: Request, username: str = "", password: str = ""):
    # Planted: verbose errors enable username enumeration. Nothing is ever authenticated.
    if not username:
        message = "Please enter a username."
    elif username.lower() == "admin":
        message = "Invalid password for user 'admin'."
    else:
        message = f"User '{username}' does not exist."
    return render(request, "security_lab.html", message=message, status_code=401)


@app.get("/security-lab/backup/", response_class=HTMLResponse)
def security_lab_backup(request: Request):
    files = [
        ("db_backup_2026-09-30.sql.gz", "2026-09-30 02:00", "48M"),
        ("config.php.bak", "2026-08-14 11:22", "3.1K"),
        (".env.old", "2026-07-02 09:15", "812"),
    ]
    return render(request, "security_backup.html", files=files)


@app.get("/security-lab/backup/{name}", response_class=PlainTextResponse)
def security_lab_backup_file(name: str):
    return PlainTextResponse("403 Forbidden", status_code=403)


@app.get("/security-lab/admin-old/", response_class=PlainTextResponse)
def security_lab_admin_old():
    return PlainTextResponse("403 Forbidden - legacy admin console disabled", status_code=403)


@app.get("/security-lab/secure", response_class=HTMLResponse)
def security_lab_secure(request: Request):
    response = render(request, "security_secure.html", csrf_token=secrets.token_urlsafe(24))
    response.set_cookie("sessionid", secrets.token_hex(12), secure=True, httponly=True, samesite="strict")
    return response


@app.post("/security-lab/secure/login", response_class=HTMLResponse)
def security_lab_secure_login(request: Request, username: str = Form(""), password: str = Form(""), csrf_token: str = Form("")):
    return render(
        request, "security_secure.html", csrf_token=secrets.token_urlsafe(24),
        message="Sign-in failed. Check your credentials and try again.", status_code=401,
    )


# --------------------------------------------------------------------------- misc


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /security-lab/admin-old/\nDisallow: /security-lab/backup/\n"


@app.get("/.well-known/security.txt", response_class=PlainTextResponse)
def security_txt():
    return (
        "Contact: mailto:security@contoso-insurance.example\n"
        "Expires: 2027-12-31T23:59:59Z\n"
        "Preferred-Languages: en\n"
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "claims_stored": len(CLAIMS), "version": os.getenv("APP_VERSION", "1.0.0")}


def not_found_page(request: Request) -> HTMLResponse:
    return render(request, "not_found.html", status_code=404)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return not_found_page(request)
    if exc.status_code == 405:
        return render(request, "not_found.html", status_code=405)
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
