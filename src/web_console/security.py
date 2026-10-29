"""Request guard for a console that drives real Azure resources from the presenter's machine.

The console binds to loopback, but any web page the presenter opens can still send requests to 127.0.0.1. So:

* Host must be the console's own loopback host:port (defeats DNS rebinding).
* Origin, when sent, must be the console's own origin; state-changing requests must send it and must be JSON.
* Sec-Fetch-Site must be same-origin (or absent), except for top-level navigations to "/".
* Every /api/* call except bootstrap and health carries a per-process random token (X-Console-Token), which only a
  same-origin page can read from /api/bootstrap.

Implemented as plain ASGI middleware so Server-Sent Event streams are never buffered.
"""

from __future__ import annotations

import json
import re
import secrets

from starlette.datastructures import Headers, MutableHeaders

TOKEN_HEADER = "x-console-token"
OPEN_PATHS = {"/api/bootstrap", "/api/health"}
# Images (<img src>) cannot send the token header: screenshots and preview frames rely on the Host, Sec-Fetch-Site
# and Cross-Origin-Resource-Policy checks instead, which already stop other sites from reading them.
MEDIA_PATHS = re.compile(r"^/api/(?:history/[^/]+/files/[^/]+|jobs/[^/]+/frames/\d+)$")
MAX_BODY_BYTES = 64 * 1024
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; "
    "font-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # Keep a handle on the live-view window the console opens ("same-origin" would sever it on navigation).
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


def new_token() -> str:
    return secrets.token_urlsafe(32)


def loopback_hosts(port: int, bind_host: str = "127.0.0.1") -> set[str]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    if bind_host not in ("0.0.0.0", "::", ""):
        hosts.add(f"{bind_host}:{port}".lower())
    return hosts


class ConsoleGuard:
    def __init__(self, app, *, token: str, hosts: set[str]) -> None:
        self.app = app
        self.token = token
        self.hosts = {h.lower() for h in hosts}
        self.origins = {f"http://{h}" for h in self.hosts}

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        problem = self._problem(scope, Headers(scope=scope))
        if problem:
            await _reject(send, *problem)
            return
        path = scope.get("path", "")

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in SECURITY_HEADERS.items():
                    if key not in headers:
                        headers[key] = value
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-cache" if path.startswith("/static/") else "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _problem(self, scope, headers: Headers) -> tuple[int, str] | None:
        method, path = scope["method"], scope.get("path", "")
        if headers.get("host", "").lower() not in self.hosts:
            return 421, "This console only answers on its loopback address."
        origin = headers.get("origin")
        if origin is not None and origin.lower() not in self.origins:
            return 403, "Cross-origin requests are not allowed."
        site = headers.get("sec-fetch-site")
        navigation = method == "GET" and path == "/" and headers.get("sec-fetch-mode") == "navigate"
        if site not in (None, "same-origin", "none") and not navigation:
            return 403, "Cross-site requests are not allowed."
        if path.startswith("/api/") and path not in OPEN_PATHS:
            media = method in ("GET", "HEAD") and MEDIA_PATHS.fullmatch(path)
            if not media and not secrets.compare_digest(headers.get(TOKEN_HEADER, ""), self.token):
                return 403, "Missing or stale console token: reload the page."
        if method not in ("GET", "HEAD", "OPTIONS"):
            if origin is None:
                return 403, "A same-origin request is required."
            if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return 415, "JSON body required."
            length = headers.get("content-length") or "0"
            if not length.isdigit() or int(length) > MAX_BODY_BYTES:
                return 413, "Request too large."
        return None


async def _reject(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
               (b"cache-control", b"no-store")]
    headers += [(k.lower().encode(), v.encode()) for k, v in SECURITY_HEADERS.items()]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
