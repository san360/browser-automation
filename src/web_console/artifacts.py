"""Run folders written by demo_common.reporting.RunRecorder: locating them, reading them and serving files safely.

Every runner writes runs/<YYYYMMDD-HHMMSS>-<scenario>-<mode>/ with events.jsonl, report.md and result.json (plus
step-NNN.png for Computer Use and local-agent.log for local mode). Runner events do not name their folder, so a live
run's folder is found by its first event: the recorder writes each event to events.jsonl before telling listeners.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

FOLDER = re.compile(r"^\d{8}-\d{6}-[A-Za-z0-9._-]{1,120}$")
FILES = {re.compile(r"^step-\d{3,4}\.png$"): "image/png", re.compile(r"^local-agent\.log$"): "text/plain; charset=utf-8"}
CHECK_ROW = re.compile(r"^\| (?P<name>.+) \| (?P<result>PASS|FAIL) \| (?P<detail>.*) \|$")
KEY_HEADING = re.compile(r"^## Answer-key recall \(heuristic\): (?P<found>\d+)/(?P<total>\d+)")
KEY_ROW = re.compile(r"^\| (?P<id>[^|]+) \| (?P<title>.+) \| (?P<hit>yes|no) \|$")
LINE = re.compile(r"^- (?P<key>Estimated cost|Tokens): (?P<value>.+)$")
MAX_TEXT = 400_000


def run_folders(runs_dir: Path) -> set[str]:
    try:
        return {p.name for p in runs_dir.iterdir() if p.is_dir()}
    except OSError:
        return set()


def first_event_ts(folder: Path) -> str | None:
    try:
        with (folder / "events.jsonl").open(encoding="utf-8") as fh:
            return json.loads(fh.readline() or "{}").get("ts")
    except (OSError, ValueError):
        return None


def locate_run_folder(runs_dir: Path, before: set[str], suffix: str, ts: str) -> str | None:
    """The new folder ending in -<scenario>-<mode> whose first recorded event has timestamp `ts`."""
    for name in sorted(run_folders(runs_dir) - before, reverse=True):
        if name.endswith(suffix) and first_event_ts(runs_dir / name) == ts:
            return name
    return None


def safe_run_dir(runs_dir: Path, folder: str) -> Path:
    """Resolve a run folder name strictly inside runs_dir (no traversal, no symlinks out, must look like a run)."""
    if not FOLDER.fullmatch(folder or ""):
        raise HTTPException(404, "Run not found.")
    root = runs_dir.resolve()
    path = (root / folder).resolve()
    if path.parent != root or not path.is_dir():
        raise HTTPException(404, "Run not found.")
    if not ((path / "events.jsonl").is_file() or (path / "result.json").is_file()):
        raise HTTPException(404, "Run not found.")
    return path


def safe_run_file(runs_dir: Path, folder: str, name: str) -> tuple[Path, str]:
    """Only files a run is expected to contain: step screenshots and the redacted local-agent log."""
    media = next((media for pattern, media in FILES.items() if pattern.fullmatch(name or "")), None)
    if media is None:
        raise HTTPException(404, "File not found.")
    path = (safe_run_dir(runs_dir, folder) / name).resolve()
    if path.parent.parent != runs_dir.resolve() or not path.is_file():
        raise HTTPException(404, "File not found.")
    return path, media


def read_text(path: Path, limit: int = MAX_TEXT) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if len(text) <= limit else text[:limit] + "\n\n… (truncated)"


def report_details(report: str) -> dict:
    """Checks, answer-key items and the cost/token lines from a report.md written by RunRecorder."""
    checks, items, lines, section, key = [], [], {}, "", None
    for raw in report.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            section = line
            heading = KEY_HEADING.match(line)
            if heading:
                key = {"found": int(heading["found"]), "total": int(heading["total"]), "items": items}
            continue
        if match := LINE.match(line):
            lines[match["key"]] = match["value"]
        elif section.startswith("## Automatic checks") and (match := CHECK_ROW.match(line)):
            checks.append({"name": match["name"], "passed": match["result"] == "PASS", "detail": match["detail"]})
        elif section.startswith("## Answer-key") and (match := KEY_ROW.match(line)) and match["id"] != "ID":
            items.append({"id": match["id"], "title": match["title"], "reported": match["hit"] == "yes"})
    return {"checks": checks, "answer_key": key, "cost_detail": lines.get("Estimated cost"),
            "tokens_detail": lines.get("Tokens")}


def screenshots(path: Path) -> list[str]:
    return sorted(p.name for p in path.glob("step-*.png") if re.fullmatch(r"step-\d{3,4}\.png", p.name))


def started_at(folder: str) -> str | None:
    try:
        return datetime.strptime(folder[:15], "%Y%m%d-%H%M%S").isoformat()
    except ValueError:
        return None


def result_payload(result: dict, runs_dir: Path) -> dict:
    """A RunResult (as a dict) plus what the UI needs from its folder: checks, answer key, screenshots, log."""
    folder = Path(result.get("run_dir") or "").name
    payload = {**result, "folder": folder or None, "started": started_at(folder), "checks": [],
               "answer_key": None, "cost_detail": None, "tokens_detail": None, "screenshots": [], "has_log": False}
    payload.pop("run_dir", None)
    try:
        path = safe_run_dir(runs_dir, folder)
    except HTTPException:
        return payload
    payload.update(report_details(read_text(path / "report.md")))
    payload["screenshots"] = screenshots(path)
    payload["has_log"] = (path / "local-agent.log").is_file()
    payload["run_path"] = str(path)
    return payload


def read_events(path: Path, limit: int = 5000) -> list[dict]:
    events = []
    try:
        with (path / "events.jsonl").open(encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh):
                if number >= limit:
                    break
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return events
