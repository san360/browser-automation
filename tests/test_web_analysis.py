"""Tests for the hosted agent's deterministic web analysis (no network)."""

import socket

import httpx
import pytest

import web_analysis as wa

INSECURE_HTML = """
<html><head><meta name="generator" content="ContosoCMS 2.1.0"><!-- jQuery v1.12.4 -->
<script>window.APP_CONFIG = { apiKey: "DEMO-NOT-A-REAL-KEY-0000", apiBase: "http://internal-api.local/v1", debug: true };</script>
</head><body>
<!-- TODO remove before go-live: admin / admin -->
<form id="login" method="get" action="/login"><input name="username"><input type="password" name="password" autocomplete="on"></form>
<form id="news" method="post" action="http://news.invalid/subscribe"><input name="email"></form>
<img src="http://assets.invalid/banner.png">
</body></html>
"""


def _response(headers, url="https://demo.contoso.example/security-lab/"):
    return httpx.Response(200, headers=headers, request=httpx.Request("GET", url))


def test_header_findings_for_insecure_page():
    report = wa.Report(url="x")
    wa.analyse_headers(report, _response([
        ("Server", "Apache/2.2.15 (CentOS)"), ("X-Powered-By", "PHP/5.4.16"),
        ("Access-Control-Allow-Origin", "*"), ("Access-Control-Allow-Credentials", "true"),
        ("Set-Cookie", "sessionid=abc; Path=/"),
    ]))
    ids = {f.id for f in report.findings}
    assert {"HDR-CSP", "HDR-CLICKJACK", "HDR-CORS", "HDR-DISCLOSE-X-POWERED-BY", "CK-HTTPONLY-sessionid", "CK-SECURE-sessionid"} <= ids


def test_hardened_headers_produce_no_header_findings():
    report = wa.Report(url="x")
    wa.analyse_headers(report, _response([
        ("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'"),
        ("Strict-Transport-Security", "max-age=31536000"), ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"), ("Referrer-Policy", "strict-origin"), ("Permissions-Policy", "camera=()"),
        ("Server", "contoso-web"), ("Set-Cookie", "sid=1; Secure; HttpOnly; SameSite=Lax"),
    ]))
    assert report.findings == []


def test_source_findings():
    report = wa.Report(url="x")
    wa.analyse_source(report, "https://demo.contoso.example/security-lab/", INSECURE_HTML)
    ids = {f.id for f in report.findings}
    assert {"SRC-COMMENT", "SRC-SECRET", "SRC-INTERNAL-HTTP", "FORM-GET-PASSWORD", "FORM-CSRF",
            "FORM-HTTP-ACTION", "SRC-MIXED", "SRC-VERSIONS"} <= ids
    secret = next(f for f in report.findings if f.id == "SRC-SECRET")
    assert "DEMO-NOT-A-REAL-KEY-0000" not in secret.evidence  # secrets are masked


def test_allow_list_blocks_other_hosts(monkeypatch):
    monkeypatch.setenv("ALLOWED_SCAN_HOSTS", "demo.contoso.example")
    with pytest.raises(wa.ScanNotAllowed):
        wa.validate_target("https://www.bing.com/")


def test_ssrf_guard_blocks_private_addresses(monkeypatch):
    monkeypatch.setenv("ALLOWED_SCAN_HOSTS", "demo.contoso.example,metadata.internal")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("169.254.169.254", 80))])
    with pytest.raises(wa.ScanNotAllowed, match="non-public"):
        wa.validate_target("http://metadata.internal/latest")


def test_public_allow_listed_host_passes(monkeypatch):
    monkeypatch.setenv("ALLOWED_SCAN_HOSTS", "*.contoso.example")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("20.50.2.1", 443))])
    assert wa.validate_target("https://demo.contoso.example/x") == "https://demo.contoso.example/x"
