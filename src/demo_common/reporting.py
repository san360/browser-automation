"""Run recording: console streaming, events.jsonl, Markdown report and result.json for every run."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import pricing
from .scenarios import AnswerKeyScore, CheckResult, RenderedScenario
from .settings import RUNS_DIR

_LIVE_VIEW = re.compile(r"https://[^\s)\]\"'<>]*(?:liveview|live-view|live\.playwright|#lv=)[^\s)\]\"'<>]*", re.IGNORECASE)
# Signed Playwright links (live view, recordings) grant access to the browser session; never persist them.
_SIGNED_LINK = re.compile(r"https://[^\s)\]\"'<>]*(?:liveview|live-view|#lv=|playwright\.microsoft\.com)[^\s)\]\"'<>]*",
                          re.IGNORECASE)
REDACTED_LINK = "<live-view-link-redacted>"
_EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9_](?:[A-Z0-9.!#$%&'*+/=?^_`{|}~-]*[A-Z0-9_])?"
                    r"@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}(?![\w-])",
                    re.IGNORECASE)
REDACTED_EMAIL = "<email-redacted>"
CONTENT_FILTER_HINT = (
    "Blocked by Azure AI Content Safety. If 'jailbreak' was detected, Prompt Shields read the task wording as an attempt "
    "to bypass safety rules (e.g. 'relax/ignore the filter'). Rephrase the task neutrally; page text that reaches the "
    "model through tool results is screened as well."
)
ICONS = {
    "info": "ℹ️ ", "action": "🧭", "tool": "🛠️ ", "message": "💬", "usage": "📊", "screenshot": "📸",
    "warning": "⚠️ ", "error": "❌", "live_view": "🔴", "check": "✅", "safety": "🛡️ ",
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    requests: int = 0

    def add(self, usage: Any) -> None:
        if usage is None:
            return
        get = usage.get if isinstance(usage, dict) else lambda k, d=None: getattr(usage, k, d)
        self.input_tokens += int(get("input_tokens", 0) or 0)
        self.output_tokens += int(get("output_tokens", 0) or 0)
        details = get("input_tokens_details", None)
        if details is not None:
            cached = details.get("cached_tokens", 0) if isinstance(details, dict) else getattr(details, "cached_tokens", 0)
            self.cached_tokens += int(cached or 0)
        self.requests += 1


@dataclass
class RunResult:
    scenario_id: str
    title: str
    mode: str
    model: str
    status: str
    duration_s: float
    input_tokens: int
    output_tokens: int
    tool_calls: int
    checks_passed: int
    checks_total: int
    answer_key_recall: float | None
    est_cost: float | None
    est_browser_minutes: int
    currency: str
    run_dir: str
    final_text: str = field(repr=False, default="")
    error: str | None = None
    cached_tokens: int = 0
    browser_session_ids: list[str] = field(default_factory=list)


class RunRecorder:
    """Collects everything that happens in a run and writes artifacts to runs/<timestamp>-<scenario>-<mode>/."""

    def __init__(self, rendered: RenderedScenario, mode: str, model: str, *, console: Console | None = None,
                 listeners: list[Callable[[dict], None]] | None = None, quiet: bool = False,
                 runs_dir: Path = RUNS_DIR) -> None:
        self.rendered = rendered
        self.mode = mode
        self.model = model
        self.console = console or Console()
        self.listeners = listeners or []
        self.quiet = quiet
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = runs_dir / f"{stamp}-{rendered.scenario.id}-{mode}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.started = time.monotonic()
        self.usage = Usage()
        self.tool_calls = 0
        self.actions: list[dict] = []
        self.live_view_url: str | None = None
        self.screenshots: list[str] = []
        self.response_ids: list[str] = []
        self.browser_session_ids: list[str] = []
        self.browser_seconds = 0.0
        (self.dir / "task.md").write_text(
            redact(f"# {rendered.scenario.title}\n\nStart URL: {rendered.url}\n\n{rendered.task}\n"), encoding="utf-8")

    # ----------------------------------------------------------------- events

    def emit(self, kind: str, message: str = "", **data: Any) -> None:
        event = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "kind": kind, "message": message, **data}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(redact(json.dumps(event, default=str, ensure_ascii=False)) + "\n")
        # Listeners (the console UI) and the presenter's terminal get the unredacted event so the live view can be opened.
        for listener in self.listeners:
            try:
                listener(event)
            except Exception:  # listeners (UI) must never break a run
                pass
        if not self.quiet and kind != "text_delta":
            self.console.print(Text.assemble(f"{ICONS.get(kind, '•')} ", (kind, "bold"), " ", message))

    def text_delta(self, delta: str) -> None:
        for listener in self.listeners:
            try:
                listener({"kind": "text_delta", "message": delta})
            except Exception:
                pass

    def action(self, name: str, arguments: dict | None = None, **extra: Any) -> None:
        self.tool_calls += 1
        args = dict(arguments or {})
        self.browser_session(args.get("browserSessionId"))
        self.actions.append({"name": name, "arguments": args, **extra})
        summary = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
        self.emit("action", f"{name}({summary})", name=name, arguments=args, **extra)

    def browser_session(self, session_id: Any) -> None:
        """Record each browser once, including sessions created during recovery."""
        if not isinstance(session_id, str) or not session_id or session_id in self.browser_session_ids:
            return
        self.browser_session_ids.append(session_id)
        self.emit("browser_session", f"Browser session: {session_id}", browserSessionId=session_id)

    def detect_browser_session(self, output: Any, *, depth: int = 0) -> None:
        """Read session creation results, including MCP text-content envelopes."""
        if depth > 8:
            return
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                return
        if isinstance(output, dict):
            self.browser_session(output.get("browserSessionId"))
            for key in ("content", "text", "structuredContent", "result"):
                if key in output:
                    self.detect_browser_session(output[key], depth=depth + 1)
        elif isinstance(output, list):
            for item in output:
                self.detect_browser_session(item, depth=depth + 1)

    def detect_live_view(self, text: str) -> None:
        match = _LIVE_VIEW.search(text or "")
        if match and not self.live_view_url:
            self.live_view_url = match.group(0)
            self.emit("live_view", f"Watch the cloud browser live: {self.live_view_url} (not saved to run artifacts)",
                      url=self.live_view_url)

    def add_usage(self, usage: Any) -> None:
        self.usage.add(usage)

    def note_content_filter(self, text: Any) -> None:
        """Explain content-filter blocks, which otherwise look like an unexplained refusal."""
        if "content_filter" in str(text or ""):
            self.emit("warning", CONTENT_FILTER_HINT)

    def screenshot(self, png: bytes, label: str) -> Path:
        path = self.dir / f"step-{len(self.screenshots) + 1:03d}.png"
        path.write_bytes(png)
        self.screenshots.append(path.name)
        self.emit("screenshot", f"{label} -> {path.name}", file=path.name)
        return path

    # ----------------------------------------------------------------- finish

    def finish(self, final_text: str, checks: list[CheckResult], score: AnswerKeyScore | None, *,
               status: str = "completed", error: str | None = None, sku: str = "GlobalStandard",
               browser_seconds: float | None = None) -> RunResult:
        duration = time.monotonic() - self.started
        seconds = self.browser_seconds if browser_seconds is None else browser_seconds
        cost = pricing.estimate(self.model, self.usage.input_tokens, self.usage.output_tokens, browser_seconds=seconds,
                                sku=sku, cached_tokens=self.usage.cached_tokens)
        clean_text = redact(final_text or "")
        result = RunResult(
            scenario_id=self.rendered.scenario.id, title=self.rendered.scenario.title, mode=self.mode, model=self.model,
            status=status, duration_s=round(duration, 1), input_tokens=self.usage.input_tokens,
            output_tokens=self.usage.output_tokens, tool_calls=self.tool_calls,
            checks_passed=sum(c.passed for c in checks), checks_total=len(checks),
            answer_key_recall=round(score.recall, 2) if score else None, est_cost=cost.total,
            est_browser_minutes=cost.browser_minutes, currency=cost.currency, run_dir=str(self.dir),
            final_text=clean_text, error=redact(error) if error else None, cached_tokens=self.usage.cached_tokens,
            browser_session_ids=list(self.browser_session_ids),
        )
        (self.dir / "result.json").write_text(
            redact(json.dumps(asdict(result), indent=2, ensure_ascii=False)), encoding="utf-8")
        (self.dir / "report.md").write_text(redact(self._report(result, checks, score, cost)), encoding="utf-8")
        if not self.quiet:
            self._print_summary(result, checks, score, cost)
        return result

    def _report(self, result: RunResult, checks: list[CheckResult], score: AnswerKeyScore | None, cost) -> str:
        lines = [
            f"# {result.title}", "",
            f"- Scenario: `{result.scenario_id}`  |  Mode: **{result.mode}**  |  Model: `{result.model}`",
            f"- Status: **{result.status}**  |  Duration: {result.duration_s}s  |  Tool calls: {result.tool_calls}",
            f"- Tokens: {result.input_tokens} in ({result.cached_tokens} cached) / {result.output_tokens} out ({self.usage.requests} responses)",
            f"- Estimated cost: {cost.describe()}",
            f"- Start URL: {self.rendered.url}", "",
            *([f"- Browser session ID: `{session_id}`" for session_id in result.browser_session_ids]),
            "", "## Task", "", self.rendered.task, "",
            "## Agent answer", "", result.final_text or "_(no answer)_", "",
        ]
        if checks:
            lines += ["## Automatic checks", "", "| Check | Result | Detail |", "|---|---|---|"]
            lines += [f"| {c.name} | {'PASS' if c.passed else 'FAIL'} | {c.detail} |" for c in checks]
            lines.append("")
        if score:
            lines += [f"## Answer-key recall (heuristic): {len(score.found)}/{score.total}", "",
                      "| ID | Issue | Reported |", "|---|---|---|"]
            lines += [f"| {i} | {score.titles[i]} | {'yes' if i in score.found else 'no'} |" for i in score.titles]
            lines.append("")
        if self.actions:
            lines += ["## Actions", ""]
            lines += [f"{n}. `{a['name']}` {redact(json.dumps(a['arguments'], ensure_ascii=False))[:300]}"
                      for n, a in enumerate(self.actions, 1)]
            lines.append("")
        if self.screenshots:
            lines += ["## Screenshots", ""] + [f"![{s}]({s})" for s in self.screenshots] + [""]
        if result.error:
            lines += ["## Error", "", f"```\n{redact(result.error)}\n```", ""]
        return "\n".join(lines)

    def _print_summary(self, result: RunResult, checks: list[CheckResult], score: AnswerKeyScore | None, cost) -> None:
        table = Table(title=f"{result.scenario_id} · {result.mode} · {result.model}", show_header=False)
        table.add_row("Status", result.status)
        table.add_row("Duration", f"{result.duration_s}s")
        table.add_row("Tool calls", str(result.tool_calls))
        if result.browser_session_ids:
            table.add_row("Browser session IDs", "\n".join(result.browser_session_ids))
        table.add_row("Tokens (in/cached/out)", f"{result.input_tokens} / {result.cached_tokens} / {result.output_tokens}")
        table.add_row("Estimated cost", cost.describe())
        if checks:
            table.add_row("Checks", f"{result.checks_passed}/{result.checks_total} passed")
            for c in checks:
                table.add_row("", f"{'PASS' if c.passed else 'FAIL'} {c.name} {c.detail}")
        if score:
            table.add_row("Answer key", f"{len(score.found)}/{score.total} known issues reported (heuristic)")
        table.add_row("Artifacts", result.run_dir)
        self.console.print(table)


def redact(text: str) -> str:
    """Remove signed Playwright links and email addresses before persisting text."""
    return _EMAIL.sub(REDACTED_EMAIL, _SIGNED_LINK.sub(REDACTED_LINK, text or ""))


def _short(value: Any, limit: int = 80) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_results(runs_dir: Path = RUNS_DIR) -> list[dict]:
    results = []
    for path in sorted(runs_dir.glob("*/result.json")):
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return results
