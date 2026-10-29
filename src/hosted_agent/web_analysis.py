"""Deterministic, read-only web analysis used by the hosted Web QA agent tools (no Agent Framework dependency).

The Browser Automation tool (via the Foundry Toolbox) sees the page the way a user does: DOM,
accessibility tree, console and network activity. It cannot see raw HTTP response headers or cookie
attributes, and the model should not guess them. These tools fill that gap with plain HTTP requests.

Safety rails (important for any agent that can reach the network):
* Only hosts listed in ALLOWED_SCAN_HOSTS (comma separated, "*.example.com" wildcards allowed) or the
  host of DEMO_SITE_URL can be analysed. Only scan systems you own or are authorised to test.
* URLs that resolve to private, loopback, link-local or otherwise non-public addresses are refused
  (SSRF protection, e.g. the instance metadata endpoint).
* Requests are GET/HEAD only, time-limited and size-limited. Nothing is submitted or exploited.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; FoundryWebQAAgent/1.0; +https://learn.microsoft.com/azure/foundry/)"
MAX_BODY_BYTES = 1_500_000
TIMEOUT = httpx.Timeout(15.0, connect=10.0)
SESSION_COOKIE_HINTS = ("session", "sid", "auth", "token", "jwt", "login")
SECRET_ASSIGNMENT = re.compile(
    r"""(?ix)\b(api[_-]?key|apikey|secret|client[_-]?secret|access[_-]?token|auth[_-]?token|password|passwd)\b
        \s*[:=]\s*["']([^"']{6,})["']"""
)
SUSPICIOUS_COMMENT = re.compile(
    r"(?i)\b(todo|fixme|hack|password|passwd|admin|secret|api[_ -]?key|token|debug|internal|staging|credential|default login|remove before)\b"
)
VERSION_BANNER = re.compile(r"(?i)\b(jquery|bootstrap|angular(?:js)?|react|vue|lodash|moment)[^\w]{0,3}v?(\d+\.\d+(?:\.\d+)?)")


class ScanNotAllowed(Exception):
    """Raised when a URL is outside the allow-list or resolves to a non-public address."""


@dataclass
class Finding:
    id: str
    severity: str  # High | Medium | Low | Info
    title: str
    evidence: str
    recommendation: str
    reference: str = ""


@dataclass
class Report:
    url: str
    final_url: str = ""
    status: int | None = None
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def add(self, *args, **kwargs) -> None:
        self.findings.append(Finding(*args, **kwargs))

    def to_json(self) -> str:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        payload = asdict(self)
        payload["summary"] = counts
        return json.dumps(payload, indent=1, ensure_ascii=False)


# --------------------------------------------------------------------------- allow-list + SSRF guard


def allowed_hosts() -> list[str]:
    hosts = [h.strip().lower() for h in os.getenv("ALLOWED_SCAN_HOSTS", "").split(",") if h.strip()]
    demo = os.getenv("DEMO_SITE_URL", "")
    if demo:
        host = urlparse(demo).hostname
        if host:
            hosts.append(host.lower())
    return sorted(set(hosts))


def host_is_allowed(host: str, allow: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for entry in allow:
        if entry.startswith("*.") and (host.endswith(entry[1:]) or host == entry[2:]):
            return True
        if host == entry:
            return True
    return False


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def validate_target(url: str) -> str:
    """Return the normalised URL or raise ScanNotAllowed."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ScanNotAllowed(f"Only absolute http(s) URLs can be analysed, got: {url!r}")
    allow = allowed_hosts()
    if not allow:
        raise ScanNotAllowed("No hosts are allowed. Set ALLOWED_SCAN_HOSTS or DEMO_SITE_URL.")
    if not host_is_allowed(parsed.hostname, allow):
        raise ScanNotAllowed(
            f"Host '{parsed.hostname}' is not in the scan allow-list {allow}. Only analyse sites you own or are authorised to test."
        )
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ScanNotAllowed(f"Cannot resolve host '{parsed.hostname}': {exc}") from exc
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise ScanNotAllowed(f"Host '{parsed.hostname}' resolves to a non-public address; refusing (SSRF protection).")
    return parsed.geturl()


async def _guard_request(request: httpx.Request) -> None:
    # Re-validate every hop, including redirects.
    validate_target(str(request.url))


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": USER_AGENT},
        event_hooks={"request": [_guard_request]},
    )


async def _fetch(client: httpx.AsyncClient, url: str, method: str = "GET") -> httpx.Response:
    return await client.request(method, url)


# --------------------------------------------------------------------------- header + cookie analysis


def _parse_set_cookie(raw: str) -> tuple[str, dict[str, str]]:
    parts = [p.strip() for p in raw.split(";")]
    name = parts[0].split("=", 1)[0] if parts and "=" in parts[0] else parts[0]
    attrs: dict[str, str] = {}
    for p in parts[1:]:
        key, _, value = p.partition("=")
        attrs[key.strip().lower()] = value.strip()
    return name, attrs


def analyse_headers(report: Report, response: httpx.Response) -> None:
    h = response.headers
    https = response.url.scheme == "https"
    report.data["headers"] = {
        k: v
        for k, v in h.items()
        if k.lower()
        in {
            "content-security-policy", "strict-transport-security", "x-frame-options", "x-content-type-options",
            "referrer-policy", "permissions-policy", "cross-origin-opener-policy", "server", "x-powered-by",
            "access-control-allow-origin", "access-control-allow-credentials", "x-aspnet-version", "cache-control",
        }
    }

    if not https:
        report.add("HDR-HTTPS", "High", "Page is served over plain HTTP", f"Final URL {response.url}",
                   "Serve the site over HTTPS only and redirect HTTP to HTTPS.", "OWASP A02:2021 Cryptographic Failures")
    hsts = h.get("strict-transport-security")
    if https and not hsts:
        report.add("HDR-HSTS", "Low", "Strict-Transport-Security header missing", "No HSTS header in response",
                   "Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains'.", "OWASP Secure Headers Project")
    elif hsts:
        match = re.search(r"max-age=(\d+)", hsts)
        if match and int(match.group(1)) < 15552000:
            report.add("HDR-HSTS-SHORT", "Low", "HSTS max-age shorter than 180 days", hsts,
                       "Use max-age of at least 15552000 (180 days).", "OWASP Secure Headers Project")

    csp = h.get("content-security-policy")
    if not csp:
        report.add("HDR-CSP", "Medium", "Content-Security-Policy header missing", "No CSP header in response",
                   "Define a restrictive CSP (default-src 'self'; frame-ancestors 'none'; ...).", "OWASP A05:2021 Security Misconfiguration")
    else:
        if "'unsafe-inline'" in csp or "'unsafe-eval'" in csp:
            report.add("HDR-CSP-WEAK", "Low", "CSP allows unsafe-inline or unsafe-eval", csp,
                       "Remove unsafe-inline/unsafe-eval; use nonces or hashes.", "OWASP A05:2021 Security Misconfiguration")
    frame_protected = bool(h.get("x-frame-options")) or (csp is not None and "frame-ancestors" in csp)
    if not frame_protected:
        report.add("HDR-CLICKJACK", "Medium", "No clickjacking protection (X-Frame-Options / frame-ancestors)",
                   "Neither X-Frame-Options nor CSP frame-ancestors is set",
                   "Add 'X-Frame-Options: DENY' or CSP 'frame-ancestors 'none''.", "OWASP A05:2021 Security Misconfiguration")
    if h.get("x-content-type-options", "").lower() != "nosniff":
        report.add("HDR-XCTO", "Low", "X-Content-Type-Options: nosniff missing", h.get("x-content-type-options", "absent"),
                   "Add 'X-Content-Type-Options: nosniff'.", "OWASP Secure Headers Project")
    if not h.get("referrer-policy"):
        report.add("HDR-REFERRER", "Low", "Referrer-Policy header missing", "absent",
                   "Add 'Referrer-Policy: strict-origin-when-cross-origin'.", "OWASP Secure Headers Project")
    if not h.get("permissions-policy"):
        report.add("HDR-PERMISSIONS", "Low", "Permissions-Policy header missing", "absent",
                   "Restrict powerful features, e.g. 'Permissions-Policy: camera=(), microphone=(), geolocation=()'.",
                   "OWASP Secure Headers Project")

    for name in ("server", "x-powered-by", "x-aspnet-version", "x-aspnetmvc-version"):
        value = h.get(name)
        if value and (name != "server" or re.search(r"\d", value)):
            report.add(f"HDR-DISCLOSE-{name.upper()}", "Low", f"'{name}' header discloses technology/version", f"{name}: {value}",
                       "Remove or genericise version banners.", "OWASP A05:2021 Security Misconfiguration")

    acao = h.get("access-control-allow-origin")
    if acao == "*" and h.get("access-control-allow-credentials", "").lower() == "true":
        report.add("HDR-CORS", "Medium", "CORS allows any origin together with credentials",
                   "Access-Control-Allow-Origin: * with Access-Control-Allow-Credentials: true",
                   "Allow only trusted origins and never combine a wildcard with credentials.", "OWASP A05:2021 Security Misconfiguration")
    elif acao == "*":
        report.add("HDR-CORS-WILDCARD", "Info", "CORS allows any origin", "Access-Control-Allow-Origin: *",
                   "Confirm the resource is intended to be public.", "OWASP A05:2021 Security Misconfiguration")

    cookies = response.headers.get_list("set-cookie")
    report.data["cookies"] = []
    for raw in cookies:
        name, attrs = _parse_set_cookie(raw)
        report.data["cookies"].append({"name": name, "attributes": sorted(attrs)})
        sensitive = any(hint in name.lower() for hint in SESSION_COOKIE_HINTS)
        if https and "secure" not in attrs:
            report.add(f"CK-SECURE-{name}", "Medium" if sensitive else "Low", f"Cookie '{name}' lacks the Secure flag", raw,
                       "Set the Secure attribute on all cookies served over HTTPS.", "OWASP A05:2021 Security Misconfiguration")
        if "httponly" not in attrs:
            report.add(f"CK-HTTPONLY-{name}", "Medium" if sensitive else "Low", f"Cookie '{name}' lacks HttpOnly", raw,
                       "Set HttpOnly so scripts cannot read the cookie.", "OWASP A05:2021 Security Misconfiguration")
        if "samesite" not in attrs:
            report.add(f"CK-SAMESITE-{name}", "Low", f"Cookie '{name}' has no SameSite attribute", raw,
                       "Set SameSite=Lax or Strict to reduce CSRF risk.", "OWASP A01:2021 Broken Access Control")


# --------------------------------------------------------------------------- HTML source analysis


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.comments: list[str] = []
        self.inline_scripts: list[str] = []
        self.forms: list[dict] = []
        self.resources: list[tuple[str, str]] = []  # (tag, url)
        self.links: list[tuple[str, str]] = []
        self.meta_generator: str | None = None
        self._in_inline_script = False
        self._script_buffer: list[str] = []
        self._current_form: dict | None = None

    def handle_comment(self, data: str) -> None:
        self.comments.append(data.strip())

    def handle_starttag(self, tag: str, attrs_list):
        attrs = {k.lower(): (v or "") for k, v in attrs_list}
        if tag == "script":
            if attrs.get("src"):
                self.resources.append(("script", attrs["src"]))
            elif attrs.get("type", "text/javascript") in ("", "text/javascript", "module", "application/javascript"):
                self._in_inline_script = True
                self._script_buffer = []
        elif tag in ("img", "iframe", "audio", "video", "source", "embed"):
            if attrs.get("src"):
                self.resources.append((tag, attrs["src"]))
        elif tag == "link" and attrs.get("href"):
            self.resources.append(("link", attrs["href"]))
        elif tag == "a" and attrs.get("href"):
            self.links.append(("a", attrs["href"]))
        elif tag == "meta" and attrs.get("name", "").lower() == "generator":
            self.meta_generator = attrs.get("content")
        elif tag == "form":
            self._current_form = {"method": attrs.get("method", "get").lower(), "action": attrs.get("action", ""),
                                  "id": attrs.get("id", ""), "inputs": []}
            self.forms.append(self._current_form)
        elif tag in ("input", "select", "textarea") and self._current_form is not None:
            self._current_form["inputs"].append({
                "tag": tag, "type": attrs.get("type", "text").lower(), "name": attrs.get("name", ""),
                "autocomplete": attrs.get("autocomplete", ""),
            })

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_inline_script:
            self.inline_scripts.append("".join(self._script_buffer))
            self._in_inline_script = False
        elif tag == "form":
            self._current_form = None

    def handle_data(self, data: str) -> None:
        if self._in_inline_script:
            self._script_buffer.append(data)


def _mask(secret: str) -> str:
    return secret[:4] + "…" + secret[-2:] if len(secret) > 8 else "…"


def analyse_source(report: Report, page_url: str, html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html[:MAX_BODY_BYTES])
    page = urlparse(page_url)

    for comment in parser.comments:
        if SUSPICIOUS_COMMENT.search(comment):
            report.add("SRC-COMMENT", "High" if re.search(r"(?i)password|credential|login", comment) else "Medium",
                       "HTML comment discloses sensitive information", comment[:240],
                       "Remove developer comments from production markup.", "OWASP A05:2021 Security Misconfiguration")

    for script in parser.inline_scripts:
        for match in SECRET_ASSIGNMENT.finditer(script):
            report.add("SRC-SECRET", "High", f"Client-side code exposes a credential-like value ({match.group(1)})",
                       f"{match.group(1)} = '{_mask(match.group(2))}'",
                       "Never ship secrets to the browser; use a backend or token exchange.", "OWASP A02:2021 Cryptographic Failures")
        for endpoint in re.findall(r"""["'](http://[^"'\s]+)["']""", script):
            report.add("SRC-INTERNAL-HTTP", "Medium", "Client-side code references a plain-HTTP endpoint", endpoint,
                       "Use HTTPS and avoid exposing internal hostnames.", "OWASP A02:2021 Cryptographic Failures")
        if re.search(r"(?i)\bdebug\s*[:=]\s*true", script):
            report.add("SRC-DEBUG", "Low", "Debug mode enabled in client configuration", "debug: true",
                       "Disable debug flags in production builds.", "OWASP A05:2021 Security Misconfiguration")

    for form in parser.forms:
        action = urljoin(page_url, form["action"] or page_url)
        has_password = any(i["type"] == "password" for i in form["inputs"])
        has_csrf = any(re.search(r"(?i)csrf|xsrf|token|__requestverification", i["name"]) for i in form["inputs"] if i["type"] == "hidden")
        label = form["id"] or form["action"] or "(form)"
        if has_password and form["method"] == "get":
            report.add("FORM-GET-PASSWORD", "High", f"Form '{label}' sends a password with GET", f"method=GET action={action}",
                       "Use POST so credentials never appear in URLs, logs or history.", "OWASP A04:2021 Insecure Design")
        if urlparse(action).scheme == "http":
            report.add("FORM-HTTP-ACTION", "Medium", f"Form '{label}' submits over plain HTTP", action,
                       "Submit forms over HTTPS only.", "OWASP A02:2021 Cryptographic Failures")
        if urlparse(action).hostname and urlparse(action).hostname != page.hostname:
            report.add("FORM-THIRD-PARTY", "Info", f"Form '{label}' posts to another host", action,
                       "Confirm the third party is trusted and uses HTTPS.", "OWASP A05:2021 Security Misconfiguration")
        if has_password and not has_csrf:
            report.add("FORM-CSRF", "Medium", f"Form '{label}' has no anti-CSRF token", "No hidden csrf/xsrf/token field found",
                       "Add a per-session anti-CSRF token and SameSite cookies.", "OWASP A01:2021 Broken Access Control")
        for field_ in form["inputs"]:
            if field_["type"] == "password" and field_["autocomplete"] not in ("current-password", "new-password", "off"):
                report.add("FORM-AUTOCOMPLETE", "Low", f"Password field '{field_['name']}' allows generic autocomplete",
                           f"autocomplete='{field_['autocomplete'] or 'unset'}'",
                           "Use autocomplete='current-password' or 'new-password'.", "OWASP ASVS V3")

    if page.scheme == "https":
        for tag, src in parser.resources:
            if src.startswith("http://"):
                report.add("SRC-MIXED", "Medium", f"Mixed content: <{tag}> loaded over HTTP", src,
                           "Load every sub-resource over HTTPS.", "OWASP A02:2021 Cryptographic Failures")

    banners = set()
    if parser.meta_generator:
        banners.add(f"generator: {parser.meta_generator}")
    for text in parser.comments + [src for _, src in parser.resources]:
        for lib, version in VERSION_BANNER.findall(text):
            banners.add(f"{lib} {version}")
    if banners:
        report.add("SRC-VERSIONS", "Low", "Software or library versions disclosed in page source", "; ".join(sorted(banners)),
                   "Remove version banners and keep client libraries up to date.", "OWASP A06:2021 Vulnerable and Outdated Components")

    report.data["forms"] = parser.forms
    report.data["external_resources"] = sorted({src for _, src in parser.resources if urlparse(urljoin(page_url, src)).hostname not in (page.hostname, None)})
    return parser
