"""Screenshots of the local agent's browser (Playwright MCP on this PC) for the console's preview pane.

Playwright MCP runs an "init page" script for every page it opens (--init-page). The script below takes a JPEG of the
page about once a second, only keeps frames that changed, and writes them to a scratch folder that the console polls.
It runs inside the MCP server, never touches the page's DOM and never changes what the agent's tools return, so the
agent's prompts, tokens and behaviour are the same with or without it. The hosted agent passes the script to
Playwright MCP when LOCAL_BROWSER_INIT_PAGE is set (src/hosted_agent/browser_backend.py).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

ENV_VAR = "LOCAL_BROWSER_INIT_PAGE"
SCRIPT = r"""'use strict';
// Written by the web console for one local run; deleted when the run ends. It must never throw.
const fs = require('fs');
const path = require('path');
const DIR = __DIR__;

async function capture(page, state) {
  if (state.busy || page.isClosed()) return;
  state.busy = true;
  try {
    const shot = await page.screenshot({ type: 'jpeg', quality: 60, scale: 'css', caret: 'initial', timeout: 3000 });
    if (state.last && shot.equals(state.last)) return;
    state.last = shot;
    const title = await page.title().catch(() => '');
    fs.writeFileSync(path.join(DIR, 'meta.tmp'), JSON.stringify({ url: page.url(), title, ts: Date.now() }));
    fs.renameSync(path.join(DIR, 'meta.tmp'), path.join(DIR, 'meta.json'));
    fs.writeFileSync(path.join(DIR, 'frame.tmp'), shot);
    fs.renameSync(path.join(DIR, 'frame.tmp'), path.join(DIR, 'frame.jpg'));
  } catch (error) {
    // Navigating, closed, or waiting on a dialog: try again on the next tick.
  } finally {
    state.busy = false;
  }
}

exports.default = async function mirror({ page }) {
  try {
    const state = { busy: false, last: null };
    const timer = setInterval(() => capture(page, state), 1000);
    if (timer.unref) timer.unref();
    page.on('close', () => clearInterval(timer));
    page.on('load', () => setTimeout(() => capture(page, state), 150));
  } catch (error) {
    // Never break the agent's browser.
  }
};
"""


class LocalMirror:
    """Context manager around one local run: exports the init-page script and reports new frames to `on_frame`."""

    def __init__(self, on_frame: Callable[[bytes, dict], None], *, interval: float = 0.4) -> None:
        self.on_frame = on_frame
        self.interval = interval
        self.dir: Path | None = None
        self._stamp: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._previous: str | None = None

    def __enter__(self) -> "LocalMirror":
        self.dir = Path(tempfile.mkdtemp(prefix="web-console-mirror-"))
        script = self.dir / "mirror.cjs"
        script.write_text(SCRIPT.replace("__DIR__", json.dumps(str(self.dir))), encoding="utf-8")
        self._previous = os.environ.get(ENV_VAR)
        os.environ[ENV_VAR] = str(script)  # inherited by the local agent's process (server_env copies os.environ)
        self._thread = threading.Thread(target=self._watch, name="local-mirror", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.poll()
        if self._previous is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._previous
        if self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)

    def _watch(self) -> None:
        while not self._stop.wait(self.interval):
            self.poll()

    def poll(self) -> None:
        if not self.dir:
            return
        frame = self.dir / "frame.jpg"
        try:
            stamp = frame.stat().st_mtime_ns
            if stamp == self._stamp:
                return
            data = frame.read_bytes()
            meta = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not data.startswith(b"\xff\xd8"):
            return
        self._stamp = stamp
        try:
            self.on_frame(data, meta if isinstance(meta, dict) else {})
        except Exception:  # the preview must never break a run
            pass
