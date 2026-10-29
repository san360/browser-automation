"""A fake runner for the web console tests: real RunRecorder artifacts and events, no Azure calls."""

from __future__ import annotations

import base64
import os
import threading
import time
from pathlib import Path

from demo_common.reporting import RunRecorder
from demo_common.scenarios import CheckResult

# A small mock browser page, as PNG (Computer Use screenshots) and JPEG (local-browser preview frames).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAKAAAABkCAIAAACO1KzYAAABQ0lEQVR4nO3bsQ1BYRSA0UesYAARpVVsoDGYIayiFAOIWhQaK2iex5dz6pe8m3y53f1nq/1toGs+9QCMS+A4geMEjhM4TuA4geMEjhM4TuA4geMEjhM4TuA4geMEjps9nq+pZ2BENjhO4DiB4wSOEzhO4DiB4wSOEzhO4DiB4wSOW3zy0flyH3+Svu1m+f2f2uA4geMEjhM4TuA4geMEjhM4TuA4gePcRcfZ4DiB4wSOEzhO4DiB4wSOEzjOTdZPXE6NxwbHCRwncJzAcQLHCRwncJzAcS464mxwnMBxAscJHCdwnMBxAscJHCdwnMBxAscJHPfRVeX6dBx+zHV3mHqE/2CD4wSOEzhO4DiB4wSOEzhO4DiB4wSOEzhO4DiB4wSO8zYpzgbHCRwncJzAcQLHCRwncJzAcQLHCRwncJzAQ9sbtkkWzV0tRtEAAAAASUVORK5CYII=")
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9"
    "Pjv/2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCABkAKADASIAAhEB"
    "AxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAk"
    "M2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5"
    "usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQA"
    "AQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3"
    "eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDB"
    "ooor9APngooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigD27+wNG/6BFj/wCAyf4Uf2Bo3/QIsf8AwGT/AAq/Ucs8cOPMbbnpwa+F9rU/mZ73"
    "LHsVP7A0b/oEWP8A4DJ/hR/YGjf9Aix/8Bk/wqx9utv+en/jpo+3W3/PT/x00/aVe7Dlj2K/9gaN/wBAix/8Bk/wo/sDRv8AoEWP/gMn+FWPt1t/z0/8dNH2"
    "62/56f8Ajpo9pV7sOWPYr/2Bo3/QIsf/AAGT/Cj+wNG/6BFj/wCAyf4VY+3W3/PT/wAdNH262/56f+Omj2lXuw5Y9iv/AGBo3/QIsf8AwGT/AAo/sDRv+gRY"
    "/wDgMn+FWPt1t/z0/wDHTR9utv8Anp/46aPaVe7Dlj2K/wDYGjf9Aix/8Bk/wo/sDRv+gRY/+Ayf4VY+3W3/AD0/8dNH262/56f+Omj2lXuw5Y9iv/YGjf8A"
    "QIsf/AZP8KP7A0b/AKBFj/4DJ/hVj7dbf89P/HTR9utv+en/AI6aPaVe7Dlj2K/9gaN/0CLH/wABk/wo/sDRv+gRY/8AgMn+FWPt1t/z0/8AHTUysGUMpyCM"
    "il7Sp3YcsexR/sDRv+gRY/8AgMn+FH9gaN/0CLH/AMBk/wAKv0Ue1qfzP7w5I9ih/YGjf9Aix/8AAZP8KP7A0b/oEWP/AIDJ/hV+ij2tT+Z/eHJHsFUNU/5Z"
    "fj/Sr9NaNHxvRWx0yM1Cdncp6mHRW19nh/54p/3yKPs8P/PFP++RV85HKYtFbX2eH/nin/fIo+zw/wDPFP8AvkUc4cpi0VtfZ4f+eKf98ij7PD/zxT/vkUc4"
    "cpi0VtfZ4f8Anin/AHyKPs8P/PFP++RRzhymLRW19nh/54p/3yKPs8P/ADxT/vkUc4cpi0VtfZ4f+eKf98ij7PD/AM8U/wC+RRzhymLW1b/8e8f+4P5UfZ4f"
    "+eKf98ipAAAABgDoBUylcpKwUUUVIwooooAKqX88kPl+W23Oc8D2q3UU9slxt3lhtzjFNWvqDM37dc/89P8Ax0Ufbrn/AJ6f+Oirn9mw/wB5/wAx/hR/ZsP9"
    "5/zH+FXeJFmU/t1z/wA9P/HRR9uuf+en/joq5/ZsP95/zH+FH9mw/wB5/wAx/hReIWZT+3XP/PT/AMdFH265/wCen/joq5/ZsP8Aef8AMf4Uf2bD/ef8x/hR"
    "eIWZT+3XP/PT/wAdFH265/56f+Oirn9mw/3n/Mf4Uf2bD/ef8x/hReIWZT+3XP8Az0/8dFX7GV5oS0jZIbHT6Uz+zYf7z/mP8KnggW3QohJBOeaUmraDSZJR"
    "RRUFBRRRQAUUUUAFFFFABRRXHfED/mH/APbT/wBlpxV3YwxFb2NJ1LXsdjRXjtFaey8zyv7X/ufj/wAA9iorx2ij2XmH9r/3Px/4B7FRXjtdL4E/5Dc3/Xs3"
    "/oS0nTsr3NaOZ+1qKHJa/n/wDvaKKKzPXCiiigAooooAKKKKACiiigAooooAK5TxxZ3V39h+zW00+3zN3loWxnbjOK6uimnZ3Ma9FVqbpt7nlP8AY+qf9A27"
    "/wC/Df4Uf2Pqn/QNu/8Avw3+FerUVp7Rnm/2TD+ZnlP9j6p/0Dbv/vw3+FH9j6p/0Dbv/vw3+FerUUe0Yf2TD+ZnlP8AY+qf9A27/wC/Df4V0HguwvbXV5Xu"
    "LSeFDbkBpIyoJ3LxzXbUUnUbVjSllsKU1NS2Ciiisz1AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACi"
    "iigD/9k=")
LIVE_URL = "https://live.playwright.microsoft.com/#lv=unit-test-signed-token"
ANSWER = ("Article: **Water damage: what's covered**\n\n- Home Plus and Home Premium cover burst pipes\n"
          "- Report within 14 days\n\nSee https://example.com/articles/water-damage for details.")


def mirror_frame(title: str = "Contoso Insurance", url: str = "https://demo.contoso.example/") -> None:
    """Write a preview frame where the console's LocalMirror init-page script would (only during local runs)."""
    script = os.environ.get("LOCAL_BROWSER_INIT_PAGE")
    if not script:
        return
    folder = Path(script).parent
    (folder / "meta.json").write_text(f'{{"url": "{url}", "title": "{title}"}}', encoding="utf-8")
    (folder / "frame.jpg").write_bytes(JPEG)


class FakeRunner:
    """Callable with the signature of web_console.runners.run_mode."""

    def __init__(self, runs_dir: Path, *, delay: float = 0.0, gate: threading.Event | None = None) -> None:
        self.runs_dir = runs_dir
        self.delay = delay
        self.gate = gate
        self.calls: list[dict] = []

    def __call__(self, mode, rendered, settings, *, model, options, listeners):
        self.calls.append({"mode": mode, "model": model, "options": options, "url": rendered.url,
                           "site": settings.demo_site_url, "env_site": os.environ.get("DEMO_SITE_URL")})
        recorder = RunRecorder(rendered, mode, model, listeners=listeners, quiet=True, runs_dir=self.runs_dir)
        pause = lambda: time.sleep(self.delay * 4)  # noqa: E731
        recorder.emit("info", f"Fake {mode} run for {rendered.scenario.id}")
        session_args = {}
        if mode in ("prompt", "hosted") or (mode == "local" and options.remote_browser):
            recorder.action("browserautomation___create_browser_session", {})
            pause()
            session_args = {"browserSessionId": f"test-browser-{mode}"}
            recorder.detect_browser_session(session_args)
            recorder.detect_live_view(f"Session created. liveViewUrl: {LIVE_URL}-{mode}")
        recorder.action("browser_navigate", {"url": rendered.url, **session_args})
        pause()
        if mode == "cua":
            recorder.screenshot(PNG, f"start {rendered.url}")
        if mode == "local":
            mirror_frame()
        if self.gate is not None:
            self.gate.wait(timeout=15)
        recorder.action("browser_type", {"target": "e24", "text": "water damage", **session_args})
        pause()
        if mode == "cua":
            recorder.screenshot(PNG, f"step 1 {rendered.url}")
        for chunk in (ANSWER[:40], ANSWER[40:90], ANSWER[90:]):
            recorder.text_delta(chunk)
            time.sleep(self.delay)
        recorder.emit("message", ANSWER.splitlines()[0][:160], chars=len(ANSWER))
        checks = [CheckResult("contains '14 days'", True), CheckResult("contains 'Home Premium'", True)]
        return recorder.finish(ANSWER, checks, None, browser_seconds=42.0)
