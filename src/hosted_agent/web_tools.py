"""Agent Framework tool wrappers around web_analysis (HTTP headers, page source, links).

See web_analysis.py for the allow-list and SSRF protections that every tool enforces.
"""

from __future__ import annotations

import json
import re
from typing import Annotated
from urllib.parse import urljoin, urlparse

import httpx
from agent_framework import tool
from pydantic import Field

from web_analysis import (
    Report,
    ScanNotAllowed,
    _PageParser,
    _client,
    _fetch,
    allowed_hosts,
    analyse_headers,
    analyse_source,
    validate_target,
)

__all__ = ["WEB_TOOLS", "allowed_hosts", "check_links", "inspect_http_security", "scan_page_source"]


# --------------------------------------------------------------------------- agent tools


@tool(approval_mode="never_require")
async def inspect_http_security(
    url: Annotated[str, Field(description="Absolute URL of a page on an allow-listed host, e.g. https://site/security-lab/")],
) -> str:
    """Passively inspect HTTP response headers, cookies, CORS, security.txt and robots.txt of a page you are authorised to test. Returns JSON findings with severity, evidence and OWASP mapping."""
    try:
        target = validate_target(url)
    except ScanNotAllowed as exc:
        return json.dumps({"error": str(exc)})
    report = Report(url=target)
    async with _client() as client:
        try:
            response = await _fetch(client, target)
        except (httpx.HTTPError, ScanNotAllowed) as exc:
            return json.dumps({"error": f"Request failed: {exc}"})
        report.final_url, report.status = str(response.url), response.status_code
        analyse_headers(report, response)
        base = f"{response.url.scheme}://{response.url.host}"
        try:
            sec = await _fetch(client, base + "/.well-known/security.txt")
            report.data["security_txt"] = sec.status_code == 200
            if sec.status_code != 200:
                report.add("META-SECURITYTXT", "Info", "No /.well-known/security.txt", f"HTTP {sec.status_code}",
                           "Publish a security.txt with a contact for vulnerability reports.", "RFC 9116")
            robots = await _fetch(client, base + "/robots.txt")
            if robots.status_code == 200:
                disallowed = re.findall(r"(?im)^\s*disallow:\s*(\S+)", robots.text)
                report.data["robots_disallow"] = disallowed
                sensitive = [p for p in disallowed if re.search(r"(?i)admin|backup|private|internal|old|config", p)]
                if sensitive:
                    report.add("META-ROBOTS", "Low", "robots.txt reveals sensitive-looking paths", ", ".join(sensitive),
                               "Do not rely on robots.txt to hide content; protect the paths instead.",
                               "OWASP A05:2021 Security Misconfiguration")
        except (httpx.HTTPError, ScanNotAllowed) as exc:
            report.notes.append(f"Auxiliary checks failed: {exc}")
    report.notes.append("Passive checks only. Findings are indicators to verify, not proof of exploitability.")
    return report.to_json()


@tool(approval_mode="never_require")
async def scan_page_source(
    url: Annotated[str, Field(description="Absolute URL of a page on an allow-listed host.")],
) -> str:
    """Download the raw HTML of a page and report source-level signals: sensitive HTML comments, credential-like values in inline scripts, insecure forms (GET passwords, HTTP actions, missing CSRF tokens, autocomplete), mixed content and disclosed library versions."""
    try:
        target = validate_target(url)
    except ScanNotAllowed as exc:
        return json.dumps({"error": str(exc)})
    report = Report(url=target)
    async with _client() as client:
        try:
            response = await _fetch(client, target)
        except (httpx.HTTPError, ScanNotAllowed) as exc:
            return json.dumps({"error": f"Request failed: {exc}"})
    report.final_url, report.status = str(response.url), response.status_code
    analyse_source(report, str(response.url), response.text)
    return report.to_json()


@tool(approval_mode="never_require")
async def check_links(
    url: Annotated[str, Field(description="Absolute URL of the page whose links, images, scripts and stylesheets should be checked.")],
    max_links: Annotated[int, Field(description="Maximum number of same-host URLs to check (1-40).", ge=1, le=40)] = 25,
) -> str:
    """Find broken links and missing resources (HTTP 4xx/5xx) on a page, limited to the same allow-listed host. Useful for UI bug troubleshooting (broken images, 404 links)."""
    try:
        target = validate_target(url)
    except ScanNotAllowed as exc:
        return json.dumps({"error": str(exc)})
    results: list[dict] = []
    async with _client() as client:
        try:
            response = await _fetch(client, target)
        except (httpx.HTTPError, ScanNotAllowed) as exc:
            return json.dumps({"error": f"Request failed: {exc}"})
        parser = _PageParser()
        parser.feed(response.text)
        host = response.url.host
        candidates: dict[str, str] = {}
        for tag, ref in parser.resources + parser.links:
            absolute = urljoin(str(response.url), ref).split("#", 1)[0]
            parsed = urlparse(absolute)
            if parsed.scheme in ("http", "https") and parsed.hostname == host and absolute not in candidates:
                candidates[absolute] = tag
        for link, tag in list(candidates.items())[:max_links]:
            try:
                r = await client.head(link)
                if r.status_code in (405, 501):
                    r = await client.get(link)
                results.append({"url": link, "element": tag, "status": r.status_code})
            except (httpx.HTTPError, ScanNotAllowed) as exc:
                results.append({"url": link, "element": tag, "status": None, "error": str(exc)})
    broken = [r for r in results if r["status"] is None or r["status"] >= 400]
    return json.dumps({"page": target, "checked": len(results), "broken": broken,
                       "ok": [r["url"] for r in results if r not in broken]}, indent=1)


WEB_TOOLS = [inspect_http_security, scan_page_source, check_links]
