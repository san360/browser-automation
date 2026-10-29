"""Browser environment for the Computer Use loop.

Computer Use is a *client-executed* tool: the model only proposes actions (click x/y, type, scroll, ...);
this module performs them in a real browser and returns screenshots. By default the browser runs locally
(Playwright Chromium). Optionally it can connect to a cloud browser in the Azure Playwright workspace
(`--remote-browser`), which requires the workspace to allow access tokens (playwrightLocalAuth=Enabled)
and PLAYWRIGHT_SERVICE_ACCESS_TOKEN to be set. That combination is not an officially documented
Computer Use pattern, so treat it as experimental.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

KEY_MAP = {
    "/": "Slash", "\\": "Backslash", "alt": "Alt", "option": "Alt", "arrowdown": "ArrowDown", "down": "ArrowDown",
    "arrowleft": "ArrowLeft", "left": "ArrowLeft", "arrowright": "ArrowRight", "right": "ArrowRight",
    "arrowup": "ArrowUp", "up": "ArrowUp", "backspace": "Backspace", "ctrl": "Control", "control": "Control",
    "cmd": "Meta", "command": "Meta", "meta": "Meta", "win": "Meta", "super": "Meta", "delete": "Delete",
    "enter": "Enter", "return": "Enter", "esc": "Escape", "escape": "Escape", "shift": "Shift", "space": " ",
    "tab": "Tab", "pagedown": "PageDown", "pageup": "PageUp", "home": "Home", "end": "End", "insert": "Insert",
}


def _get(action: Any, key: str, default: Any = None) -> Any:
    if isinstance(action, dict):
        return action.get(key, default)
    return getattr(action, key, default)


class BrowserEnvironment:
    def __init__(self, *, width: int = 1440, height: int = 900, headless: bool = True,
                 remote_endpoint: str | None = None, access_token: str | None = None,
                 api_version: str = "2025-09-01") -> None:
        self.width, self.height = width, height
        self.headless = headless
        self.remote_endpoint = remote_endpoint
        self.access_token = access_token
        self.api_version = api_version
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "BrowserEnvironment":
        self._pw = await async_playwright().start()
        if self.remote_endpoint:
            if not self.access_token:
                raise RuntimeError("Remote browser needs PLAYWRIGHT_SERVICE_ACCESS_TOKEN (workspace access token).")
            ws = f"{self.remote_endpoint}?os=linux&runId={uuid.uuid4()}&api-version={self.api_version}"
            self._browser = await self._pw.chromium.connect(
                ws, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=60_000
            )
        else:
            self._browser = await self._pw.chromium.launch(
                headless=self.headless, args=[f"--window-size={self.width},{self.height}", "--disable-extensions"]
            )
        self._context = await self._browser.new_context(viewport={"width": self.width, "height": self.height})
        self.page = await self._context.new_page()
        return self

    async def __aexit__(self, *exc) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        if self._pw:
            await self._pw.stop()

    @property
    def url(self) -> str:
        return self.page.url if self.page else ""

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or ""

    async def goto(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)

    async def screenshot(self) -> bytes:
        try:
            return await self.page.screenshot(full_page=False)
        except Exception:
            await asyncio.sleep(1)
            return await self.page.screenshot(full_page=False)

    def _xy(self, action: Any) -> tuple[int, int]:
        x = int(_get(action, "x", 0) or 0)
        y = int(_get(action, "y", 0) or 0)
        return max(0, min(x, self.width - 1)), max(0, min(y, self.height - 1))

    async def execute(self, action: Any) -> str:
        """Execute one model-proposed action. Returns a short description for the run log."""
        kind = _get(action, "type")
        page = self.page
        if kind == "click":
            button = _get(action, "button", "left") or "left"
            x, y = self._xy(action)
            if button == "back":
                await page.go_back()
            elif button == "forward":
                await page.go_forward()
            else:
                await page.mouse.click(x, y, button={"right": "right", "middle": "middle", "wheel": "middle"}.get(button, "left"))
            await self._settle()
            return f"click {button} at ({x},{y})"
        if kind == "double_click":
            x, y = self._xy(action)
            await page.mouse.dblclick(x, y)
            await self._settle()
            return f"double_click at ({x},{y})"
        if kind == "drag":
            path = _get(action, "path", []) or []
            if len(path) >= 2:
                start = path[0]
                await page.mouse.move(int(_get(start, "x", 0)), int(_get(start, "y", 0)))
                await page.mouse.down()
                for point in path[1:]:
                    await page.mouse.move(int(_get(point, "x", 0)), int(_get(point, "y", 0)))
                await page.mouse.up()
            return f"drag through {len(path)} points"
        if kind == "move":
            x, y = self._xy(action)
            await page.mouse.move(x, y)
            return f"move to ({x},{y})"
        if kind == "scroll":
            x, y = self._xy(action)
            dx, dy = int(_get(action, "scroll_x", 0) or 0), int(_get(action, "scroll_y", 0) or 0)
            await page.mouse.move(x, y)
            await page.mouse.wheel(dx, dy)
            await asyncio.sleep(0.4)
            return f"scroll ({dx},{dy}) at ({x},{y})"
        if kind == "keypress":
            keys = [KEY_MAP.get(str(k).lower(), str(k)) for k in (_get(action, "keys", []) or [])]
            if len(keys) > 1:
                await page.keyboard.press("+".join(keys))
            elif keys:
                await page.keyboard.press(keys[0])
            await self._settle()
            return f"keypress {'+'.join(keys)}"
        if kind == "type":
            text = _get(action, "text", "") or ""
            await page.keyboard.type(text, delay=15)
            return f"type {text[:40]!r}"
        if kind == "wait":
            ms = int(_get(action, "ms", 1000) or 1000)
            await asyncio.sleep(min(ms, 5000) / 1000)
            return f"wait {ms}ms"
        if kind == "screenshot":
            return "screenshot"
        return f"unsupported action {kind!r}"

    async def _settle(self) -> None:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except PlaywrightTimeout:
            pass
        await asyncio.sleep(0.6)
        pages = self._context.pages if self._context else []
        if len(pages) > 1 and pages[-1] is not self.page and pages[-1].url not in ("", "about:blank"):
            self.page = pages[-1]  # follow links that open a new tab
